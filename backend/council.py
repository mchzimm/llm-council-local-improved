"""3-stage LLM Council orchestration with multi-round deliberation."""

import time
from typing import List, Dict, Any, Tuple, AsyncGenerator, Callable, Optional
from .lmstudio import query_models_parallel, query_model_with_retry, query_model_streaming
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL, FORMATTER_MODEL
from .config_loader import get_deliberation_rounds, get_deliberation_config, get_response_config
from .model_metrics import (
    record_query_result, 
    record_evaluation, 
    get_evaluator_for_model,
    get_valid_models
)


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

    # Use first available council model for title generation
    response = await query_model(COUNCIL_MODELS[0], messages, timeout=30.0)

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
        List of dicts with 'model' and 'response' keys
    """
    import asyncio
    
    # Get response config for max_tokens
    response_config = get_response_config()
    max_tokens = response_config.get("max_tokens", {}).get("stage1")
    
    # Build concise prompt if configured
    response_style = response_config.get("response_style", "standard")
    if response_style == "concise":
        prompt = f"""Answer the following question concisely and directly. Be clear and informative, but avoid unnecessary verbosity. Aim for 2-3 focused paragraphs.

Question: {user_query}"""
    else:
        prompt = user_query
    
    messages = [{"role": "user", "content": prompt}]
    stage1_results = []
    
    async def stream_model(model: str, retry_count: int = 0):
        """Stream a single model's response with retry on empty/error."""
        max_retries = 2
        content = ""
        reasoning = ""
        
        async for chunk in query_model_streaming(model, messages, max_tokens=max_tokens):
            if chunk["type"] == "token":
                content = chunk["content"]
                on_event("stage1_token", {
                    "model": model,
                    "delta": chunk["delta"],
                    "content": content
                })
            elif chunk["type"] == "thinking":
                reasoning = chunk["content"]
                on_event("stage1_thinking", {
                    "model": model,
                    "delta": chunk["delta"],
                    "thinking": reasoning
                })
            elif chunk["type"] == "complete":
                final_content = chunk["content"]
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
                    "reasoning_content": chunk.get("reasoning_content", "")
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
        result = await query_model_with_retry(evaluator_model, messages, timeout=30.0)
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
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2 with streaming: Collect rankings from all council models.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1
        on_event: Callback for streaming events

    Returns:
        Tuple of (rankings_list, label_to_model mapping)
    """
    import asyncio
    
    # Get response config for max_tokens
    response_config = get_response_config()
    max_tokens = response_config.get("max_tokens", {}).get("stage2")
    response_style = response_config.get("response_style", "standard")
    
    # Create anonymized labels
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }
    
    # Build ranking prompt - concise version if configured
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])
    
    if response_style == "concise":
        ranking_prompt = f"""Evaluate these responses to: "{user_query}"

{responses_text}

Briefly assess each response (1-2 sentences each), then provide:

FINAL RANKING:
1. Response X
2. Response Y
(etc.)"""
    else:
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

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]
    stage2_results = []
    
    async def stream_ranking(model: str):
        """Stream a single model's ranking."""
        content = ""
        reasoning = ""
        
        async for chunk in query_model_streaming(model, messages, max_tokens=max_tokens):
            if chunk["type"] == "token":
                content = chunk["content"]
                on_event("stage2_token", {
                    "model": model,
                    "delta": chunk["delta"],
                    "content": content
                })
            elif chunk["type"] == "thinking":
                reasoning = chunk["content"]
                on_event("stage2_thinking", {
                    "model": model,
                    "delta": chunk["delta"],
                    "thinking": reasoning
                })
            elif chunk["type"] == "complete":
                full_text = chunk["content"]
                parsed = parse_ranking_from_text(full_text)
                on_event("stage2_model_complete", {
                    "model": model,
                    "ranking": full_text,
                    "parsed_ranking": parsed
                })
                return {
                    "model": model,
                    "ranking": full_text,
                    "parsed_ranking": parsed
                }
            elif chunk["type"] == "error":
                on_event("stage2_model_error", {
                    "model": model,
                    "error": chunk["error"]
                })
                return None
        
        if content:
            parsed = parse_ranking_from_text(content)
            return {"model": model, "ranking": content, "parsed_ranking": parsed}
        return None
    
    tasks = [stream_ranking(model) for model in COUNCIL_MODELS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if result and not isinstance(result, Exception):
            stage2_results.append(result)
    
    return stage2_results, label_to_model


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
    
    async for chunk in query_model_streaming(model_to_use, messages, max_tokens=max_tokens):
        if chunk["type"] == "token":
            content = chunk["content"]
            on_event("stage3_token", {
                "model": model_to_use,
                "delta": chunk["delta"],
                "content": content
            })
        elif chunk["type"] == "thinking":
            reasoning = chunk["content"]
            on_event("stage3_thinking", {
                "model": model_to_use,
                "delta": chunk["delta"],
                "thinking": reasoning
            })
        elif chunk["type"] == "complete":
            on_event("stage3_complete", {
                "model": model_to_use,
                "response": chunk["content"],
                "reasoning_content": chunk.get("reasoning_content", "")
            })
            return {
                "model": model_to_use,
                "response": chunk["content"]
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
