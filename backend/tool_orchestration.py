"""
Multi-tool orchestration for complex queries requiring multiple tool calls.

Uses a planning phase to decompose queries into steps, then executes tools
sequentially, passing results between steps.
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
import uuid

from .mcp.registry import get_mcp_registry
from .lmstudio import query_model
from .config_loader import get_chairman_model


async def needs_multi_tool_orchestration(user_query: str) -> bool:
    """
    Determine if a query requires multi-tool orchestration.
    
    Patterns that suggest multi-step execution:
    - Time-relative queries (yesterday, last week, tomorrow, last Tuesday)
    - Queries combining location + time + data (weather, events)
    - Complex calculations requiring multiple inputs
    """
    query_lower = user_query.lower()
    
    # Day-of-week patterns (last tuesday, next monday, etc.)
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in day_names:
        if f"last {day}" in query_lower or f"next {day}" in query_lower or f"this {day}" in query_lower:
            if any(word in query_lower for word in ["weather", "forecast", "temperature", "rain"]):
                return True
    
    # Time-relative patterns that need date calculation + another tool
    time_relative_patterns = [
        ("yesterday", ["weather", "news", "events", "happened"]),
        ("last week", ["weather", "news", "events", "happened"]),
        ("tomorrow", ["weather", "forecast"]),
        ("next week", ["weather", "forecast"]),
        ("last month", ["weather", "news", "events"]),
    ]
    
    for time_pattern, context_words in time_relative_patterns:
        if time_pattern in query_lower:
            if any(word in query_lower for word in context_words):
                return True
    
    # Queries that need location + time + data
    multi_context_patterns = [
        ("weather", "here"),  # Need location + current time + weather
        ("weather", "now"),
        ("weather", "in"),  # Weather in a specific location
        ("time", "in"),  # Time in different location
    ]
    
    for p1, p2 in multi_context_patterns:
        if p1 in query_lower and p2 in query_lower:
            return True
    
    return False


async def plan_tool_execution(user_query: str, available_tools: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create an execution plan for the query using LLM.
    
    Returns a list of steps, each with:
    - step_number: int
    - description: str
    - tool: str (tool name)
    - depends_on: List[int] (step numbers this depends on)
    - parameters: Dict (parameters for the tool, may include $step_N references)
    """
    chairman = get_chairman_model()
    
    # Format tool list for prompt - available_tools contains MCPTool objects
    tool_descriptions = []
    for tool_name, tool_info in available_tools.items():
        # MCPTool has attributes: name, description, input_schema, server_name
        desc = getattr(tool_info, 'description', 'No description')
        input_schema = getattr(tool_info, 'input_schema', {})
        params = input_schema.get('properties', {}) if isinstance(input_schema, dict) else {}
        param_list = list(params.keys())[:5]  # First 5 params
        tool_descriptions.append(f"- {tool_name}: {desc} (params: {', '.join(param_list)})")
    
    tools_text = "\n".join(tool_descriptions[:15])  # Limit to avoid token overflow
    
    prompt = f"""You are a tool orchestration planner. Given a user query and available tools, create an execution plan.

USER QUERY: "{user_query}"

AVAILABLE TOOLS:
{tools_text}

Create a JSON execution plan with steps to answer the query. Each step should use one tool.

Rules:
1. Use the minimum number of steps necessary
2. Each step can reference results from previous steps using $step_N syntax
3. For date calculations (yesterday, last week), use the calculator or compute directly
4. Include all required parameters for each tool call

Output ONLY valid JSON in this format:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "What this step does",
      "tool": "tool.name",
      "depends_on": [],
      "parameters": {{"param1": "value1"}}
    }},
    {{
      "step_number": 2,
      "description": "Use result from step 1",
      "tool": "another.tool",
      "depends_on": [1],
      "parameters": {{"input": "$step_1.result"}}
    }}
  ]
}}

Date reference keywords (will be resolved automatically):
- YESTERDAY, TODAY, TOMORROW
- LAST WEEK, NEXT WEEK
- LAST MONDAY, LAST TUESDAY, ... LAST SUNDAY (gets the most recent past occurrence)
- THIS MONDAY, THIS TUESDAY, ... (gets this week's occurrence)
- NEXT MONDAY, NEXT TUESDAY, ... (gets next week's occurrence)

Example for "what was the weather yesterday?":
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "Get current location",
      "tool": "system-geo-location.get-system-geo-location",
      "depends_on": [],
      "parameters": {{}}
    }},
    {{
      "step_number": 2,
      "description": "Get weather for yesterday at current location",
      "tool": "weather.get-weather-for-date",
      "depends_on": [1],
      "parameters": {{
        "date": "YESTERDAY"
      }}
    }}
  ]
}}

Example for "what was the weather like last Tuesday?":
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "Get current location",
      "tool": "system-geo-location.get-system-geo-location",
      "depends_on": [],
      "parameters": {{}}
    }},
    {{
      "step_number": 2,
      "description": "Get weather for last Tuesday at current location",
      "tool": "weather.get-weather-for-date",
      "depends_on": [1],
      "parameters": {{
        "date": "LAST TUESDAY"
      }}
    }}
  ]
}}

Example for "what's the weather like now in Tokyo, Japan?" (specific location mentioned):
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "Get current weather for Tokyo",
      "tool": "location-time.get-weather-for-location-and-date",
      "depends_on": [],
      "parameters": {{
        "location_name": "Tokyo, Japan",
        "date": "TODAY"
      }}
    }}
  ]
}}

Example for "what was the weather like yesterday in Paris?" (specific location + relative date):
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "Get yesterday's weather for Paris",
      "tool": "location-time.get-weather-for-location-and-date",
      "depends_on": [],
      "parameters": {{
        "location_name": "Paris, France",
        "date": "YESTERDAY"
      }}
    }}
  ]
}}

IMPORTANT: When a specific location is mentioned (city, country, address), use "location-time.get-weather-for-location-and-date" directly.
Only use "system-geo-location.get-system-geo-location" when no location is specified and you need the user's current location.


Now create the plan for: "{user_query}"
"""

    try:
        response = await query_model(chairman, [{"role": "user", "content": prompt}], timeout=30)
        
        if not response or not response.get('content'):
            return []
        
        content = response['content'].strip()
        
        # Try to extract JSON from response
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()
        
        plan = json.loads(content)
        return plan.get('steps', [])
        
    except Exception as e:
        print(f"[Orchestration] Failed to create plan: {e}")
        return []


def resolve_date_reference(date_str: str, current_date: datetime) -> str:
    """
    Resolve relative date references like YESTERDAY, LAST_WEEK, LAST TUESDAY, etc.
    """
    date_upper = date_str.upper().strip()
    
    if date_upper == "YESTERDAY":
        return (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_upper == "TODAY":
        return current_date.strftime("%Y-%m-%d")
    elif date_upper == "TOMORROW":
        return (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_upper == "LAST_WEEK" or date_upper == "LAST WEEK":
        return (current_date - timedelta(weeks=1)).strftime("%Y-%m-%d")
    elif date_upper == "NEXT_WEEK" or date_upper == "NEXT WEEK":
        return (current_date + timedelta(weeks=1)).strftime("%Y-%m-%d")
    
    # Handle "LAST <DAYNAME>" patterns (e.g., LAST TUESDAY, LAST MONDAY)
    day_names = {
        "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3,
        "FRIDAY": 4, "SATURDAY": 5, "SUNDAY": 6
    }
    
    for day_name, day_num in day_names.items():
        if f"LAST {day_name}" in date_upper or f"LAST_{day_name}" in date_upper:
            # Calculate last occurrence of this day
            current_weekday = current_date.weekday()
            days_ago = (current_weekday - day_num) % 7
            if days_ago == 0:
                days_ago = 7  # If today is that day, go back a week
            target_date = current_date - timedelta(days=days_ago)
            return target_date.strftime("%Y-%m-%d")
        
        # Handle "THIS <DAYNAME>" for upcoming day
        if f"THIS {day_name}" in date_upper or f"THIS_{day_name}" in date_upper:
            current_weekday = current_date.weekday()
            days_until = (day_num - current_weekday) % 7
            if days_until == 0:
                days_until = 0  # Today is that day
            target_date = current_date + timedelta(days=days_until)
            return target_date.strftime("%Y-%m-%d")
        
        # Handle "NEXT <DAYNAME>" for next week's day
        if f"NEXT {day_name}" in date_upper or f"NEXT_{day_name}" in date_upper:
            current_weekday = current_date.weekday()
            days_until = (day_num - current_weekday) % 7
            if days_until == 0:
                days_until = 7  # Next week's occurrence
            else:
                days_until += 7  # Go to next week
            target_date = current_date + timedelta(days=days_until)
            return target_date.strftime("%Y-%m-%d")
    
    # Return as-is if not a recognized reference
    return date_str


def is_date_reference(value: str) -> bool:
    """Check if a value looks like a date reference that should be resolved."""
    value_upper = value.upper().strip()
    
    # Simple date references
    if value_upper in ["YESTERDAY", "TODAY", "TOMORROW", "LAST_WEEK", "NEXT_WEEK", "LAST WEEK", "NEXT WEEK"]:
        return True
    
    # Day-of-week references
    day_names = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    for day in day_names:
        if f"LAST {day}" in value_upper or f"LAST_{day}" in value_upper:
            return True
        if f"THIS {day}" in value_upper or f"THIS_{day}" in value_upper:
            return True
        if f"NEXT {day}" in value_upper or f"NEXT_{day}" in value_upper:
            return True
    
    return False


def resolve_step_references(parameters: Dict, step_results: Dict[int, Any], current_date: datetime = None) -> Dict:
    """
    Resolve $step_N references in parameters to actual values from previous steps.
    Also resolves date references like YESTERDAY, LAST TUESDAY, etc.
    """
    resolved = {}
    
    for key, value in parameters.items():
        if isinstance(value, str):
            # Check for step references ($step_N.field)
            if value.startswith("$step_"):
                try:
                    # Parse $step_N.field
                    parts = value[1:].split(".")
                    step_num = int(parts[0].replace("step_", ""))
                    field_path = parts[1:] if len(parts) > 1 else []
                    
                    result = step_results.get(step_num, {})
                    
                    # Navigate to nested field
                    for field in field_path:
                        if isinstance(result, dict):
                            result = result.get(field, result)
                    
                    resolved[key] = result
                except Exception as e:
                    print(f"[Orchestration] Failed to resolve {value}: {e}")
                    resolved[key] = value
            
            # Check for date references (including day-of-week)
            elif current_date and is_date_reference(value):
                resolved_date = resolve_date_reference(value, current_date)
                print(f"[Orchestration] Resolved date '{value}' -> '{resolved_date}'")
                resolved[key] = resolved_date
            else:
                resolved[key] = value
        else:
            resolved[key] = value
    
    return resolved


async def execute_orchestrated_tools(
    user_query: str,
    on_event: Optional[Callable] = None
) -> Optional[Dict[str, Any]]:
    """
    Execute a multi-tool orchestration workflow.
    
    1. Create execution plan
    2. Execute each step in order
    3. Pass results between steps
    4. Return combined results
    
    Args:
        user_query: The user's question
        on_event: Optional callback for streaming events
        
    Returns:
        Combined results from all tool executions
    """
    registry = get_mcp_registry()
    
    print(f"[Orchestration] Starting multi-tool orchestration for: {user_query[:50]}...")
    
    if on_event:
        on_event("orchestration_start", {"query": user_query})
    
    # Get available tools
    available_tools = registry.all_tools
    if not available_tools:
        print("[Orchestration] No tools available")
        return None
    
    # Create execution plan
    print("[Orchestration] Creating execution plan...")
    plan = await plan_tool_execution(user_query, available_tools)
    
    if not plan:
        print("[Orchestration] Failed to create plan")
        return None
    
    print(f"[Orchestration] Plan created with {len(plan)} steps")
    
    if on_event:
        on_event("orchestration_plan", {"steps": plan})
    
    # Execute each step
    step_results: Dict[int, Any] = {}
    current_date = datetime.now()
    all_outputs = []
    
    for step in plan:
        step_num = step.get('step_number', 0)
        tool_name = step.get('tool', '')
        description = step.get('description', '')
        parameters = step.get('parameters', {})
        
        print(f"[Orchestration] Step {step_num}: {description}")
        print(f"[Orchestration]   Tool: {tool_name}")
        
        # Check dependencies are satisfied
        depends_on = step.get('depends_on', [])
        for dep in depends_on:
            if dep not in step_results:
                print(f"[Orchestration] Missing dependency: step {dep}")
        
        # Resolve step references in parameters
        resolved_params = resolve_step_references(parameters, step_results, current_date)
        print(f"[Orchestration]   Params: {resolved_params}")
        
        # Execute the tool
        call_id = str(uuid.uuid4())[:8]
        
        if on_event:
            on_event("tool_call_start", {
                "tool": tool_name,
                "arguments": resolved_params,
                "call_id": call_id,
                "step": step_num,
                "description": description
            })
        
        try:
            result = await registry.call_tool(tool_name, resolved_params)
            
            # Store result for later steps
            step_results[step_num] = extract_tool_result(result)
            
            if on_event:
                on_event("tool_call_complete", {
                    "tool": tool_name,
                    "result": result,
                    "call_id": call_id,
                    "step": step_num
                })
            
            # Collect output
            if result.get('success'):
                all_outputs.append({
                    "step": step_num,
                    "description": description,
                    "tool": tool_name,
                    "output": step_results[step_num]
                })
            
            print(f"[Orchestration]   Result: success={result.get('success')}")
            
        except Exception as e:
            print(f"[Orchestration]   Failed: {e}")
            step_results[step_num] = {"error": str(e)}
            
            if on_event:
                on_event("tool_call_complete", {
                    "tool": tool_name,
                    "result": {"success": False, "error": str(e)},
                    "call_id": call_id,
                    "step": step_num
                })
    
    # Combine all results
    combined_result = {
        "success": True,
        "tool": "orchestration",
        "server": "orchestration",
        "output": {
            "query": user_query,
            "steps_executed": len(all_outputs),
            "results": all_outputs,
            "final_data": step_results.get(len(plan), step_results.get(max(step_results.keys()) if step_results else 0, {}))
        }
    }
    
    if on_event:
        on_event("orchestration_complete", {
            "query": user_query,
            "steps": len(all_outputs),
            "success": True
        })
    
    print(f"[Orchestration] Complete: {len(all_outputs)} steps executed")
    return combined_result


def extract_tool_result(result: Dict[str, Any]) -> Any:
    """
    Extract the useful data from a tool result for use in subsequent steps.
    """
    if not result.get('success'):
        return result.get('error', 'Failed')
    
    output = result.get('output', {})
    
    # Handle MCP content wrapper
    if isinstance(output, dict) and 'content' in output:
        content = output['content']
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get('text', '')
            try:
                return json.loads(text)
            except:
                return text
    
    return output
