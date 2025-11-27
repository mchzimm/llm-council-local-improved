"""LM Studio API client for making local LLM requests."""

import httpx
import asyncio
import time
import json
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from .config_loader import get_model_connection_info, load_config


async def query_model_with_retry(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
    for_title: bool = False,
    for_evaluation: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Query a model with retry logic and proper timeout handling.

    Args:
        model: LM Studio model identifier
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds (uses config default if None)
        max_retries: Maximum retry attempts (uses config default if None)
        for_title: Whether this is for title generation (affects timeout)
        for_evaluation: Whether this is for model evaluation (shorter timeout)

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    config = load_config()
    timeout_config = config.get('timeout_config', {})
    
    # Determine timeout based on use case
    if timeout is None:
        if for_evaluation:
            timeout = timeout_config.get('evaluation_timeout', 60)
        elif for_title:
            timeout = timeout_config.get('title_generation_timeout', 300)
        else:
            # Default for council/chairman queries - 5 minutes for reasoning models
            timeout = timeout_config.get('default_timeout', 300)
    
    # Determine max retries
    if max_retries is None:
        max_retries = timeout_config.get('max_retries', 2)
    
    backoff_factor = timeout_config.get('retry_backoff_factor', 2)
    connection_timeout = timeout_config.get('connection_timeout', 10)
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            return await query_model(
                model=model,
                messages=messages,
                timeout=timeout,
                connection_timeout=connection_timeout
            )
        
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException) as e:
            last_error = e
            if attempt < max_retries:
                wait_time = backoff_factor ** attempt
                print(f"Timeout on attempt {attempt + 1} for model {model}, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print(f"Model {model} failed after {max_retries + 1} attempts due to timeout: {e}")
        
        except Exception as e:
            print(f"Non-timeout error querying model {model}: {e}")
            last_error = e
            # Don't retry on non-timeout errors
            break
    
    return None


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    connection_timeout: Optional[float] = None,
    max_tokens: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via LM Studio API.

    Args:
        model: LM Studio model identifier (e.g., "microsoft/phi-4-mini-reasoning")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds (uses config default if None)
        connection_timeout: Connection timeout in seconds (uses config default if None)
        max_tokens: Maximum tokens to generate (optional, uses model default if None)

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    # Load timeout config
    config = load_config()
    timeout_cfg = config.get('timeout_config', {})
    
    if timeout is None:
        timeout = timeout_cfg.get('default_timeout', 600)
    if connection_timeout is None:
        connection_timeout = timeout_cfg.get('connection_timeout', 30)
    
    # Get connection info for this specific model
    connection_info = get_model_connection_info(model)
    api_endpoint = connection_info["api_endpoint"]
    api_key = connection_info["api_key"]
    
    headers = {
        "Content-Type": "application/json",
    }
    
    # Add API key if provided
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
    }
    
    # Add max_tokens if specified
    if max_tokens:
        payload["max_tokens"] = max_tokens

    try:
        # Use separate timeouts for connection and read
        timeout_config = httpx.Timeout(
            connect=connection_timeout,
            read=timeout,
            write=timeout,
            pool=timeout
        )
        
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(
                api_endpoint,
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            message = data['choices'][0]['message']

            # For thinking/reasoning models, extract content from reasoning_content if main content is empty
            content = message.get('content')
            reasoning_content = message.get('reasoning_content', '')
            
            # If content is empty or None, try to use reasoning_content for thinking models
            if not content and reasoning_content:
                # Extract the final answer from reasoning content if available
                # For title generation, we want the complete reasoning as it often contains the title
                content = reasoning_content

            return {
                'content': content,
                'reasoning_content': reasoning_content,
                'reasoning_details': message.get('reasoning_details')
            }

    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException) as e:
        # Re-raise timeout exceptions for retry handling
        raise e
    except Exception as e:
        print(f"Error querying model {model} at {api_endpoint}: {e}")
        # Print more detailed error info for debugging
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel via LM Studio.

    Args:
        models: List of LM Studio model identifiers
        messages: List of message dicts to send to each model
        timeout: Request timeout in seconds (uses config default if None)

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    # Create tasks for all models with retry logic
    tasks = [query_model_with_retry(model, messages, timeout=timeout) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # Map models to their responses, handle exceptions
    result = {}
    for model, response in zip(models, responses):
        if isinstance(response, Exception):
            print(f"Exception for model {model}: {response}")
            result[model] = None
        else:
            result[model] = response
    
    return result


async def query_model_streaming(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    connection_timeout: Optional[float] = None,
    on_token: Optional[Callable[[str, str, Optional[str]], None]] = None,
    max_tokens: Optional[int] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Query a model with streaming enabled, yielding tokens as they arrive.

    Args:
        model: LM Studio model identifier
        messages: List of message dicts with 'role' and 'content'
        timeout: Per-chunk read timeout in seconds (uses config default if None)
        connection_timeout: Connection timeout in seconds (uses config default if None)
        on_token: Optional callback (token, token_type, content_so_far) called for each token
        max_tokens: Maximum tokens to generate (optional)

    Yields:
        Dict with 'type' ('token', 'thinking', 'complete') and 'content' or 'delta'
    """
    # Load timeout config
    config = load_config()
    timeout_config = config.get('timeout_config', {})
    
    if timeout is None:
        timeout = timeout_config.get('streaming_chunk_timeout', 600)
    if connection_timeout is None:
        connection_timeout = timeout_config.get('connection_timeout', 30)
    
    connection_info = get_model_connection_info(model)
    api_endpoint = connection_info["api_endpoint"]
    api_key = connection_info["api_key"]
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    
    if max_tokens:
        payload["max_tokens"] = max_tokens

    content_buffer = ""
    reasoning_buffer = ""

    try:
        # For streaming, read timeout is per-chunk, not total
        # Use longer read timeout to allow for model thinking between chunks
        timeout_config = httpx.Timeout(
            connect=connection_timeout,
            read=timeout,  # Per-chunk timeout - needs to be long for reasoning models
            write=30.0,
            pool=30.0
        )
        
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            async with client.stream(
                "POST",
                api_endpoint,
                headers=headers,
                json=payload
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        
                        # Check for reasoning content (thinking models)
                        reasoning_delta = delta.get("reasoning_content", "")
                        if reasoning_delta:
                            reasoning_buffer += reasoning_delta
                            if on_token:
                                on_token(reasoning_delta, "thinking", reasoning_buffer)
                            yield {
                                "type": "thinking",
                                "delta": reasoning_delta,
                                "content": reasoning_buffer
                            }
                        
                        # Regular content
                        content_delta = delta.get("content", "")
                        if content_delta:
                            content_buffer += content_delta
                            if on_token:
                                on_token(content_delta, "token", content_buffer)
                            yield {
                                "type": "token",
                                "delta": content_delta,
                                "content": content_buffer
                            }
                    
                    except json.JSONDecodeError:
                        continue
        
        # Yield final complete message
        yield {
            "type": "complete",
            "content": content_buffer,
            "reasoning_content": reasoning_buffer
        }

    except Exception as e:
        print(f"Streaming error for model {model}: {e}")
        yield {
            "type": "error",
            "error": str(e),
            "content": content_buffer,
            "reasoning_content": reasoning_buffer
        }