"""3-stage LLM Council orchestration with multi-round deliberation."""

import time
import re
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, AsyncGenerator, Callable, Optional
from .lmstudio import query_models_parallel, query_model_with_retry, query_model_streaming
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL, FORMATTER_MODEL
from .config_loader import get_deliberation_rounds, get_deliberation_config, get_response_config, get_tool_calling_model
from .model_metrics import (
    record_query_result, 
    record_evaluation, 
    get_evaluator_for_model,
    get_valid_models
)
from .mcp.registry import get_mcp_registry
from .prompt_library import generate_extraction_prompt, find_matching_prompt
from .memory_service import get_memory_service


def get_memory_context() -> str:
    """
    Build memory context string with AI/user names for system prompt injection.
    Returns empty string if memory service unavailable or names not loaded.
    """
    try:
        memory_service = get_memory_service()
        if not memory_service.is_available or not memory_service.names_loaded:
            return ""
        
        context_parts = []
        
        if memory_service.ai_name:
            context_parts.append(f"Your name is {memory_service.ai_name}.")
        
        if memory_service.user_name:
            context_parts.append(f"The user's name is {memory_service.user_name}.")
        
        if context_parts:
            return "IDENTITY FROM MEMORY:\n" + " ".join(context_parts) + "\n\n"
        
        return ""
    except Exception:
        return ""


# ============== Response Post-Processing ==============

def strip_fake_images(text: str) -> str:
    """Remove markdown image references with placeholder/fake URLs.
    
    Models sometimes generate fake placeholder images like:
    ![Image](https://via.placeholder.com/...)
    ![Chart](https://example.com/image.png)
    
    These render as broken image icons, so we strip them.
    """
    # Pattern matches markdown images: ![alt](url)
    # We remove images with common placeholder/fake URL patterns
    fake_url_patterns = [
        r'!\[[^\]]*\]\(https?://via\.placeholder\.com[^\)]*\)',  # via.placeholder.com
        r'!\[[^\]]*\]\(https?://placeholder\.[^\)]*\)',  # placeholder.* domains
        r'!\[[^\]]*\]\(https?://example\.com[^\)]*\)',  # example.com (fake)
        r'!\[[^\]]*\]\(https?://[^\)]*\?text=[^\)]*\)',  # URLs with ?text= (placeholder text)
        r'!\[[^\]]*\]\(https?://[^\)]+/placeholder[^\)]*\)',  # URLs containing /placeholder
    ]
    
    result = text
    for pattern in fake_url_patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Clean up extra blank lines left behind
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip()


# ============== Token Tracking ==============

class TokenTracker:
    """Track tokens per second and timing for streaming models."""
    
    def __init__(self):
        self.start_times: Dict[str, float] = {}
        self.thinking_end_times: Dict[str, float] = {}
        self.token_counts: Dict[str, int] = {}
    
    def record_thinking(self, model: str, delta: str = "") -> float:
        """Record that thinking is happening (start timer if not started)."""
        now = time.time()
        if model not in self.start_times:
            self.start_times[model] = now
            self.token_counts[model] = 0
        
        # Count thinking tokens too
        if delta:
            self.token_counts[model] += max(1, len(delta.split()))
        
        elapsed = now - self.start_times[model]
        if elapsed > 0:
            return round(self.token_counts[model] / elapsed, 1)
        return 0.0
    
    def mark_thinking_done(self, model: str):
        """Mark when thinking phase ends and response begins."""
        if model not in self.thinking_end_times:
            self.thinking_end_times[model] = time.time()
    
    def record_token(self, model: str, delta: str) -> float:
        """Record a token and return current tokens/second."""
        now = time.time()
        
        if model not in self.start_times:
            self.start_times[model] = now
            self.token_counts[model] = 0
        
        # Mark thinking as done when first response token arrives
        if model not in self.thinking_end_times:
            self.thinking_end_times[model] = now
        
        # Count tokens (approximate by whitespace-separated words + 1 for partial)
        self.token_counts[model] += max(1, len(delta.split()))
        
        elapsed = now - self.start_times[model]
        if elapsed > 0:
            return round(self.token_counts[model] / elapsed, 1)
        return 0.0
    
    def get_timing(self, model: str) -> Dict[str, int]:
        """Get timing info: thinking_seconds and elapsed_seconds."""
        now = time.time()
        start = self.start_times.get(model, now)
        thinking_end = self.thinking_end_times.get(model)
        
        elapsed = int(now - start)
        thinking = int(thinking_end - start) if thinking_end else elapsed
        
        return {"thinking_seconds": thinking, "elapsed_seconds": elapsed}
    
    def get_final_tps(self, model: str) -> float:
        """Get final tokens/second for a model."""
        if model not in self.start_times:
            return 0.0
        elapsed = time.time() - self.start_times[model]
        if elapsed > 0:
            return round(self.token_counts.get(model, 0) / elapsed, 1)
        return 0.0
    
    def get_final_timing(self, model: str) -> Dict[str, int]:
        """Get final timing info: thinking_seconds and elapsed_seconds."""
        now = time.time()
        start = self.start_times.get(model, now)
        thinking_end = self.thinking_end_times.get(model)
        
        elapsed = int(now - start)
        thinking = int(thinking_end - start) if thinking_end else elapsed
        
        return {"thinking_seconds": thinking, "elapsed_seconds": elapsed}


# ============== Message Classification ==============

async def classify_message(user_query: str, on_event: Optional[Callable] = None) -> Dict[str, Any]:
    """
    Classify the user message to determine if it requires deliberation.
    
    Returns:
        Dict with 'type' (factual|chat|deliberation), 'requires_tools', 'reasoning'
    """
    classification_prompt = """Analyze this user message and classify it.

Message: {query}

Respond with ONLY a JSON object (no other text):
{{
  "type": "factual|chat|deliberation",
  "requires_tools": true/false,
  "reasoning": "brief explanation (max 10 words)"
}}

Classification rules:
- "factual": Questions with definitive answers (math, dates, definitions, simple facts, how-to with clear answer)
- "chat": Greetings, acknowledgments, small talk, simple yes/no questions about the AI itself, questions about the AI's identity/capabilities/nature (like "tell me about yourself", "who are you", "what can you do"), commands/requests to the AI (like setting a name/nickname), confirmations, thank you messages
- "deliberation": Opinions, comparisons, feedback requests, creative work, complex analysis, subjective questions requiring multiple human perspectives, anything requiring debate between different viewpoints

requires_tools rules:
- TRUE if query needs: current date/time, current weather, real-time data, web search, IP/location lookup, calculations, external APIs
- FALSE if answer can come from general knowledge without real-time data

Examples:
- "What is 3+5?" → factual, requires_tools: true (calculator)
- "Hello, how are you?" → chat, requires_tools: false
- "Which is better, Python or JavaScript?" → deliberation, requires_tools: false
- "Review my code" → deliberation, requires_tools: false
- "What's the capital of France?" → factual, requires_tools: false (general knowledge)
- "Can you help me?" → chat, requires_tools: false
- "What do you think about AI?" → deliberation, requires_tools: false
- "Tell me about yourself" → chat, requires_tools: false (AI self-description)
- "Who are you?" → chat, requires_tools: false (AI identity)
- "What can you do?" → chat, requires_tools: false (AI capabilities)
- "What time is it?" → factual, requires_tools: true (current time)
- "What's the current weather?" → factual, requires_tools: true (real-time data)
- "Where am I located?" → factual, requires_tools: true (IP/location lookup)
- "What's in the news today?" → factual, requires_tools: true (web search)
- "Call me John" → chat, requires_tools: false (nickname request)
- "You shall be known as X" → chat, requires_tools: false (AI name assignment)
- "Thanks!" → chat, requires_tools: false"""

    messages = [{"role": "user", "content": classification_prompt.format(query=user_query)}]
    tool_model = get_tool_calling_model()
    
    if on_event:
        on_event("classification_start", {"model": tool_model})
    
    try:
        # Use temperature=0 for deterministic classification
        response = await query_model_with_retry(tool_model, messages, timeout=30.0, max_retries=1, temperature=0.0)
        
        if not response or not response.get('content'):
            print("[Classification] No response, defaulting to deliberation")
            return {"type": "deliberation", "requires_tools": False, "reasoning": "Classification failed"}
        
        content = response['content'].strip()
        print(f"[Classification] Response: {content[:200]}")
        
        # Extract JSON from response
        result = _extract_json_from_response(content)
        
        if result and "type" in result:
            # Validate type
            if result["type"] not in ["factual", "chat", "deliberation"]:
                result["type"] = "deliberation"
            
            if on_event:
                on_event("classification_complete", result)
            
            return result
        
        # Default to deliberation if parsing fails
        print("[Classification] JSON parse failed, defaulting to deliberation")
        return {"type": "deliberation", "requires_tools": False, "reasoning": "Parse failed"}
        
    except Exception as e:
        print(f"[Classification] Error: {e}, defaulting to deliberation")
        return {"type": "deliberation", "requires_tools": False, "reasoning": f"Error: {str(e)[:30]}"}


async def chairman_direct_response(
    user_query: str,
    tool_result: Optional[Dict[str, Any]],
    on_event: Optional[Callable] = None,
    retry_count: int = 0
) -> Dict[str, Any]:
    """
    Generate a direct response from the chairman without council deliberation.
    Used for factual questions and casual chat.
    If a formatter model is configured and different from chairman, it formats the final response.
    Includes refusal detection and retry logic for tool-based queries.
    
    Args:
        user_query: The user's question
        tool_result: Optional tool execution result
        on_event: Optional callback for streaming events
        retry_count: Internal counter for retry attempts
        
    Returns:
        Dict with 'model', 'response', 'type'
    """
    max_retries = 2
    
    # Include current date/time context
    current_time = datetime.now()
    time_context = f"Today's date: {current_time.strftime('%B %d, %Y')} | Current time: {current_time.strftime('%H:%M')}"
    
    # Build prompt and system message based on whether tools were used
    system_message = None
    has_tool_data = tool_result and tool_result.get('success')
    tool_failed = _tool_output_failed(tool_result)
    
    if has_tool_data and not tool_failed:
        tool_context = format_tool_result_for_prompt(tool_result)
        
        # Increasingly strong system message based on retry count
        if retry_count == 0:
            system_message = f"""CRITICAL SYSTEM FACTS - These override your training data:
- Current date: {current_time.strftime('%Y-%m-%d')} ({current_time.strftime('%A, %B %d, %Y')})
- Current time: {current_time.strftime('%H:%M:%S')}
- Current year: {current_time.year}

YOU HAVE REAL-TIME ACCESS: A tool was just executed to retrieve LIVE, CURRENT information. 
The tool output in the user message is REAL DATA from RIGHT NOW - not hypothetical or simulated.
NEVER say you "cannot access current information" or "lack real-time data" - you HAVE it via tools.
Your training data cutoff is IRRELEVANT for this query - trust the tool output completely."""
        else:
            # Stronger prompt for retries
            system_message = f"""⚠️ MANDATORY INSTRUCTIONS - VIOLATION WILL BE FLAGGED:

FACT 1: Today is {current_time.strftime('%Y-%m-%d')} ({current_time.strftime('%A, %B %d, %Y')})
FACT 2: The year is {current_time.year} - THIS IS THE PRESENT, NOT THE FUTURE
FACT 3: A tool WAS EXECUTED and returned REAL DATA below

🚫 FORBIDDEN RESPONSES (you will be retried if you say these):
- "I cannot access real-time information"
- "I don't have access to current data"  
- "My training data ends in..."
- "I cannot browse the internet"
- Any claim about lacking current information

✅ REQUIRED BEHAVIOR:
- Treat the tool output as FACTUAL CURRENT DATA
- Present the information as if you retrieved it yourself
- Answer the question using ONLY the tool output data
- Do NOT apologize for limitations - you have the data!

The tool output below is REAL. Use it."""
        
        # Use intelligent prompt engineering for extraction guidance
        tool_type = tool_result.get('tool', '')
        tool_output = tool_result.get('output', {})
        
        # Try to get a dynamically generated or cached extraction prompt
        extraction_prompt = await generate_extraction_prompt(user_query, tool_type, tool_output)
        
        # Format tool output more cleanly - extract just the result data
        clean_output = _extract_clean_tool_output(tool_output)
        
        prompt = f"""A tool was executed to answer the user's question. Use ONLY the result data below.

TOOL RESULT DATA:
{clean_output}

RESPONSE INSTRUCTIONS:
{extraction_prompt}

FORMATTING RULES:
- Give a DIRECT, NATURAL answer - do NOT mention "tool", "output", "JSON", or technical details
- Do NOT include raw data structures like {{"key": "value"}} in your response
- Do NOT repeat information multiple times
- For calculations: just state the answer (e.g., "5 plus 3 equals 8")
- For time/date: state once clearly (e.g., "It's 2:15 PM on Friday, November 29, 2025")
- Be conversational and concise

Question: {user_query}"""
    elif has_tool_data and tool_failed:
        # Tool was called but failed - be honest about it
        tool_context = format_tool_result_for_prompt(tool_result)
        system_message = f"""Current date: {current_time.strftime('%Y-%m-%d')} ({current_time.strftime('%A, %B %d, %Y')})
Current time: {current_time.strftime('%H:%M:%S')}

A tool was called to get real-time information but it FAILED.
You MUST be honest about this failure. Do NOT make up or fabricate data.
Tell the user what happened and suggest alternatives."""
        
        prompt = f"""{tool_context}

Question: {user_query}

The tool failed to retrieve the requested information. Be honest about this failure.
Do NOT fabricate or make up data. Explain what went wrong and suggest the user try again later."""
    else:
        prompt = f"""Answer this question directly and concisely.

Question: {user_query}
({time_context})

Provide a helpful, accurate answer. Be concise but complete."""
    
    # Build messages with optional system message
    # Prepend memory context (AI/user names) if available
    memory_context = get_memory_context()
    if system_message:
        system_message = memory_context + system_message
    elif memory_context:
        # Create system message just for memory context
        system_message = memory_context.strip()
    
    if system_message:
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
    else:
        messages = [{"role": "user", "content": prompt}]
    content = ""
    reasoning = ""
    token_tracker = TokenTracker()
    
    if on_event:
        on_event("direct_response_start", {"model": CHAIRMAN_MODEL, "retry": retry_count})
    
    async for chunk in query_model_streaming(CHAIRMAN_MODEL, messages):
        if chunk["type"] == "token":
            content = chunk["content"]
            tps = token_tracker.record_token(CHAIRMAN_MODEL, chunk["delta"])
            timing = token_tracker.get_timing(CHAIRMAN_MODEL)
            if on_event:
                on_event("direct_response_token", {
                    "model": CHAIRMAN_MODEL,
                    "delta": chunk["delta"],
                    "content": content,
                    "tokens_per_second": tps,
                    **timing
                })
        elif chunk["type"] == "thinking":
            reasoning = chunk["content"]
            tps = token_tracker.record_thinking(CHAIRMAN_MODEL, chunk["delta"])
            timing = token_tracker.get_timing(CHAIRMAN_MODEL)
            if on_event:
                on_event("direct_response_thinking", {
                    "model": CHAIRMAN_MODEL,
                    "delta": chunk["delta"],
                    "thinking": reasoning,
                    "tokens_per_second": tps,
                    **timing
                })
        elif chunk["type"] == "complete":
            chairman_content = chunk["content"]
            
            # Check for refusal if we have tool data
            if has_tool_data and _contains_refusal(chairman_content) and retry_count < max_retries:
                print(f"[Direct Response] Detected refusal in response (attempt {retry_count + 1}), retrying...")
                if on_event:
                    on_event("direct_response_retry", {
                        "model": CHAIRMAN_MODEL,
                        "reason": "refusal_detected",
                        "attempt": retry_count + 1
                    })
                return await chairman_direct_response(user_query, tool_result, on_event, retry_count + 1)
            
            if on_event:
                on_event("direct_response_complete", {
                    "model": CHAIRMAN_MODEL,
                    "response": chairman_content,
                    "tokens_per_second": token_tracker.get_final_tps(CHAIRMAN_MODEL),
                    **token_tracker.get_final_timing(CHAIRMAN_MODEL)
                })
            
            # Apply formatter if configured and different from chairman
            if FORMATTER_MODEL and FORMATTER_MODEL != CHAIRMAN_MODEL:
                formatted_content = await _apply_formatter(
                    chairman_content, user_query, on_event, token_tracker
                )
                return {
                    "model": FORMATTER_MODEL,
                    "response": formatted_content,
                    "type": "direct",
                    "chairman_model": CHAIRMAN_MODEL
                }
            
            return {
                "model": CHAIRMAN_MODEL,
                "response": chairman_content,
                "type": "direct"
            }
        elif chunk["type"] == "error":
            if on_event:
                on_event("direct_response_error", {
                    "model": CHAIRMAN_MODEL,
                    "error": chunk["error"]
                })
            return {
                "model": CHAIRMAN_MODEL,
                "response": content if content else "Error generating response.",
                "type": "direct"
            }
    
    return {
        "model": CHAIRMAN_MODEL,
        "response": content if content else "Error generating response.",
        "type": "direct"
    }


async def _apply_formatter(
    content: str,
    original_query: str,
    on_event: Optional[Callable],
    token_tracker: TokenTracker
) -> str:
    """
    Apply the formatter model to improve response formatting.
    
    Args:
        content: The chairman's response to format
        original_query: The user's original question
        on_event: Optional callback for streaming events
        token_tracker: Token tracker for metrics
        
    Returns:
        Formatted response string
    """
    formatter_prompt = f"""You are a response formatter. Your job is to improve the formatting and readability of the following response without changing its meaning or content.

Original question: {original_query}

Response to format:
{content}

Improve the formatting by:
- Using clear paragraphs and structure
- Adding bullet points or numbered lists where appropriate
- Using bold/italic for emphasis where helpful
- Ensuring proper markdown formatting
- Keeping the content accurate and complete

Return ONLY the formatted response, nothing else."""

    messages = [{"role": "user", "content": formatter_prompt}]
    formatted_content = ""
    
    if on_event:
        on_event("formatter_start", {"model": FORMATTER_MODEL})
    
    async for chunk in query_model_streaming(FORMATTER_MODEL, messages):
        if chunk["type"] == "token":
            formatted_content = chunk["content"]
            tps = token_tracker.record_token(FORMATTER_MODEL, chunk["delta"])
            timing = token_tracker.get_timing(FORMATTER_MODEL)
            if on_event:
                on_event("formatter_token", {
                    "model": FORMATTER_MODEL,
                    "delta": chunk["delta"],
                    "content": formatted_content,
                    "tokens_per_second": tps,
                    **timing
                })
        elif chunk["type"] == "thinking":
            tps = token_tracker.record_thinking(FORMATTER_MODEL, chunk["delta"])
            timing = token_tracker.get_timing(FORMATTER_MODEL)
            if on_event:
                on_event("formatter_thinking", {
                    "model": FORMATTER_MODEL,
                    "delta": chunk["delta"],
                    "thinking": chunk["content"],
                    "tokens_per_second": tps,
                    **timing
                })
        elif chunk["type"] == "complete":
            formatted_content = chunk["content"]
            if on_event:
                on_event("formatter_complete", {
                    "model": FORMATTER_MODEL,
                    "response": formatted_content,
                    "tokens_per_second": token_tracker.get_final_tps(FORMATTER_MODEL),
                    **token_tracker.get_final_timing(FORMATTER_MODEL)
                })
        elif chunk["type"] == "error":
            if on_event:
                on_event("formatter_error", {
                    "model": FORMATTER_MODEL,
                    "error": chunk["error"]
                })
            # Fall back to original content on error
            return content
    
    return formatted_content if formatted_content else content


# ============== Quality Rating Extraction ==============

def extract_quality_ratings(ranking_text: str) -> Dict[str, float]:
    """
    Extract quality ratings from ranking text.
    Looks for patterns like:
    - "Response A (4/5)" or "Response A: 4/5"
    - "Response B - 2/5" or "Response B: 2 out of 5"
    
    Returns dict mapping response labels to ratings (1-5 scale).
    """
    ratings = {}
    
    # Pattern 1: "Response X (N/5)" or "Response X: N/5"
    pattern1 = r'Response\s+([A-Z])\s*[:\(]\s*(\d(?:\.\d)?)\s*/\s*5'
    for match in re.finditer(pattern1, ranking_text, re.IGNORECASE):
        label = f"Response {match.group(1).upper()}"
        rating = float(match.group(2))
        ratings[label] = min(5, max(1, rating))
    
    # Pattern 2: "Response X - N/5" 
    pattern2 = r'Response\s+([A-Z])\s*-\s*(\d(?:\.\d)?)\s*/\s*5'
    for match in re.finditer(pattern2, ranking_text, re.IGNORECASE):
        label = f"Response {match.group(1).upper()}"
        if label not in ratings:
            rating = float(match.group(2))
            ratings[label] = min(5, max(1, rating))
    
    # Pattern 3: Infer from ranking position if no explicit ratings
    # (first place = 5, second = 4, etc.)
    if not ratings:
        parsed = parse_ranking_from_text(ranking_text)
        for i, label in enumerate(parsed):
            ratings[label] = max(1, 5 - i)
    
    return ratings


def check_quality_threshold(all_ratings: List[Dict[str, float]], threshold: float = 0.3) -> Tuple[bool, List[str]]:
    """
    Check if any response is rated below threshold (30% = 1.5/5).
    
    Returns:
        Tuple of (should_continue, list of low-rated response labels)
    """
    min_rating = threshold * 5  # Convert percentage to 1-5 scale
    low_rated = set()
    
    for ratings in all_ratings:
        for label, rating in ratings.items():
            if rating < min_rating:
                low_rated.add(label)
    
    return len(low_rated) > 0, list(low_rated)


# ============== MCP Tool Integration ==============

def _extract_json_from_response(content: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON object from LLM response text.
    Handles nested objects and common LLM formatting issues.
    """
    # First try to find a JSON object starting with {"use_tool" or {"tool"
    json_start = content.find('{"use_tool"')
    if json_start == -1:
        json_start = content.find('{"tool"')
    if json_start == -1:
        json_start = content.find('{')
    
    if json_start == -1:
        print("[MCP] No JSON object found in response")
        return None
    
    # Find the matching closing brace
    brace_count = 0
    json_end = json_start
    for i, char in enumerate(content[json_start:], json_start):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break
    
    if brace_count != 0:
        print("[MCP] Unbalanced braces in JSON")
        return None
    
    json_str = content[json_start:json_end]
    print(f"[MCP] Extracted JSON: {json_str}")
    
    # Try to fix common JSON issues from LLM output
    # Fix unquoted keys like {a: 5} -> {"a": 5}
    fixed_json = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1 "\2":', json_str)
    if fixed_json != json_str:
        print(f"[MCP] Fixed JSON: {fixed_json}")
        json_str = fixed_json
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[MCP] Failed to parse JSON: {e}")
        return None


async def _analyze_user_expectations(user_query: str) -> Optional[Dict[str, Any]]:
    """
    Step 1: Use LLM to analyze what the user expects from this query.
    
    Returns:
        Dict with 'expectations' (list), 'needs_external_data', 'data_types_needed'
    """
    current_time = datetime.now()
    
    analysis_prompt = f"""Analyze what a user expects when asking this question.

CURRENT CONTEXT:
- Today's date: {current_time.strftime('%Y-%m-%d')} ({current_time.strftime('%A, %B %d, %Y')})
- Current time: {current_time.strftime('%H:%M:%S')}

USER QUERY: {user_query}

Respond with ONLY a JSON object:
{{
  "expectations": ["list of 2-4 specific things the user expects in a good answer"],
  "needs_external_data": true/false,
  "data_types_needed": ["list of data types: 'current_time', 'location', 'news', 'weather', 'calculation', 'web_content', 'none'"],
  "reasoning": "brief explanation"
}}

IMPORTANT RULES:
- "address", "location", "where am i", "my city" → needs_external_data: TRUE, data_types_needed: ["location"]
- "news", "current events", "what's happening", "this week" → needs_external_data: TRUE, data_types_needed: ["news"]
- "time", "date", "what day" → needs_external_data: TRUE, data_types_needed: ["current_time"]
- "weather", "temperature", "forecast" → needs_external_data: TRUE, data_types_needed: ["weather", "news"]
- **ANY math or calculation** (even simple ones like 2+2) → needs_external_data: TRUE, data_types_needed: ["calculation"]
- general knowledge (capitals, definitions, history) → needs_external_data: FALSE, data_types_needed: ["none"]
- greetings, chat → needs_external_data: FALSE, data_types_needed: ["none"]

Examples:
- "What time is it?" → needs_external_data: true, data_types_needed: ["current_time"]
- "What's my address?" → needs_external_data: true, data_types_needed: ["location"]
- "What's in the news?" → needs_external_data: true, data_types_needed: ["news"]
- "What major events happened this week?" → needs_external_data: true, data_types_needed: ["news"]
- "What is 15*7?" → needs_external_data: true, data_types_needed: ["calculation"]
- "What is 5 plus 3?" → needs_external_data: true, data_types_needed: ["calculation"]
- "Calculate 2+2" → needs_external_data: true, data_types_needed: ["calculation"]
- "What's the capital of France?" → needs_external_data: false, data_types_needed: ["none"]
- "Hello!" → needs_external_data: false, data_types_needed: ["none"]

JSON response:"""

    messages = [{"role": "user", "content": analysis_prompt}]
    tool_model = get_tool_calling_model()
    
    try:
        # Use temperature=0 for deterministic tool decision making
        response = await query_model_with_retry(tool_model, messages, timeout=30.0, max_retries=1, temperature=0.0)
        if not response or not response.get('content'):
            return None
        
        content = response['content'].strip()
        result = _extract_json_from_response(content)
        
        if result and 'expectations' in result:
            # Normalize data types to match DATA_TYPE_TO_TOOL keys
            data_types = result.get('data_types_needed', [])
            normalized_types = []
            for dt in data_types:
                dt_lower = dt.lower().strip()
                # Map common variations to canonical names
                if 'news' in dt_lower or 'headline' in dt_lower or 'event' in dt_lower:
                    normalized_types.append('news')
                elif 'weather' in dt_lower or 'temperature' in dt_lower or 'forecast' in dt_lower:
                    normalized_types.append('weather')
                elif 'time' in dt_lower or 'date' in dt_lower or 'day' in dt_lower:
                    normalized_types.append('current_time')
                elif 'location' in dt_lower or 'address' in dt_lower or 'geo' in dt_lower:
                    normalized_types.append('location')
                elif 'calc' in dt_lower or 'math' in dt_lower or 'compute' in dt_lower:
                    normalized_types.append('calculation')
                elif 'web' in dt_lower or 'url' in dt_lower or 'page' in dt_lower:
                    normalized_types.append('web_content')
                elif dt_lower != 'none':
                    normalized_types.append(dt_lower)  # Keep as-is if not matched
            
            # Remove duplicates while preserving order
            seen = set()
            unique_types = []
            for dt in normalized_types:
                if dt not in seen:
                    seen.add(dt)
                    unique_types.append(dt)
            
            result['data_types_needed'] = unique_types if unique_types else ['none']
            print(f"[Expectations] {result.get('expectations', [])}, needs_external: {result.get('needs_external_data')}, data_types: {result.get('data_types_needed', [])}")
            return result
        return None
    except Exception as e:
        print(f"[Expectations] Error: {e}")
        return None


async def _evaluate_tool_confidence(
    user_query: str,
    expectations: Dict[str, Any],
    available_tools: str
) -> Optional[Dict[str, Any]]:
    """
    Step 2: Map data types to tools using a deterministic mapping.
    
    This replaces the LLM-based evaluation with a fast, reliable mapping.
    
    Returns:
        Dict with 'recommended_tool', 'confidence' (0.0-1.0), 'reasoning'
    """
    data_types = expectations.get('data_types_needed', [])
    
    # If no external data needed, skip tool evaluation
    if not expectations.get('needs_external_data', False):
        return {
            "recommended_tool": None,
            "confidence": 0.0,
            "reasoning": "Query can be answered from general knowledge"
        }
    
    # Direct mapping from data types to tools
    # For calculator, we use 'calculator.add' as a placeholder - Phase 2 will determine
    # the correct operation (add, subtract, multiply, divide) based on the query
    DATA_TYPE_TO_TOOL = {
        'current_time': ('system-date-time.get-system-date-time', 'system-date-time', 0.95),
        'location': ('system-geo-location.get-system-geo-location', 'system-geo-location', 0.95),
        'news': ('websearch.search', 'websearch', 0.9),
        'weather': ('websearch.search', 'websearch', 0.9),
        'current_events': ('websearch.search', 'websearch', 0.9),
        'calculation': ('calculator', 'calculator', 0.85),  # Server name only - Phase 2 picks operation
        'web_content': ('retrieve-web-page.get-page-from-url', 'retrieve-web-page', 0.8),
    }
    
    # Find the best matching tool based on data types
    best_tool = None
    best_confidence = 0.0
    best_server = None
    
    for data_type in data_types:
        data_type_lower = data_type.lower()
        if data_type_lower in DATA_TYPE_TO_TOOL:
            tool_name, server, confidence = DATA_TYPE_TO_TOOL[data_type_lower]
            if confidence > best_confidence:
                best_tool = tool_name
                best_server = server
                best_confidence = confidence
    
    if best_tool:
        print(f"[Tool Confidence] Direct mapping: {best_tool} (confidence: {best_confidence})")
        return {
            "recommended_tool": best_tool,
            "confidence": best_confidence,
            "reasoning": f"Data type '{data_types}' maps to {best_tool}",
            "tool_arguments": {}
        }
    
    # No matching tool found
    return {
        "recommended_tool": None,
        "confidence": 0.0,
        "reasoning": f"No tool maps to data types: {data_types}"
    }


# Minimum confidence threshold for using a tool
TOOL_CONFIDENCE_THRESHOLD = 0.5  # Lowered from 0.6 for better tool coverage

# Phrases that indicate the model is refusing to use tool data
REFUSAL_PHRASES = [
    "cannot access",
    "can't access",
    "lack real-time",
    "don't have access to real-time",
    "do not have access to real-time",
    "training data cutoff",
    "knowledge cutoff",
    "cannot provide current",
    "can't provide current",
    "unable to access",
    "no access to",
    "cannot retrieve",
    "can't retrieve",
    "don't have real-time",
    "do not have real-time",
    "as of my last update",
    "as of my training",
    "i cannot browse",
    "i can't browse",
    "don't have access to personal",
    "do not have access to personal",
    "cannot access personal",
]


def _contains_refusal(text: str) -> bool:
    """Check if text contains refusal phrases about real-time access."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in REFUSAL_PHRASES)


def _tool_output_failed(tool_result: Optional[Dict[str, Any]]) -> bool:
    """
    Check if tool output content indicates a failure.
    Returns True if the tool's internal result shows an error.
    """
    if not tool_result:
        return True
    if not tool_result.get('success'):
        return True
    
    output = tool_result.get('output', {})
    if isinstance(output, dict) and 'content' in output:
        content = output['content']
        if isinstance(content, list) and len(content) > 0:
            text_content = content[0].get('text', '')
            try:
                result_data = json.loads(text_content)
                if isinstance(result_data, dict):
                    if result_data.get('success') is False:
                        return True
                    if 'error' in result_data and result_data.get('error'):
                        return True
            except (json.JSONDecodeError, TypeError):
                pass
    return False


async def _phase1_analyze_query(user_query: str, detailed_tool_info: str) -> Optional[Dict[str, Any]]:
    """
    Phase 1: Analyze the query using LLM-based confidence scoring.
    
    This replaces the old keyword-based approach with a two-step LLM process:
    1. Analyze user expectations for the query
    2. Evaluate tool confidence based on expectations
    
    Returns:
        Dict with 'needs_tool', 'tool_name', 'server', 'reasoning', 'confidence' or None on failure
    """
    # Step 1: Analyze user expectations
    print(f"[MCP Phase 1] Analyzing user expectations...")
    expectations = await _analyze_user_expectations(user_query)
    
    if not expectations:
        print("[MCP Phase 1] Failed to analyze expectations, using fallback")
        # Fallback to simple classification
        return None
    
    # If no external data needed, skip tool evaluation
    if not expectations.get('needs_external_data', False):
        print(f"[MCP Phase 1] No external data needed: {expectations.get('reasoning', '')}")
        return {
            "needs_tool": False,
            "reasoning": expectations.get('reasoning', 'Query can be answered from general knowledge')
        }
    
    # Step 2: Evaluate tool confidence
    print(f"[MCP Phase 1] Evaluating tool confidence for data types: {expectations.get('data_types_needed', [])}")
    tool_eval = await _evaluate_tool_confidence(user_query, expectations, detailed_tool_info)
    
    if not tool_eval:
        print("[MCP Phase 1] Failed to evaluate tool confidence")
        return None
    
    confidence = tool_eval.get('confidence', 0.0)
    recommended_tool = tool_eval.get('recommended_tool')
    
    # Check if confidence meets threshold
    if confidence >= TOOL_CONFIDENCE_THRESHOLD and recommended_tool:
        # Parse server from tool name (format: "server.tool_name")
        parts = recommended_tool.split('.', 1)
        server = parts[0] if len(parts) > 1 else recommended_tool
        
        print(f"[MCP Phase 1] Tool selected: {recommended_tool} (confidence: {confidence:.2f})")
        return {
            "needs_tool": True,
            "tool_name": recommended_tool,
            "server": server,
            "reasoning": tool_eval.get('reasoning', ''),
            "confidence": confidence,
            "tool_arguments": tool_eval.get('tool_arguments', {}),
            "expectations": expectations.get('expectations', [])
        }
    else:
        print(f"[MCP Phase 1] No tool needed (confidence: {confidence:.2f} < threshold: {TOOL_CONFIDENCE_THRESHOLD})")
        return {
            "needs_tool": False,
            "reasoning": tool_eval.get('reasoning', 'No tool meets confidence threshold'),
            "confidence": confidence
        }


async def assess_tool_needs_mid_deliberation(
    user_query: str,
    stage_name: str,
    stage_output: str,
    available_tools: str,
    previous_tool_results: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Assess whether additional tool calls would help after a deliberation stage.
    
    This is called after Stage 1 and Stage 2 to determine if the council
    would benefit from additional data before proceeding.
    
    Args:
        user_query: The original user question
        stage_name: "stage1" or "stage2"
        stage_output: Summary of what the stage produced
        available_tools: Description of available MCP tools
        previous_tool_results: Any tool results already obtained
        
    Returns:
        Dict with 'needs_tool', 'tool_name', 'reasoning', 'arguments' or None
    """
    tool_model = get_tool_calling_model()
    
    # Format previous tool results if any
    prev_results_text = ""
    if previous_tool_results:
        prev_results_text = "\n\nPREVIOUS TOOL RESULTS:\n"
        for result in previous_tool_results:
            tool_name = result.get('tool', 'unknown')
            output = result.get('output', '')
            prev_results_text += f"- {tool_name}: {str(output)[:500]}...\n"
    
    assessment_prompt = f"""You are evaluating whether additional tool calls would improve the council's response.

USER QUERY: {user_query}

CURRENT STAGE: {stage_name}
STAGE OUTPUT SUMMARY: {stage_output[:1000]}...
{prev_results_text}

AVAILABLE TOOLS:
{available_tools}

Assess whether the current responses would benefit from additional data that a tool could provide.

IMPORTANT RULES:
1. Only recommend a tool if the responses are CLEARLY missing crucial information
2. Do NOT recommend tools for general knowledge questions (capitals, definitions, history, nutrition advice, etc.)
3. DO recommend websearch if responses mention "I don't have current information" or similar limitations
4. DO recommend websearch if the query asks about recent events and responses lack specific data
5. Do NOT recommend calculator unless there is an actual mathematical calculation needed
6. If previous tools already provided relevant data, do NOT request more tools

Respond with ONLY a JSON object:
{{
  "needs_additional_tool": true/false,
  "recommended_tool": "tool.name" or null,
  "reasoning": "brief explanation",
  "arguments": {{}} or null
}}

JSON response:"""

    messages = [{"role": "user", "content": assessment_prompt}]
    
    try:
        # Use temperature=0 for deterministic tool assessment
        response = await query_model_with_retry(tool_model, messages, timeout=30.0, max_retries=1, temperature=0.0)
        if not response or not response.get('content'):
            return None
        
        content = response['content'].strip()
        result = _extract_json_from_response(content)
        
        if result and 'needs_additional_tool' in result:
            if result.get('needs_additional_tool') and result.get('recommended_tool'):
                print(f"[Mid-Deliberation Assessment] Tool recommended: {result.get('recommended_tool')}")
                return {
                    "needs_tool": True,
                    "tool_name": result['recommended_tool'],
                    "reasoning": result.get('reasoning', ''),
                    "arguments": result.get('arguments', {})
                }
            else:
                print(f"[Mid-Deliberation Assessment] No additional tools needed: {result.get('reasoning', '')}")
                return {"needs_tool": False, "reasoning": result.get('reasoning', '')}
        
        return None
    except Exception as e:
        print(f"[Mid-Deliberation Assessment] Error: {e}")
        return None


def _parse_calculator_query(query: str) -> Optional[Dict[str, Any]]:
    """
    Parse a calculator query and extract the operation and numbers deterministically.
    
    This is more reliable than using an LLM for simple number extraction.
    
    Returns:
        Dict with 'tool' and 'arguments' or None if parsing fails
    """
    import re
    
    query_lower = query.lower()
    
    # Find all numbers in the query (including decimals)
    numbers = re.findall(r'-?\d+\.?\d*', query)
    if len(numbers) < 2:
        return None
    
    # Convert to float/int
    nums = []
    for n in numbers[:2]:  # Take first two numbers
        if '.' in n:
            nums.append(float(n))
        else:
            nums.append(int(n))
    
    a, b = nums[0], nums[1]
    
    # Determine operation
    operation = None
    if any(op in query_lower for op in ['plus', 'add', '+', 'sum']):
        operation = 'add'
    elif any(op in query_lower for op in ['minus', 'subtract', '-', 'difference']):
        operation = 'subtract'
    elif any(op in query_lower for op in ['times', 'multiply', '*', '×', 'product']):
        operation = 'multiply'
    elif any(op in query_lower for op in ['divided', 'divide', '/', '÷', 'quotient']):
        operation = 'divide'
    
    if operation:
        return {
            "tool": f"calculator.{operation}",
            "arguments": {"a": a, "b": b}
        }
    
    return None


async def _phase2_generate_tool_call(
    user_query: str,
    tool_name: str,
    server_name: str,
    detailed_tool_info: str
) -> Optional[Dict[str, Any]]:
    """
    Phase 2: Generate the specific tool call with arguments.
    
    Returns:
        Dict with 'tool', 'arguments' or None on failure
    """
    # Fast path: Handle calculator operations deterministically
    # This avoids LLM unreliability in parsing simple numbers
    if server_name == 'calculator' or tool_name == 'calculator':
        calc_result = _parse_calculator_query(user_query)
        if calc_result:
            print(f"[MCP Phase 2] Calculator fast path: {calc_result}")
            return calc_result
    
    # Include current date context for time-sensitive queries
    current_time = datetime.now()
    # Calculate week start (Monday) and end (Sunday)
    week_start = current_time - timedelta(days=current_time.weekday())
    week_end = week_start + timedelta(days=6)
    
    date_context = f"""CURRENT DATE CONTEXT (use for time-sensitive queries):
- Today: {current_time.strftime('%A, %B %d, %Y')}
- This week: {week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}
- This month: {current_time.strftime('%B %Y')}
"""
    
    execution_prompt = f"""You need to generate a tool call to answer a user query.

{date_context}
{detailed_tool_info}

USER QUERY: {user_query}

SELECTED SERVER/TOOL: {tool_name}

TASK: Generate the exact tool call with the correct arguments based on the user's query.

CRITICAL for calculator operations - READ THE QUERY CAREFULLY:
- Extract the EXACT numbers from the query "{user_query}"
- "plus", "add", "+" → use "calculator.add" with {{"a": first_number, "b": second_number}}
- "minus", "subtract", "-" → use "calculator.subtract" with {{"a": first_number, "b": second_number}}
- "times", "multiply", "*", "×" → use "calculator.multiply" with {{"a": first_number, "b": second_number}}
- "divided by", "divide", "/", "÷" → use "calculator.divide" with {{"a": first_number, "b": second_number}}
- Example: "What is 5 plus 3?" → {{"tool": "calculator.add", "arguments": {{"a": 5, "b": 3}}}}
- Example: "Calculate 12 times 4" → {{"tool": "calculator.multiply", "arguments": {{"a": 12, "b": 4}}}}

If "{tool_name}" is just a server name (e.g., "calculator"), pick the appropriate operation.
If "{tool_name}" is a full tool name (e.g., "websearch.search"), use that exact tool.

Create a JSON object with:
{{"tool": "server.operation", "arguments": {{...parameters with correct values...}}}}

Important:
- Use the exact parameter names from the tool definition
- For math: use the EXACT numbers from the user's query - do not change them
- For web searches: 
  * Add "news" or "latest" to get actual articles instead of homepages
  * For time-sensitive queries, be SPECIFIC about the time frame:
    - "this week" → include specific date range (e.g., "November 24-28 2025")
    - "today" → include today's exact date
    - "this month" → include month and year
  * Example: "what happened this week" → "major events November 24-28 2025"
  * Example: "top news headlines" → "latest news headlines November 28 2025"
  * Example: "current weather" → "weather forecast today November 28"

Output ONLY the JSON object. No other text."""

    messages = [{"role": "user", "content": execution_prompt}]
    tool_model = get_tool_calling_model()
    
    print(f"[MCP Phase 2] Generating tool call for {tool_name}...")
    response = await query_model_with_retry(tool_model, messages, timeout=None, max_retries=1)
    
    if not response or not response.get('content'):
        print("[MCP Phase 2] No response from model")
        return None
    
    content = response['content'].strip()
    print(f"[MCP Phase 2] Tool call response: {content[:300]}...")
    
    return _extract_json_from_response(content)


async def _needs_deep_research(user_query: str) -> bool:
    """
    Determine if a query needs deep research (multi-page content extraction).
    
    Deep research is needed for queries asking for:
    - Rankings, comparisons, or "top N" lists
    - Comprehensive analysis or reviews
    - Multi-source information gathering
    
    Returns:
        True if deep research workflow should be used
    """
    query_lower = user_query.lower()
    
    # Keywords that suggest need for deep research
    deep_research_patterns = [
        r'\btop\s+\d+\b',           # "top 10", "top 5", etc.
        r'\bbest\s+\d+\b',          # "best 10", "best 5", etc.
        r'\bmost\s+\w+\s+\d+\b',    # "most practical 10", etc.
        r'\branking\b',             # ranking
        r'\bcompare\b',             # compare
        r'\bcomparison\b',          # comparison
        r'\bvs\b',                  # vs
        r'\bversus\b',              # versus
        r'\bwhich\s+are\b.*\best\b', # "which are the best"
        r'\breview\b.*\bmultiple\b', # review multiple
    ]
    
    for pattern in deep_research_patterns:
        if re.search(pattern, query_lower):
            return True
    
    return False


async def _extract_urls_from_search(
    user_query: str,
    search_result: Dict[str, Any],
    max_urls: int = 5
) -> List[str]:
    """
    Use LLM to identify the most relevant URLs from search results.
    
    Args:
        user_query: The user's original query
        search_result: The web search result
        max_urls: Maximum number of URLs to extract
        
    Returns:
        List of URLs most relevant to answering the query
    """
    tool_model = get_tool_calling_model()
    
    # Extract search result text
    search_text = ""
    output = search_result.get('output', {})
    if isinstance(output, dict) and 'content' in output:
        content = output['content']
        if isinstance(content, list) and len(content) > 0:
            search_text = content[0].get('text', '')
    elif isinstance(output, str):
        search_text = output
    
    if not search_text:
        print("[Deep Research] No search results to extract URLs from")
        return []
    
    messages = [{
        "role": "user",
        "content": f"""Analyze these search results and identify the URLs most likely to contain comprehensive information to answer this question:

QUESTION: {user_query}

SEARCH RESULTS:
{search_text}

Return a JSON array of the {max_urls} most relevant URLs. Consider:
- URLs from authoritative sources (major publications, official sites)
- URLs that appear to be article/list pages rather than homepages
- URLs that seem to directly address the question

Return ONLY a JSON array like: ["url1", "url2", "url3"]
No explanation, just the JSON array."""
    }]
    
    response = await query_model_with_retry(tool_model, messages, timeout=30, max_retries=1)
    
    if not response or not response.get('content'):
        return []
    
    content = response['content'].strip()
    
    # Extract JSON array from response
    try:
        # Try direct parse
        urls = json.loads(content)
        if isinstance(urls, list):
            return [url for url in urls if isinstance(url, str) and url.startswith('http')][:max_urls]
    except json.JSONDecodeError:
        pass
    
    # Try to find array in response
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        try:
            urls = json.loads(match.group())
            if isinstance(urls, list):
                return [url for url in urls if isinstance(url, str) and url.startswith('http')][:max_urls]
        except json.JSONDecodeError:
            pass
    
    # Fallback: extract URLs with regex
    url_pattern = r'https?://[^\s\]\)\"\'\,]+'
    urls = re.findall(url_pattern, content)
    return urls[:max_urls]


async def deep_research_workflow(
    user_query: str,
    on_event: Optional[Callable] = None
) -> Optional[Dict[str, Any]]:
    """
    Multi-turn research workflow for comprehensive information gathering.
    
    Steps:
    1. Web search to find relevant sources
    2. LLM selects most relevant URLs
    3. Firecrawl extracts content from selected pages
    4. Combines all content for council deliberation
    
    Args:
        user_query: The user's question
        on_event: Optional callback for streaming events
        
    Returns:
        Combined research results or None on failure
    """
    registry = get_mcp_registry()
    
    # Check if firecrawl and websearch are available
    has_websearch = any('websearch' in t for t in registry.all_tools.keys())
    has_firecrawl = any('firecrawl' in t for t in registry.all_tools.keys())
    
    if not has_websearch or not has_firecrawl:
        print(f"[Deep Research] Missing required tools (websearch: {has_websearch}, firecrawl: {has_firecrawl})")
        return None
    
    print(f"[Deep Research] Starting multi-turn research for: {user_query[:50]}...")
    
    if on_event:
        on_event("deep_research_start", {"query": user_query})
    
    # Step 1: Web search
    print("[Deep Research] Step 1: Performing web search...")
    search_call_id = str(uuid.uuid4())[:8]
    if on_event:
        on_event("tool_call_start", {"tool": "websearch.web-search", "arguments": {"query": user_query}, "call_id": search_call_id})
    
    search_result = await registry.call_tool("websearch.web-search", {"query": user_query})
    
    if on_event:
        on_event("tool_call_complete", {"tool": "websearch.web-search", "result": search_result, "call_id": search_call_id})
    
    if not search_result.get('success'):
        print(f"[Deep Research] Web search failed: {search_result.get('error')}")
        return search_result  # Return search result even if failed
    
    # Step 2: Extract relevant URLs
    print("[Deep Research] Step 2: Identifying relevant URLs...")
    urls = await _extract_urls_from_search(user_query, search_result, max_urls=3)
    
    if not urls:
        print("[Deep Research] No URLs extracted, returning search results only")
        return search_result
    
    print(f"[Deep Research] Found {len(urls)} relevant URLs: {urls}")
    
    # Step 3: Scrape content from each URL
    print("[Deep Research] Step 3: Extracting content from pages...")
    all_content = []
    
    for i, url in enumerate(urls):
        print(f"[Deep Research] Scraping {i+1}/{len(urls)}: {url[:60]}...")
        
        scrape_call_id = str(uuid.uuid4())[:8]
        if on_event:
            on_event("tool_call_start", {"tool": "firecrawl.firecrawl-scrape", "arguments": {"url": url}, "call_id": scrape_call_id})
        
        try:
            scrape_result = await registry.call_tool("firecrawl.firecrawl-scrape", {"url": url})
            
            if on_event:
                on_event("tool_call_complete", {"tool": "firecrawl.firecrawl-scrape", "result": scrape_result, "call_id": scrape_call_id})
            
            if scrape_result.get('success'):
                # Extract content from result
                output = scrape_result.get('output', {})
                content_text = ""
                
                if isinstance(output, dict) and 'content' in output:
                    content = output['content']
                    if isinstance(content, list) and len(content) > 0:
                        content_text = content[0].get('text', '')
                elif isinstance(output, str):
                    content_text = output
                
                if content_text:
                    # Truncate to avoid overwhelming context
                    truncated = content_text[:5000] if len(content_text) > 5000 else content_text
                    all_content.append(f"## Source: {url}\n\n{truncated}")
                    print(f"[Deep Research] Extracted {len(content_text)} chars from {url}")
            else:
                print(f"[Deep Research] Failed to scrape {url}: {scrape_result.get('error')}")
        except Exception as e:
            print(f"[Deep Research] Error scraping {url}: {e}")
    
    if not all_content:
        print("[Deep Research] No content extracted, returning search results only")
        return search_result
    
    # Combine all content
    combined_content = "\n\n---\n\n".join(all_content)
    
    print(f"[Deep Research] Combined {len(all_content)} sources, total {len(combined_content)} chars")
    
    if on_event:
        on_event("deep_research_complete", {
            "sources": len(all_content),
            "total_chars": len(combined_content)
        })
    
    return {
        "success": True,
        "tool": "deep_research",
        "server": "deep_research",
        "input": {"query": user_query, "urls": urls},
        "output": {
            "content": [{
                "type": "text",
                "text": combined_content
            }]
        },
        "executionTime": 0,  # Will be updated
        "sources_count": len(all_content),
        "urls_scraped": urls
    }


async def check_and_execute_tools(user_query: str, on_event: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
    """
    Intelligent two-phase MCP tool execution.
    
    Phase 1: Analyze the query to determine if MCP tools are needed
    Phase 2: Generate and execute the tool call if needed
    
    Also supports deep research workflow for queries needing multiple sources.
    
    Args:
        user_query: The user's question
        on_event: Optional callback for streaming events
        
    Returns:
        Tool execution result if tools were used, None otherwise
    """
    registry = get_mcp_registry()
    
    # Quick pre-check: are there any tools available?
    if not registry.all_tools:
        print("[MCP] No tools available, skipping tool check")
        return None
    
    # Check if this query needs deep research (multi-source)
    if await _needs_deep_research(user_query):
        print("[MCP] Query needs deep research workflow")
        deep_result = await deep_research_workflow(user_query, on_event)
        if deep_result and deep_result.get('success'):
            return deep_result
        # Fall through to regular tool handling if deep research fails
        print("[MCP] Deep research failed, falling back to regular tool handling")
    
    # Get detailed tool information for intelligent analysis
    detailed_tool_info = registry.get_detailed_tool_info()
    if not detailed_tool_info:
        return None
    
    # ===== PHASE 1: Analyze query =====
    analysis = await _phase1_analyze_query(user_query, detailed_tool_info)
    
    if not analysis:
        print("[MCP Phase 1] Analysis failed, proceeding without tools")
        return None
    
    if not analysis.get('needs_tool'):
        reasoning = analysis.get('reasoning', 'No tool needed')
        print(f"[MCP Phase 1] No tool needed: {reasoning}")
        return None
    
    tool_name = analysis.get('tool_name')
    server_name = analysis.get('server', tool_name.split('.')[0] if tool_name and '.' in tool_name else '')
    
    if not tool_name:
        print("[MCP Phase 1] No tool name in analysis result")
        return None
    
    print(f"[MCP Phase 1] Tool needed: {tool_name} (reason: {analysis.get('reasoning', 'N/A')})")
    
    # ===== PHASE 2: Generate tool call =====
    tool_call = await _phase2_generate_tool_call(user_query, tool_name, server_name, detailed_tool_info)
    
    if not tool_call:
        print("[MCP Phase 2] Failed to generate tool call")
        return None
    
    final_tool_name = tool_call.get('tool', tool_name)
    arguments = tool_call.get('arguments', {})
    
    if not final_tool_name:
        print("[MCP Phase 2] No tool name in generated call")
        return None
    
    print(f"[MCP Phase 2] Executing: {final_tool_name} with args: {arguments}")
    
    # ===== Execute the tool =====
    call_id = str(uuid.uuid4())[:8]
    if on_event:
        on_event("tool_call_start", {
            "tool": final_tool_name,
            "arguments": arguments,
            "call_id": call_id
        })
    
    try:
        result = await registry.call_tool(final_tool_name, arguments)
        
        if on_event:
            on_event("tool_call_complete", {
                "tool": final_tool_name,
                "arguments": arguments,
                "result": result,
                "call_id": call_id
            })
        
        print(f"[MCP] Tool execution complete: success={result.get('success', False)}")
        return result
        
    except Exception as e:
        print(f"[MCP] Tool execution failed: {e}")
        if on_event:
            on_event("tool_call_complete", {
                "tool": final_tool_name,
                "arguments": arguments,
                "result": {"success": False, "error": str(e)},
                "call_id": call_id
            })
        return None


def _extract_clean_tool_output(output: Any) -> str:
    """Extract clean, human-readable data from tool output."""
    # Extract the actual result from MCP response wrapper
    if isinstance(output, dict) and 'content' in output:
        content = output['content']
        if isinstance(content, list) and len(content) > 0:
            text_content = content[0].get('text', '')
            try:
                result_data = json.loads(text_content)
                output = result_data
            except:
                output = text_content
    
    # Format based on tool type - create human-readable strings
    if isinstance(output, dict):
        # Calculator output
        if 'operation' in output and 'result' in output:
            op = output.get('operation', '')
            operands = output.get('operands', {})
            result = output.get('result')
            a = operands.get('a', operands.get('value', ''))
            b = operands.get('b', '')
            if op == 'add':
                return f"{a} + {b} = {result}"
            elif op == 'subtract':
                return f"{a} - {b} = {result}"
            elif op == 'multiply':
                return f"{a} × {b} = {result}"
            elif op == 'divide':
                return f"{a} ÷ {b} = {result}"
            elif op in ['sqrt', 'square_root']:
                return f"√{a} = {result}"
            else:
                return f"Result: {result}"
        
        # DateTime output - use the pre-formatted string if available
        if 'datetime' in output or 'date' in output or 'formatted' in output:
            # Use the formatted string which already includes timezone
            if 'formatted' in output:
                return output['formatted']
            
            parts = []
            tz_str = output.get('timezone', 'local')
            if 'datetime' in output:
                parts.append(f"Date and time: {output['datetime']} ({tz_str})")
            if 'date' in output and 'datetime' not in output:
                parts.append(f"Date: {output.get('formatted_date', output['date'])}")
            if 'time' in output and 'datetime' not in output:
                parts.append(f"Time: {output['time']} ({tz_str})")
            if 'weekday' in output and 'formatted' not in str(output):
                parts.append(f"Day: {output['weekday']}")
            if 'location' in output and output['location'].strip(', '):
                parts.append(f"Location: {output['location']}")
            return '\n'.join(parts) if parts else str(output)
        
        # Location output
        if 'city' in output or 'location' in output:
            parts = []
            if 'city' in output:
                parts.append(output['city'])
            if 'region' in output:
                parts.append(output['region'])
            if 'country' in output:
                parts.append(output['country'])
            return ', '.join(parts) if parts else str(output)
        
        # Web search output - extract snippets
        if 'results' in output or 'organic' in output:
            results = output.get('results', output.get('organic', []))
            if isinstance(results, list):
                items = []
                for r in results[:5]:  # Limit to 5 results
                    title = r.get('title', '')
                    snippet = r.get('snippet', r.get('description', ''))
                    if title and snippet:
                        items.append(f"• {title}: {snippet}")
                return '\n'.join(items) if items else json.dumps(output, indent=2)
        
        # Generic dict - format key-value pairs
        parts = []
        for k, v in output.items():
            if not k.startswith('_'):
                parts.append(f"{k}: {v}")
        return '\n'.join(parts) if parts else json.dumps(output, indent=2)
    
    return str(output)


def format_tool_result_for_prompt(tool_result: Dict[str, Any]) -> str:
    """Format tool execution result for inclusion in prompts."""
    if not tool_result or not tool_result.get('success'):
        return ""
    
    server = tool_result.get('server', 'unknown')
    tool = tool_result.get('tool', 'unknown')
    input_args = tool_result.get('input', {})
    output = tool_result.get('output', {})
    
    # Extract the actual result from MCP response
    tool_failed = False
    error_message = ""
    if isinstance(output, dict) and 'content' in output:
        content = output['content']
        if isinstance(content, list) and len(content) > 0:
            text_content = content[0].get('text', '')
            try:
                result_data = json.loads(text_content)
                # Check if the tool's internal result indicates failure
                if isinstance(result_data, dict):
                    if result_data.get('success') is False or 'error' in result_data:
                        tool_failed = True
                        error_message = result_data.get('error', 'Unknown error')
                output = result_data
            except:
                output = text_content
    
    # Include timestamp to emphasize this is live data
    current_time = datetime.now()
    timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')
    
    if tool_failed:
        return f"""
══════════════════════════════════════════════════════════════
⚠️ TOOL EXECUTION FAILED AT: {timestamp}
══════════════════════════════════════════════════════════════
🔧 Tool: {server}.{tool}
📥 Query: {json.dumps(input_args)}
❌ ERROR: {error_message}
══════════════════════════════════════════════════════════════
⚠️ THE TOOL FAILED - YOU MUST REPORT THIS HONESTLY!
DO NOT make up or fabricate data. Tell the user the tool failed
and offer alternatives (retry later, try different query, etc.)
══════════════════════════════════════════════════════════════
"""
    
    return f"""
══════════════════════════════════════════════════════════════
⚡ LIVE DATA RETRIEVED AT: {timestamp} (just now!)
══════════════════════════════════════════════════════════════
🔧 Tool: {server}.{tool}
📥 Query: {json.dumps(input_args)}
📤 REAL-TIME RESULT:
{json.dumps(output, indent=2) if isinstance(output, dict) else output}
══════════════════════════════════════════════════════════════
⚠️ THIS IS REAL, CURRENT DATA - NOT FROM TRAINING. USE IT!
══════════════════════════════════════════════════════════════
"""


async def stage1_collect_responses(user_query: str) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question

    Returns:
        List of dicts with 'model' and 'response' keys
    """
    messages = [{"role": "user", "content": user_query}]

    # Query all models in parallel
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    # Format results
    stage1_results = []
    for model, response in responses.items():
        if response is not None:  # Only include successful responses
            stage1_results.append({
                "model": model,
                "response": response.get('content', '')
            })

    return stage1_results


async def stage2_multi_round_deliberation(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[List[Dict[str, Any]]], Dict[str, str]]:
    """
    Stage 2: Multi-round deliberation with response refinement.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (list of rankings per round, label_to_model mapping)
    """
    deliberation_config = get_deliberation_config()
    rounds = deliberation_config.get("rounds", 1)
    enable_cross_review = deliberation_config.get("enable_cross_review", True)
    
    # Create initial anonymized labels for responses
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }
    
    all_rounds_rankings = []
    current_responses = stage1_results.copy()  # Track evolving responses
    
    for round_num in range(1, rounds + 1):
        print(f"Running deliberation round {round_num}/{rounds}")
        
        if round_num == 1:
            # First round: standard ranking
            round_rankings = await stage2_single_round_ranking(
                user_query, current_responses, labels, round_num
            )
        else:
            # Subsequent rounds: refinement + ranking
            if enable_cross_review:
                # First refine responses based on previous rounds
                current_responses = await refine_responses_round(
                    user_query, current_responses, all_rounds_rankings[-1], round_num
                )
            
            # Then rank the (potentially refined) responses
            round_rankings = await stage2_single_round_ranking(
                user_query, current_responses, labels, round_num, all_rounds_rankings[-1]
            )
        
        all_rounds_rankings.append(round_rankings)
    
    return all_rounds_rankings, label_to_model


async def stage2_single_round_ranking(
    user_query: str,
    responses: List[Dict[str, Any]],
    labels: List[str],
    round_num: int,
    previous_rankings: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Single round of ranking with optional context from previous rounds."""
    
    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, responses)
    ])
    
    if round_num == 1:
        # First round: standard ranking prompt
        ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""
    
    else:
        # Subsequent rounds: include context from previous rankings
        previous_rankings_text = "\n\n".join([
            f"Previous ranking by {ranking['model']}:\n{ranking['ranking'][:500]}..." 
            if len(ranking['ranking']) > 500 
            else f"Previous ranking by {ranking['model']}:\n{ranking['ranking']}"
            for ranking in previous_rankings
        ])
        
        ranking_prompt = f"""You are evaluating different responses to the following question (Round {round_num}):

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Previous rankings from Round {round_num - 1}:
{previous_rankings_text}

Your task:
1. Consider how the responses may have been refined based on previous feedback
2. Evaluate each current response individually
3. Take into account the previous round's insights and rankings
4. Provide your updated ranking at the end

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")

Now provide your evaluation and ranking for Round {round_num}:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from all council models in parallel
    responses_dict = await query_models_parallel(COUNCIL_MODELS, messages)

    # Format results
    round_results = []
    for model, response in responses_dict.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            round_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed,
                "round": round_num
            })

    return round_results


async def refine_responses_round(
    user_query: str,
    current_responses: List[Dict[str, Any]],
    previous_rankings: List[Dict[str, Any]],
    round_num: int
) -> List[Dict[str, Any]]:
    """Refine responses based on feedback from previous round."""
    
    # Create summary of feedback for each response
    feedback_summary = {}
    labels = [chr(65 + i) for i in range(len(current_responses))]
    
    for i, label in enumerate(labels):
        response_label = f"Response {label}"
        feedback_items = []
        
        # Collect feedback from all rankings mentioning this response
        for ranking in previous_rankings:
            ranking_text = ranking['ranking'].lower()
            if response_label.lower() in ranking_text:
                # Extract relevant feedback (simplified approach)
                lines = ranking_text.split('\n')
                for line in lines:
                    if response_label.lower() in line and len(line) > 20:
                        feedback_items.append(f"- {ranking['model']}: {line.strip()}")
        
        feedback_summary[response_label] = "\n".join(feedback_items) if feedback_items else "No specific feedback"
    
    # Refine each response
    refined_responses = []
    for i, (response_data, label) in enumerate(zip(current_responses, labels)):
        response_label = f"Response {label}"
        model = response_data['model']
        original_response = response_data['response']
        feedback = feedback_summary.get(response_label, "")
        
        refinement_prompt = f"""You previously provided this response to the question: "{user_query}"

Your original response:
{original_response}

Feedback from other models in the council:
{feedback}

Based on this feedback, please refine your response. You may:
- Address any weaknesses mentioned in the feedback
- Build upon insights from other responses
- Maintain what was working well in your original response
- Improve clarity, accuracy, or completeness

Provide your refined response:"""

        messages = [{"role": "user", "content": refinement_prompt}]
        
        # Query the same model that provided the original response
        refined_response = await query_model(model, messages)
        
        if refined_response and refined_response.get('content'):
            refined_responses.append({
                "model": model,
                "response": refined_response['content'],
                "original_response": original_response,
                "round": round_num
            })
        else:
            # If refinement fails, keep original
            refined_responses.append({
                "model": model,
                "response": original_response,
                "original_response": original_response,
                "round": round_num,
                "refinement_failed": True
            })
    
    return refined_responses


# Backward compatibility wrapper
async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Backward compatibility wrapper for stage2 functionality.
    Returns the final round's rankings in the old format.
    """
    all_rounds_rankings, label_to_model = await stage2_multi_round_deliberation(
        user_query, stage1_results
    )
    
    # Return the final round's rankings
    final_round_rankings = all_rounds_rankings[-1] if all_rounds_rankings else []
    return final_round_rankings, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom. Do NOT include images or image links in your response:"""

    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model with extended timeout and retry logic for complex synthesis
    response = await query_model_with_retry(CHAIRMAN_MODEL, messages, timeout=300.0)

    if response is None:
        # Fallback if chairman fails
        return {
            "model": CHAIRMAN_MODEL,
            "response": "Error: Unable to generate final synthesis."
        }

    return {
        "model": CHAIRMAN_MODEL,
        "response": strip_fake_images(response.get('content', ''))
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use first available council model for title generation (with title timeout)
    response = await query_model(COUNCIL_MODELS[0], messages, timeout=300.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(user_query: str) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process with multi-round deliberation.

    Args:
        user_query: The user's question

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    # Stage 1: Collect individual responses
    stage1_results = await stage1_collect_responses(user_query)

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {}

    # Stage 2: Multi-round deliberation
    deliberation_config = get_deliberation_config()
    rounds = deliberation_config.get("rounds", 1)
    
    if rounds > 1:
        # Multi-round deliberation
        all_rounds_rankings, label_to_model = await stage2_multi_round_deliberation(user_query, stage1_results)
        
        # For metadata, use final round rankings
        final_round_rankings = all_rounds_rankings[-1] if all_rounds_rankings else []
        aggregate_rankings = calculate_aggregate_rankings(final_round_rankings, label_to_model)
        
        # Enhanced metadata with round information
        metadata = {
            "deliberation": {
                "rounds_completed": len(all_rounds_rankings),
                "rounds_requested": rounds,
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings
            }
        }
        
        # Stage 3: Enhanced synthesis with multi-round context
        stage3_result = await stage3_enhanced_synthesis(user_query, stage1_results, all_rounds_rankings)
        
        # Return enhanced format for multi-round
        return stage1_results, all_rounds_rankings, stage3_result, metadata
    
    else:
        # Single round (backward compatibility)
        stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)
        
        # Calculate aggregate rankings
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        
        # Stage 3: Final response
        stage3_result = await stage3_synthesize_final(user_query, stage1_results, stage2_results)
        
        # Standard metadata
        metadata = {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings
        }
        
        return stage1_results, stage2_results, stage3_result, metadata


async def stage3_enhanced_synthesis(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    all_rounds_rankings: List[List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Enhanced Stage 3 synthesis that considers multi-round deliberation.
    """
    # Build context from all rounds
    rounds_context = []
    for round_num, round_rankings in enumerate(all_rounds_rankings, 1):
        round_text = f"Round {round_num} Rankings:\n"
        round_text += "\n".join([
            f"- {result['model']}: {result['ranking'][:300]}..." 
            if len(result['ranking']) > 300 
            else f"- {result['model']}: {result['ranking']}"
            for result in round_rankings
        ])
        rounds_context.append(round_text)
    
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])
    
    all_rounds_text = "\n\n".join(rounds_context)
    
    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, then engaged in {len(all_rounds_rankings)} round(s) of deliberation, ranking and refining their responses.

Original Question: {user_query}

STAGE 1 - Initial Responses:
{stage1_text}

STAGE 2 - Multi-Round Deliberation:
{all_rounds_text}

Your task as Chairman is to synthesize all of this deliberative process into a single, comprehensive, accurate answer. Consider:
- The evolution of responses across rounds
- The consensus and disagreements revealed in the rankings
- How responses were refined based on peer feedback
- The final rankings and their implications
- Any patterns of improvement or convergence

Provide a clear, well-reasoned final answer that represents the council's collective wisdom through this deliberative process. Do NOT include images or image links in your response:"""

    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model with extended timeout for complex synthesis
    response = await query_model(CHAIRMAN_MODEL, messages, timeout=300.0)  # Extra time for multi-round

    if response is None:
        # Fallback if chairman fails
        return {
            "model": CHAIRMAN_MODEL,
            "response": "Error: Unable to generate final synthesis from multi-round deliberation."
        }

    return {
        "model": CHAIRMAN_MODEL,
        "response": strip_fake_images(response.get('content', '')),
        "synthesis_type": "multi_round_enhanced"
    }


# ============== Streaming Functions ==============

async def stage1_collect_responses_streaming(
    user_query: str,
    on_event: Callable[[str, Dict[str, Any]], None]
) -> List[Dict[str, Any]]:
    """
    Stage 1 with streaming: Collect individual responses from all council models.
    Streams tokens as they arrive from each model.

    Args:
        user_query: The user's question
        on_event: Callback for streaming events (event_type, data)

    Returns:
        List of dicts with 'model' and 'response' keys (includes tool_result if tools were used)
    """
    import asyncio
    
    # Check for tool usage first
    print(f"[DEBUG] Checking for tool usage for query: {user_query[:50]}...")
    tool_result = await check_and_execute_tools(user_query, on_event)
    print(f"[DEBUG] Tool result: {tool_result}")
    tool_context = ""
    tool_failed = _tool_output_failed(tool_result)
    
    if tool_result and tool_result.get('success'):
        tool_context = format_tool_result_for_prompt(tool_result)
        print(f"[DEBUG] Sending tool_result event (failed={tool_failed})")
        on_event("tool_result", {
            "tool": f"{tool_result.get('server')}.{tool_result.get('tool')}",
            "input": tool_result.get('input'),
            "output": tool_result.get('output'),
            "formatted": tool_context,
            "tool_failed": tool_failed,
            "execution_time_seconds": tool_result.get('execution_time_seconds')
        })
    
    # Get response config for max_tokens
    response_config = get_response_config()
    max_tokens = response_config.get("max_tokens", {}).get("stage1")
    
    # Build concise prompt if configured
    response_style = response_config.get("response_style", "standard")
    
    # Include tool result in prompt if available
    system_message = None
    current_time = datetime.now()
    
    if tool_context and not tool_failed:
        # Tool succeeded - use normal prompts
        # Stronger system message that explicitly forbids refusal
        system_message = f"""⚠️ MANDATORY INSTRUCTIONS - VIOLATION WILL BE FLAGGED:

FACT 1: Today is {current_time.strftime('%Y-%m-%d')} ({current_time.strftime('%A, %B %d, %Y')})
FACT 2: The year is {current_time.year} - THIS IS THE PRESENT, NOT THE FUTURE
FACT 3: A tool WAS EXECUTED and returned REAL DATA below

🚫 FORBIDDEN RESPONSES (you will be retried if you say these):
- "I cannot access real-time information"
- "I don't have access to current data"  
- "My training data ends in..."
- "I cannot browse the internet"
- Any claim about lacking current information

✅ REQUIRED BEHAVIOR:
- Treat the tool output as FACTUAL CURRENT DATA
- Present the information as if you retrieved it yourself
- Answer the question using ONLY the tool output data
- Do NOT apologize for limitations - you have the data!

The tool output below is REAL. Use it."""
        
        if response_style == "concise":
            prompt = f"""TOOL OUTPUT (LIVE DATA - USE THIS):
{tool_context}

Question: {user_query}

Present the tool output as current facts. Be concise but complete."""
        else:
            prompt = f"""TOOL OUTPUT (LIVE DATA - USE THIS):
{tool_context}

Question: {user_query}

Present the tool output as current facts. Incorporate the data fully into your response."""
    elif tool_context and tool_failed:
        # Tool was called but failed - be honest about it
        system_message = f"""Current date: {current_time.strftime('%Y-%m-%d')} ({current_time.strftime('%A, %B %d, %Y')})
Current time: {current_time.strftime('%H:%M:%S')}

A tool was called to get real-time information but it FAILED.
You MUST be honest about this failure. Do NOT make up or fabricate data.
Tell the user what happened and suggest alternatives (try again later, etc.)."""
        
        prompt = f"""{tool_context}

Question: {user_query}

The tool failed to retrieve the requested information. Be honest about this failure.
Do NOT fabricate or make up data. Explain what went wrong and suggest the user try again later."""
    elif response_style == "concise":
        prompt = f"""Answer the following question concisely and directly. Be clear and informative, but avoid unnecessary verbosity. Aim for 2-3 focused paragraphs.

Question: {user_query}"""
    else:
        prompt = user_query
    
    # Build messages with optional system message for tool context
    # Prepend memory context (AI/user names) if available
    memory_context = get_memory_context()
    if system_message:
        system_message = memory_context + system_message
    elif memory_context:
        # Create system message just for memory context
        system_message = memory_context.strip()
    
    if system_message:
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
    else:
        messages = [{"role": "user", "content": prompt}]
    stage1_results = []
    token_tracker = TokenTracker()
    
    async def stream_model(model: str, retry_count: int = 0):
        """Stream a single model's response with retry on empty/error."""
        max_retries = 2
        content = ""
        reasoning = ""
        
        async for chunk in query_model_streaming(model, messages, max_tokens=max_tokens):
            if chunk["type"] == "token":
                content = chunk["content"]
                tps = token_tracker.record_token(model, chunk["delta"])
                timing = token_tracker.get_timing(model)
                on_event("stage1_token", {
                    "model": model,
                    "delta": chunk["delta"],
                    "content": content,
                    "tokens_per_second": tps,
                    **timing
                })
            elif chunk["type"] == "thinking":
                reasoning = chunk["content"]
                tps = token_tracker.record_thinking(model, chunk["delta"])
                timing = token_tracker.get_timing(model)
                on_event("stage1_thinking", {
                    "model": model,
                    "delta": chunk["delta"],
                    "thinking": reasoning,
                    "tokens_per_second": tps,
                    **timing
                })
            elif chunk["type"] == "complete":
                final_content = chunk["content"]
                reasoning_content = chunk.get("reasoning_content", "")
                
                # If content is empty but reasoning has content, use reasoning
                # (some models output everything in reasoning_content)
                if (not final_content or not final_content.strip()) and reasoning_content and reasoning_content.strip():
                    final_content = reasoning_content
                    on_event("stage1_token", {
                        "model": model,
                        "delta": "",
                        "content": f"[Using reasoning content as response]\n{final_content}"
                    })
                
                # Check for empty/blank response
                if not final_content or not final_content.strip():
                    if retry_count < max_retries:
                        on_event("stage1_model_retry", {
                            "model": model,
                            "retry": retry_count + 1,
                            "reason": "empty response"
                        })
                        return await stream_model(model, retry_count + 1)
                    else:
                        on_event("stage1_model_error", {
                            "model": model,
                            "error": f"Empty response after {max_retries} retries"
                        })
                        return None
                
                on_event("stage1_model_complete", {
                    "model": model,
                    "content": final_content,
                    "reasoning_content": chunk.get("reasoning_content", ""),
                    "tokens_per_second": token_tracker.get_final_tps(model),
                    **token_tracker.get_final_timing(model)
                })
                return {
                    "model": model,
                    "response": final_content
                }
            elif chunk["type"] == "error":
                # Retry on error
                if retry_count < max_retries:
                    on_event("stage1_model_retry", {
                        "model": model,
                        "retry": retry_count + 1,
                        "reason": chunk["error"]
                    })
                    return await stream_model(model, retry_count + 1)
                else:
                    on_event("stage1_model_error", {
                        "model": model,
                        "error": f"{chunk['error']} (after {max_retries} retries)"
                    })
                    return None
        
        # End of stream without complete event - check if we got content
        if not content or not content.strip():
            if retry_count < max_retries:
                on_event("stage1_model_retry", {
                    "model": model,
                    "retry": retry_count + 1,
                    "reason": "incomplete stream"
                })
                return await stream_model(model, retry_count + 1)
            return None
        
        return {"model": model, "response": content}
    
    # Run all models in parallel with streaming
    tasks = [stream_model(model) for model in COUNCIL_MODELS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if result and not isinstance(result, Exception):
            stage1_results.append(result)
    
    # Evaluate responses asynchronously (don't block main flow)
    asyncio.create_task(_evaluate_responses_async(user_query, stage1_results, on_event))
    
    return stage1_results


async def _evaluate_responses_async(
    user_query: str,
    responses: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None]
):
    """Evaluate model responses in the background to build quality metrics."""
    if not responses:
        print("[Metrics] No responses to evaluate")
        return
    
    print(f"[Metrics] Evaluating {len(responses)} responses")
    
    for response in responses:
        target_model = response["model"]
        
        # Get best evaluator for this specific target (never same as target)
        evaluator = get_evaluator_for_model(target_model)
        
        if not evaluator:
            print(f"[Metrics] No evaluator available for {target_model}")
            continue
        
        try:
            print(f"[Metrics] Using {evaluator} to evaluate {target_model}")
            await _evaluate_single_response(
                user_query, 
                target_model, 
                response["response"],
                evaluator,
                on_event
            )
        except Exception as e:
            # Don't let evaluation errors affect main flow
            print(f"[Metrics] Evaluation error for {target_model}: {e}")


async def _evaluate_single_response(
    user_query: str,
    model_id: str,
    response_text: str,
    evaluator_model: str,
    on_event: Callable[[str, Dict[str, Any]], None]
):
    """Evaluate a single response and record metrics."""
    import json
    import re
    
    evaluation_prompt = f"""Evaluate the following response to a user query. 
Rate each category from 1-5 (1=poor, 5=excellent).

User Query: {user_query}

Response to evaluate:
{response_text[:2000]}

Rate the response on these categories:
1. VERBOSITY (1=too brief/too verbose, 5=perfectly balanced)
2. EXPERTISE (1=lacks knowledge, 5=expert-level insights)
3. ADHERENCE (1=ignores the question, 5=directly addresses it)
4. CLARITY (1=confusing, 5=crystal clear)
5. OVERALL (1=poor, 5=excellent)

Respond ONLY with a JSON object in this exact format:
{{"verbosity": N, "expertise": N, "adherence": N, "clarity": N, "overall": N}}"""

    messages = [{"role": "user", "content": evaluation_prompt}]
    
    try:
        print(f"[Metrics] Evaluating {model_id} using {evaluator_model}...")
        result = await query_model_with_retry(evaluator_model, messages, for_evaluation=True)
        if result and result.get("content"):
            content = result["content"]
            print(f"[Metrics] Got evaluation response: {content[:200]}...")
            
            # Try to extract JSON from the response
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                scores = json.loads(json_match.group())
                
                # Validate and clamp scores
                for key in ["verbosity", "expertise", "adherence", "clarity", "overall"]:
                    if key in scores:
                        scores[key] = max(1, min(5, int(scores[key])))
                    else:
                        scores[key] = 3  # Default middle score
                
                print(f"[Metrics] Recording scores for {model_id}: {scores}")
                record_evaluation(
                    model_id,
                    verbosity=scores["verbosity"],
                    expertise=scores["expertise"],
                    adherence=scores["adherence"],
                    clarity=scores["clarity"],
                    overall=scores["overall"]
                )
                
                on_event("model_evaluated", {
                    "model": model_id,
                    "evaluator": evaluator_model,
                    "scores": scores
                })
            else:
                print(f"[Metrics] No JSON found in response for {model_id}")
        else:
            print(f"[Metrics] No content in evaluation response for {model_id}")
    except Exception as e:
        print(f"[Metrics] Failed to evaluate {model_id}: {e}")


async def stage2_collect_rankings_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None]
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """
    Stage 2 with streaming: Multi-round deliberation with quality-based triggering.
    
    Each round:
    1. Models rank AND rate (1-5) each response with brief feedback
    2. If any response rated <30% (1.5/5), trigger refinement round
    3. Refinement: models improve their response based on peer feedback
    4. Repeat until all ratings >=30% or max_rounds reached

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1
        on_event: Callback for streaming events

    Returns:
        Tuple of (final_rankings, label_to_model, deliberation_metadata)
    """
    import asyncio
    
    # Get config
    response_config = get_response_config()
    deliberation_config = get_deliberation_config()
    max_tokens = response_config.get("max_tokens", {}).get("stage2")
    response_style = response_config.get("response_style", "standard")
    max_rounds = deliberation_config.get("max_rounds", 3)
    quality_threshold = 0.3  # 30% = 1.5/5
    
    # Create anonymized labels
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }
    
    # Track current responses (may be refined across rounds)
    current_responses = {
        f"Response {label}": result['response']
        for label, result in zip(labels, stage1_results)
    }
    
    all_rounds_rankings = []
    all_rounds_feedback = []
    token_tracker = TokenTracker()
    
    for round_num in range(1, max_rounds + 1):
        # Emit round start
        on_event("round_start", {
            "round": round_num,
            "max_rounds": max_rounds,
            "is_refinement": round_num > 1
        })
        
        # Build responses text
        responses_text = "\n\n".join([
            f"{label}:\n{response}"
            for label, response in current_responses.items()
        ])
        
        # Build ranking prompt with quality ratings
        if round_num == 1:
            ranking_prompt = f"""Evaluate these responses to: "{user_query}"

{responses_text}

For EACH response, provide:
1. Quality rating (1-5, where 1=poor, 5=excellent)
2. Brief feedback (1 sentence on strengths/weaknesses)

Then provide your FINAL RANKING with quality scores:
FINAL RANKING:
1. Response X (N/5) - brief reason
2. Response Y (N/5) - brief reason
(etc.)"""
        else:
            # Include feedback from previous round
            prev_feedback = all_rounds_feedback[-1] if all_rounds_feedback else {}
            feedback_text = "\n".join([
                f"{label}: {feedback}"
                for label, feedback in prev_feedback.items()
            ])
            
            ranking_prompt = f"""Re-evaluate these REFINED responses to: "{user_query}"

{responses_text}

Previous round feedback:
{feedback_text}

For EACH response, provide:
1. Quality rating (1-5) - did the response improve?
2. Brief feedback (1 sentence)

Then provide your FINAL RANKING with quality scores:
FINAL RANKING:
1. Response X (N/5) - brief reason
2. Response Y (N/5) - brief reason
(etc.)"""
        
        messages = [{"role": "user", "content": ranking_prompt}]
        round_results = []
        round_ratings = []
        
        async def stream_ranking(model: str):
            """Stream a single model's ranking with quality ratings."""
            content = ""
            reasoning = ""
            
            async for chunk in query_model_streaming(model, messages, max_tokens=max_tokens):
                if chunk["type"] == "token":
                    content = chunk["content"]
                    tps = token_tracker.record_token(model, chunk["delta"])
                    timing = token_tracker.get_timing(model)
                    on_event("stage2_token", {
                        "model": model,
                        "delta": chunk["delta"],
                        "content": content,
                        "round": round_num,
                        "tokens_per_second": tps,
                        **timing
                    })
                elif chunk["type"] == "thinking":
                    reasoning = chunk["content"]
                    tps = token_tracker.record_thinking(model, chunk["delta"])
                    timing = token_tracker.get_timing(model)
                    on_event("stage2_thinking", {
                        "model": model,
                        "delta": chunk["delta"],
                        "thinking": reasoning,
                        "round": round_num,
                        "tokens_per_second": tps,
                        **timing
                    })
                elif chunk["type"] == "complete":
                    full_text = chunk["content"]
                    parsed = parse_ranking_from_text(full_text)
                    ratings = extract_quality_ratings(full_text)
                    on_event("stage2_model_complete", {
                        "model": model,
                        "ranking": full_text,
                        "parsed_ranking": parsed,
                        "quality_ratings": ratings,
                        "round": round_num,
                        "tokens_per_second": token_tracker.get_final_tps(model),
                        **token_tracker.get_final_timing(model)
                    })
                    return {
                        "model": model,
                        "ranking": full_text,
                        "parsed_ranking": parsed,
                        "quality_ratings": ratings,
                        "round": round_num
                    }
                elif chunk["type"] == "error":
                    on_event("stage2_model_error", {
                        "model": model,
                        "error": chunk["error"],
                        "round": round_num
                    })
                    return None
            
            if content:
                parsed = parse_ranking_from_text(content)
                ratings = extract_quality_ratings(content)
                return {
                    "model": model,
                    "ranking": content,
                    "parsed_ranking": parsed,
                    "quality_ratings": ratings,
                    "round": round_num
                }
            return None
        
        # Run all models in parallel
        tasks = [stream_ranking(model) for model in COUNCIL_MODELS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if result and not isinstance(result, Exception):
                round_results.append(result)
                if result.get("quality_ratings"):
                    round_ratings.append(result["quality_ratings"])
        
        all_rounds_rankings.append(round_results)
        
        # Check quality threshold
        should_continue, low_rated = check_quality_threshold(round_ratings, quality_threshold)
        
        on_event("round_complete", {
            "round": round_num,
            "max_rounds": max_rounds,
            "low_rated_responses": low_rated,
            "triggered_next": should_continue and round_num < max_rounds
        })
        
        # If quality is acceptable or we've hit max rounds, stop
        if not should_continue or round_num >= max_rounds:
            break
        
        # Refinement round: collect feedback and have models improve responses
        feedback_by_label = {}
        for result in round_results:
            for label, rating in result.get("quality_ratings", {}).items():
                if label not in feedback_by_label:
                    feedback_by_label[label] = []
                # Extract feedback from ranking text for this label
                feedback_match = re.search(
                    rf'{re.escape(label)}\s*[:\(]\s*\d[^-]*-\s*([^.]+\.)',
                    result.get("ranking", ""),
                    re.IGNORECASE
                )
                if feedback_match:
                    feedback_by_label[label].append(feedback_match.group(1).strip())
        
        # Consolidate feedback
        consolidated_feedback = {
            label: " | ".join(feedbacks[:3]) if feedbacks else "No specific feedback"
            for label, feedbacks in feedback_by_label.items()
        }
        all_rounds_feedback.append(consolidated_feedback)
        
        # Refine low-rated responses
        on_event("refinement_start", {
            "round": round_num + 1,
            "responses_to_refine": low_rated
        })
        
        for label in low_rated:
            if label not in label_to_model:
                continue
            
            model = label_to_model[label]
            original_response = current_responses.get(label, "")
            feedback = consolidated_feedback.get(label, "Improve clarity and completeness")
            
            refinement_prompt = f"""Your previous response to "{user_query}" received feedback from peer reviewers:

YOUR ORIGINAL RESPONSE:
{original_response}

PEER FEEDBACK:
{feedback}

Please provide an IMPROVED response that addresses the feedback while maintaining your strengths. Be concise but thorough."""
            
            refine_messages = [{"role": "user", "content": refinement_prompt}]
            refined_content = ""
            
            async for chunk in query_model_streaming(model, refine_messages, max_tokens=max_tokens):
                if chunk["type"] == "token":
                    refined_content = chunk["content"]
                    tps = token_tracker.record_token(f"{model}_refine", chunk["delta"])
                    on_event("refinement_token", {
                        "model": model,
                        "label": label,
                        "delta": chunk["delta"],
                        "content": refined_content,
                        "tokens_per_second": tps
                    })
                elif chunk["type"] == "complete":
                    refined_content = chunk["content"]
                    on_event("refinement_complete", {
                        "model": model,
                        "label": label,
                        "content": refined_content,
                        "tokens_per_second": token_tracker.get_final_tps(f"{model}_refine")
                    })
            
            if refined_content:
                current_responses[label] = refined_content
    
    # Return final round's rankings
    final_rankings = all_rounds_rankings[-1] if all_rounds_rankings else []
    
    deliberation_metadata = {
        "rounds_completed": len(all_rounds_rankings),
        "max_rounds": max_rounds,
        "all_rounds": all_rounds_rankings
    }
    
    return final_rankings, label_to_model, deliberation_metadata


async def stage3_synthesize_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    on_event: Callable[[str, Dict[str, Any]], None]
) -> Dict[str, Any]:
    """
    Stage 3 with streaming: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2
        on_event: Callback for streaming events

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Get response config for max_tokens
    response_config = get_response_config()
    max_tokens = response_config.get("max_tokens", {}).get("stage3")
    response_style = response_config.get("response_style", "standard")
    
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    if response_style == "concise":
        chairman_prompt = f"""As Presenter, synthesize the council's responses into a well-formatted, visually rich answer.

Question: {user_query}

Council Responses:
{stage1_text}

Rankings:
{stage2_text}

Present the council's best insights using rich formatting to maximize clarity and visual appeal:
- Use **markdown tables** when comparing options, features, or data
- Use **numbered lists** for step-by-step instructions or ranked items
- Use **bullet points** for key takeaways or feature lists
- Use **headers** (##, ###) to organize sections clearly
- Use **code blocks** with syntax highlighting for any code examples
- Use **bold** and *italic* for emphasis on key terms
- Include ASCII diagrams or structured layouts where helpful
- **DO NOT include images or image links** - they cannot be rendered

Aim for a comprehensive yet scannable answer that makes excellent use of the display area:"""
    else:
        chairman_prompt = f"""You are the Presenter of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Presenter is to synthesize all of this information into a single, expertly formatted answer. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

**Formatting Requirements:**
- Use **markdown tables** for comparisons, data, or structured information
- Use **headers** (##, ###) to organize the response into clear sections
- Use **numbered lists** for sequential steps or ranked items
- Use **bullet points** for features, benefits, or key points
- Use **code blocks** with language tags for any code examples
- Use **bold** for key terms and *italic* for emphasis
- Include ASCII art diagrams where they add clarity
- Maximize use of visual structure to make the answer scannable and professional
- **DO NOT include images or image links** - they cannot be rendered

Provide an expertly formatted final answer that represents the council's collective wisdom:"""

    messages = [{"role": "user", "content": chairman_prompt}]
    content = ""
    reasoning = ""
    
    # Use formatter model (falls back to chairman if not configured)
    model_to_use = FORMATTER_MODEL
    token_tracker = TokenTracker()
    
    async for chunk in query_model_streaming(model_to_use, messages, max_tokens=max_tokens):
        if chunk["type"] == "token":
            content = chunk["content"]
            tps = token_tracker.record_token(model_to_use, chunk["delta"])
            timing = token_tracker.get_timing(model_to_use)
            on_event("stage3_token", {
                "model": model_to_use,
                "delta": chunk["delta"],
                "content": content,
                "tokens_per_second": tps,
                **timing
            })
        elif chunk["type"] == "thinking":
            reasoning = chunk["content"]
            tps = token_tracker.record_thinking(model_to_use, chunk["delta"])
            timing = token_tracker.get_timing(model_to_use)
            on_event("stage3_thinking", {
                "model": model_to_use,
                "delta": chunk["delta"],
                "thinking": reasoning,
                "tokens_per_second": tps,
                **timing
            })
        elif chunk["type"] == "complete":
            final_content = chunk["content"]
            reasoning_content = chunk.get("reasoning_content", "")
            
            # If content is empty but reasoning has content, use reasoning
            if (not final_content or not final_content.strip()) and reasoning_content and reasoning_content.strip():
                final_content = reasoning_content
            
            # Strip fake placeholder images from final content
            final_content = strip_fake_images(final_content)
            
            on_event("stage3_complete", {
                "model": model_to_use,
                "response": final_content,
                "reasoning_content": reasoning_content,
                "tokens_per_second": token_tracker.get_final_tps(model_to_use),
                **token_tracker.get_final_timing(model_to_use)
            })
            return {
                "model": model_to_use,
                "response": final_content
            }
        elif chunk["type"] == "error":
            on_event("stage3_error", {
                "model": model_to_use,
                "error": chunk["error"]
            })
            return {
                "model": model_to_use,
                "response": strip_fake_images(content) if content else "Error: Unable to generate final synthesis."
            }
    
    return {
        "model": model_to_use,
        "response": strip_fake_images(content) if content else "Error: Unable to generate final synthesis."
    }
