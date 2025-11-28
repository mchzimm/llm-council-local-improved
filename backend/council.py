"""3-stage LLM Council orchestration with multi-round deliberation."""

import time
import re
import json
from datetime import datetime
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
- "chat": Greetings, acknowledgments, small talk, simple yes/no questions about the AI itself
- "deliberation": Opinions, comparisons, feedback requests, creative work, complex analysis, subjective questions, anything requiring multiple perspectives

Examples:
- "What is 3+5?" → factual
- "Hello, how are you?" → chat  
- "Which is better, Python or JavaScript?" → deliberation
- "Review my code" → deliberation
- "What's the capital of France?" → factual
- "Can you help me?" → chat
- "What do you think about AI?" → deliberation"""

    messages = [{"role": "user", "content": classification_prompt.format(query=user_query)}]
    tool_model = get_tool_calling_model()
    
    if on_event:
        on_event("classification_start", {"model": tool_model})
    
    try:
        response = await query_model_with_retry(tool_model, messages, timeout=30.0, max_retries=1)
        
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
    on_event: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Generate a direct response from the chairman without council deliberation.
    Used for factual questions and casual chat.
    If a formatter model is configured and different from chairman, it formats the final response.
    
    Args:
        user_query: The user's question
        tool_result: Optional tool execution result
        on_event: Optional callback for streaming events
        
    Returns:
        Dict with 'model', 'response', 'type'
    """
    # Include current date/time context
    current_time = datetime.now()
    time_context = f"Today's date: {current_time.strftime('%B %d, %Y')} | Current time: {current_time.strftime('%H:%M')}"
    
    # Build prompt based on whether tools were used
    if tool_result and tool_result.get('success'):
        tool_context = format_tool_result_for_prompt(tool_result)
        prompt = f"""IMPORTANT CONTEXT:
- {time_context}
- A real-time tool was executed to fetch CURRENT, LIVE data for this query
- The tool output below contains UP-TO-DATE information retrieved just now
- DO NOT claim you "lack access to current information" - you HAVE it via the tool output

{tool_context}

Question: {user_query}

Instructions:
1. The tool output above is CURRENT and AUTHORITATIVE - use it directly
2. Present the information as current facts (because they ARE current)
3. Provide a clear, direct answer. Be concise but complete."""
    else:
        prompt = f"""Answer this question directly and concisely.

Question: {user_query}
({time_context})

Provide a helpful, accurate answer. Be concise but complete."""
    
    messages = [{"role": "user", "content": prompt}]
    content = ""
    reasoning = ""
    token_tracker = TokenTracker()
    
    if on_event:
        on_event("direct_response_start", {"model": CHAIRMAN_MODEL})
    
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


# Keywords that strongly indicate websearch is required
WEBSEARCH_KEYWORDS = ['news', 'current events', 'latest', 'recent', 'happening', 
                      "today's", 'this week', 'trending', 'breaking', 'headlines']


def _requires_websearch(query: str) -> bool:
    """Check if query contains keywords that strongly suggest websearch is needed."""
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in WEBSEARCH_KEYWORDS)


async def _phase1_analyze_query(user_query: str, detailed_tool_info: str) -> Optional[Dict[str, Any]]:
    """
    Phase 1: Analyze the query to determine if MCP tools are needed.
    
    Returns:
        Dict with 'needs_tool', 'tool_name', 'server', 'reasoning' or None on failure
    """
    # Fast path: if query contains news/current events keywords, short-circuit to websearch
    if _requires_websearch(user_query):
        print(f"[MCP Phase 1] Keywords detected, using websearch directly")
        return {
            "needs_tool": True,
            "tool_name": "websearch.search",
            "server": "websearch",
            "reasoning": "Query about current events/news requires websearch"
        }
    
    # Include current date/time context so model knows the actual time
    current_time = datetime.now()
    time_context = f"""CRITICAL CONTEXT - READ CAREFULLY:
- Today's date is: {current_time.strftime('%Y-%m-%d')} ({current_time.strftime('%A, %B %d, %Y')})
- Current time: {current_time.strftime('%H:%M:%S')} (local timezone)
- Year: {current_time.year}

IMPORTANT: You HAVE ACCESS to external tools including websearch!
- Do NOT say you "lack real-time access" or "cannot access current information"
- For ANY question about news, current events, or real-time information → USE websearch.search
- For date/time questions → USE system-date-time.get-system-date-time"""

    analysis_prompt = f"""You are a tool router that decides which MCP tool to use for a query.

{time_context}

{detailed_tool_info}

USER QUERY: {user_query}

DECISION RULES (follow strictly):
1. News/current events/what's happening → websearch.search (ALWAYS)
2. Math calculations → calculator tools
3. Date/time questions → system-date-time.get-system-date-time
4. Location questions → system-geo-location.get-system-geo-location
5. Factual questions (capitals, definitions) → no tool needed

Respond with ONLY a JSON object:
- Tool needed: {{"needs_tool": true, "tool_name": "server.tool_name", "server": "server_name", "reasoning": "brief"}}
- No tool: {{"needs_tool": false, "reasoning": "brief"}}

JSON response:"""

    messages = [{"role": "user", "content": analysis_prompt}]
    tool_model = get_tool_calling_model()
    
    print(f"[MCP Phase 1] Analyzing query with {tool_model}...")
    response = await query_model_with_retry(tool_model, messages, timeout=None, max_retries=1)
    
    if not response or not response.get('content'):
        print("[MCP Phase 1] No response from model")
        return None
    
    content = response['content'].strip()
    print(f"[MCP Phase 1] Analysis response: {content[:300]}...")
    
    return _extract_json_from_response(content)


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
    execution_prompt = f"""You need to generate a tool call to answer a user query.

{detailed_tool_info}

USER QUERY: {user_query}

SELECTED TOOL: {tool_name}

TASK: Generate the exact tool call with the correct arguments based on the user's query.

For the tool "{tool_name}", create a JSON object with:
{{"tool": "{tool_name}", "arguments": {{...parameters with correct values...}}}}

Important:
- Use the exact parameter names from the tool definition
- Provide appropriate values based on the user's query
- For math operations, extract the numbers from the query
- For web searches, formulate a good search query

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


async def check_and_execute_tools(user_query: str, on_event: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
    """
    Intelligent two-phase MCP tool execution.
    
    Phase 1: Analyze the query to determine if MCP tools are needed
    Phase 2: Generate and execute the tool call if needed
    
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
    if on_event:
        on_event("tool_call_start", {
            "tool": final_tool_name,
            "arguments": arguments
        })
    
    try:
        result = await registry.call_tool(final_tool_name, arguments)
        
        if on_event:
            on_event("tool_call_complete", {
                "tool": final_tool_name,
                "arguments": arguments,
                "result": result
            })
        
        print(f"[MCP] Tool execution complete: success={result.get('success', False)}")
        return result
        
    except Exception as e:
        print(f"[MCP] Tool execution failed: {e}")
        if on_event:
            on_event("tool_call_complete", {
                "tool": final_tool_name,
                "arguments": arguments,
                "result": {"success": False, "error": str(e)}
            })
        return None


def format_tool_result_for_prompt(tool_result: Dict[str, Any]) -> str:
    """Format tool execution result for inclusion in prompts."""
    if not tool_result or not tool_result.get('success'):
        return ""
    
    server = tool_result.get('server', 'unknown')
    tool = tool_result.get('tool', 'unknown')
    input_args = tool_result.get('input', {})
    output = tool_result.get('output', {})
    
    # Extract the actual result from MCP response
    if isinstance(output, dict) and 'content' in output:
        content = output['content']
        if isinstance(content, list) and len(content) > 0:
            text_content = content[0].get('text', '')
            try:
                result_data = json.loads(text_content)
                output = result_data
            except:
                output = text_content
    
    return f"""
🔧 **MCP Tool Used**: {server}.{tool}
   **Input**: {json.dumps(input_args)}
   **Output**: {json.dumps(output) if isinstance(output, dict) else output}
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

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

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
        "response": response.get('content', '')
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

Provide a clear, well-reasoned final answer that represents the council's collective wisdom through this deliberative process:"""

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
        "response": response.get('content', ''),
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
    if tool_result and tool_result.get('success'):
        tool_context = format_tool_result_for_prompt(tool_result)
        print(f"[DEBUG] Sending tool_result event")
        on_event("tool_result", {
            "tool": f"{tool_result.get('server')}.{tool_result.get('tool')}",
            "input": tool_result.get('input'),
            "output": tool_result.get('output'),
            "formatted": tool_context
        })
    
    # Get response config for max_tokens
    response_config = get_response_config()
    max_tokens = response_config.get("max_tokens", {}).get("stage1")
    
    # Build concise prompt if configured
    response_style = response_config.get("response_style", "standard")
    
    # Include tool result in prompt if available
    if tool_context:
        # Get current date/time to provide context
        current_time = datetime.now()
        time_context = f"Today's date: {current_time.strftime('%B %d, %Y')} | Current time: {current_time.strftime('%H:%M')}"
        
        if response_style == "concise":
            prompt = f"""IMPORTANT CONTEXT:
- {time_context}
- A real-time tool was executed to fetch CURRENT, LIVE data for this query
- The tool output below contains UP-TO-DATE information retrieved just now
- DO NOT claim you "lack access to current information" - you HAVE it via the tool output

{tool_context}

Question: {user_query}

Instructions:
1. The tool output above is CURRENT and AUTHORITATIVE - use it directly
2. Present the information as current facts (because they ARE current)
3. Be concise but complete"""
        else:
            prompt = f"""IMPORTANT CONTEXT:
- {time_context}
- A real-time tool was executed to fetch CURRENT, LIVE data for this query
- The tool output below contains UP-TO-DATE information retrieved just now
- DO NOT claim you "lack access to current information" - you HAVE it via the tool output

{tool_context}

Question: {user_query}

Instructions:
1. The tool output above is CURRENT and AUTHORITATIVE - use it directly
2. Present the information as current facts (because they ARE current)
3. Incorporate the tool output fully into your response"""
    elif response_style == "concise":
        prompt = f"""Answer the following question concisely and directly. Be clear and informative, but avoid unnecessary verbosity. Aim for 2-3 focused paragraphs.

Question: {user_query}"""
    else:
        prompt = user_query
    
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
                "response": content if content else "Error: Unable to generate final synthesis."
            }
    
    return {
        "model": model_to_use,
        "response": content if content else "Error: Unable to generate final synthesis."
    }
