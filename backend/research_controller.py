"""
Self-Improving Research Controller

This module implements a recursive research agent that:
1. Reads context from Graphiti memory before processing queries
2. Uses a state machine approach (Think → Research/Build/Answer)
3. Writes learned knowledge back to memory
4. Can dynamically build new tools via mcp-dev-team

The controller maintains a research state and iterates until the query is answered
or the maximum number of rounds is reached.
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ResearchState:
    """State object for the research loop."""
    user_query: str
    current_knowledge: List[Dict[str, Any]] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    current_round: int = 0
    max_rounds: int = 50
    status: str = "WORKING"  # WORKING, FINISHED, ERROR
    final_answer: Optional[str] = None
    lessons_learned: List[Dict[str, Any]] = field(default_factory=list)
    

CONTROLLER_SYSTEM_PROMPT = """# Role
You are the **Recursive Research Controller**, an autonomous agent capable of self-improvement. Your goal is to answer the User Query by traversing a loop of reasoning, memory retrieval, and dynamic tool usage.

# Capabilities
1. **Graphiti Memory:** You possess a semantic knowledge graph. You do not need to research facts you have already learned.
2. **Dynamic Tooling:** You have access to a suite of MCP tools.
3. **Tool Fabrication:** Crucially, if you lack a tool required to answer a query, you can **build it yourself** using the `mcp-dev-team` meta-tool.

# Current Environment
**User Query:** "{user_query}"

**Graphiti Context (Known Facts):**
{current_context}

**Currently Registered Tools:**
{available_tools}

**Action History:**
{action_history}

# Decision Logic (The Loop)
Analyze the User Query and your Current Context. Follow this priority order strictly:

1. **COMPLETE:** If the "Graphiti Context" contains sufficient information to fully answer the User Query, output the Final Answer.
2. **USE EXISTING:** If information is missing, check "Currently Registered Tools". If a relevant tool exists, use it.
3. **BUILD NEW:** If information is missing AND no existing tool can retrieve it, you must **BUILD** a new tool.
   * Heuristic: Break the missing capability down into the smallest possible functional unit.
   * Action: Call `mcp-dev-team` to build a new tool.
4. **CORRECT:** If a previous tool execution failed (see context), analyze the error and retry with fixed parameters.

# Output Format
You must respond with a SINGLE valid JSON object. Do not include markdown formatting or prose outside the JSON.

**Schema:**
{{
  "thought_process": "Brief reasoning about what is known vs. unknown and why you are choosing this action.",
  "status": "WORKING" | "FINISHED",
  "action": {{
    "name": "tool_name_to_call or null if FINISHED",
    "parameters": {{ ... }}
  }},
  "missing_information": ["list of what is still unknown"],
  "final_answer": "Only populate if status is FINISHED. Otherwise null.",
  "lessons_learned": ["Any insights about the query, process, or data that should be saved to memory"]
}}

# Important Constraints
* **Do not hallucinate data.** If it is not in "Graphiti Context", you do not know it.
* **Tool Building:** When building a tool, be highly specific in the requirements parameter.
* **Iterative Approach:** One loop = One specific action.
* **Knowledge Recording:** Always identify lessons learned that should be saved for future queries.
"""


class SelfImprovingResearchController:
    """
    Controller for self-improving research that:
    - Retrieves context from Graphiti before processing
    - Runs a state machine loop to answer queries
    - Records learned knowledge back to memory
    """
    
    def __init__(self, memory_service=None, mcp_registry=None, llm_query_func=None):
        """
        Initialize the controller.
        
        Args:
            memory_service: The Graphiti memory service
            mcp_registry: The MCP tool registry
            llm_query_func: Function to query an LLM
        """
        self.memory_service = memory_service
        self.mcp_registry = mcp_registry
        self.llm_query_func = llm_query_func
        
    async def get_memory_context(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve relevant context from Graphiti memory."""
        if not self.memory_service:
            return []
        
        try:
            # Search memory for relevant context (use search_memories with 's')
            results = await self.memory_service.search_memories(query, limit=limit)
            return results if results else []
        except Exception as e:
            print(f"[Research Controller] Memory search error: {e}")
            return []
    
    async def get_available_tools(self) -> List[str]:
        """Get list of available MCP tools."""
        if not self.mcp_registry:
            return []
        
        try:
            tools = self.mcp_registry.all_tools
            return [f"{t.server_name}.{t.name}" for t in tools.values()] if tools else []
        except Exception as e:
            print(f"[Research Controller] Tool registry error: {e}")
            return []
    
    async def save_lesson_to_memory(self, lesson: Dict[str, Any], query: str) -> bool:
        """Save a learned lesson to Graphiti memory."""
        if not self.memory_service:
            return False
        
        try:
            episode_content = f"Lesson learned while researching '{query[:50]}...': {lesson.get('content', str(lesson))}"
            await self.memory_service.add_episode(
                content=episode_content,
                metadata={
                    "type": "lesson_learned",
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    **lesson
                }
            )
            return True
        except Exception as e:
            print(f"[Research Controller] Failed to save lesson: {e}")
            return False
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool and return results."""
        if not self.mcp_registry:
            return {"success": False, "error": "MCP registry not available"}
        
        try:
            result = await self.mcp_registry.call_tool(tool_name, parameters)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_llm_decision(self, state: ResearchState) -> Dict[str, Any]:
        """Get the LLM's next action decision based on current state."""
        if not self.llm_query_func:
            return {"status": "ERROR", "error": "LLM query function not available"}
        
        # Format context for prompt
        context_str = json.dumps(state.current_knowledge, indent=2) if state.current_knowledge else "No relevant context found in memory."
        tools_str = "\n".join(f"- {t}" for t in state.available_tools) if state.available_tools else "No tools available."
        history_str = json.dumps(state.action_history[-5:], indent=2) if state.action_history else "No actions taken yet."
        
        prompt = CONTROLLER_SYSTEM_PROMPT.format(
            user_query=state.user_query,
            current_context=context_str,
            available_tools=tools_str,
            action_history=history_str
        )
        
        try:
            response = await self.llm_query_func(
                [{"role": "system", "content": prompt}, {"role": "user", "content": "Decide on the next action."}],
                timeout=60
            )
            
            if response and response.get('content'):
                content = response['content']
                # Try to parse JSON from response
                try:
                    if '```json' in content:
                        content = content.split('```json')[1].split('```')[0]
                    elif '```' in content:
                        content = content.split('```')[1].split('```')[0]
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"status": "ERROR", "error": "Could not parse LLM response as JSON", "raw": content}
            
            return {"status": "ERROR", "error": "Empty LLM response"}
            
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    async def run_research_loop(self, query: str, on_event=None) -> Dict[str, Any]:
        """
        Run the main research loop.
        
        Args:
            query: The user's query to research
            on_event: Optional callback for streaming events
            
        Returns:
            Final result with answer and metadata
        """
        # Initialize state
        state = ResearchState(user_query=query)
        
        # Get initial context from memory
        if on_event:
            on_event("memory_search_start", {"query": query})
        
        state.current_knowledge = await self.get_memory_context(query)
        state.available_tools = await self.get_available_tools()
        
        if on_event:
            on_event("memory_search_complete", {
                "facts_found": len(state.current_knowledge),
                "tools_available": len(state.available_tools)
            })
        
        print(f"[Research Controller] Starting loop for: {query[:50]}...")
        print(f"[Research Controller] Found {len(state.current_knowledge)} relevant facts in memory")
        print(f"[Research Controller] {len(state.available_tools)} tools available")
        
        # Main loop
        while state.current_round < state.max_rounds and state.status == "WORKING":
            state.current_round += 1
            
            if on_event:
                on_event("round_start", {"round": state.current_round})
            
            print(f"[Research Controller] Round {state.current_round}/{state.max_rounds}")
            
            # Get LLM decision
            decision = await self.get_llm_decision(state)
            
            if decision.get("status") == "ERROR":
                print(f"[Research Controller] Error: {decision.get('error')}")
                state.status = "ERROR"
                break
            
            # Record action in history
            action_record = {
                "round": state.current_round,
                "thought": decision.get("thought_process", ""),
                "action": decision.get("action"),
                "timestamp": datetime.now().isoformat()
            }
            state.action_history.append(action_record)
            
            # Update missing information
            if decision.get("missing_information"):
                state.missing_information = decision["missing_information"]
            
            # Check if finished
            if decision.get("status") == "FINISHED":
                state.status = "FINISHED"
                state.final_answer = decision.get("final_answer")
                state.lessons_learned = decision.get("lessons_learned", [])
                break
            
            # Execute action
            action = decision.get("action", {})
            if action and action.get("name"):
                tool_name = action["name"]
                parameters = action.get("parameters", {})
                
                if on_event:
                    on_event("tool_execution_start", {"tool": tool_name, "parameters": parameters})
                
                print(f"[Research Controller] Executing tool: {tool_name}")
                result = await self.execute_tool(tool_name, parameters)
                
                # Add result to action record
                action_record["result"] = result
                
                if on_event:
                    on_event("tool_execution_complete", {"tool": tool_name, "success": result.get("success")})
                
                # If tool succeeded, update knowledge
                if result.get("success"):
                    state.current_knowledge.append({
                        "source": f"tool:{tool_name}",
                        "data": result.get("result"),
                        "round": state.current_round
                    })
        
        # Save lessons to memory
        if state.lessons_learned:
            print(f"[Research Controller] Saving {len(state.lessons_learned)} lessons to memory")
            for lesson in state.lessons_learned:
                if isinstance(lesson, str):
                    lesson = {"content": lesson}
                await self.save_lesson_to_memory(lesson, query)
        
        # Return result
        return {
            "success": state.status == "FINISHED",
            "status": state.status,
            "answer": state.final_answer,
            "rounds_taken": state.current_round,
            "facts_used": len(state.current_knowledge),
            "lessons_learned": state.lessons_learned,
            "action_summary": [
                {"round": a["round"], "tool": a.get("action", {}).get("name"), "thought": a.get("thought", "")[:100]}
                for a in state.action_history
            ]
        }


# Knowledge categories for memory storage
KNOWLEDGE_CATEGORIES = {
    "fact": "A verified piece of information",
    "process": "A step-by-step procedure or workflow",
    "lesson": "An insight learned from experience",
    "preference": "A user preference or configuration",
    "entity": "Information about a person, place, or thing",
    "relationship": "A connection between entities",
    "error_correction": "A correction to previously incorrect information"
}


async def augment_query_with_memory(
    query: str,
    memory_service,
    max_facts: int = 5
) -> Dict[str, Any]:
    """
    Augment a user query with relevant context from memory.
    
    This is a lightweight pre-processing step that retrieves relevant
    facts before the main council deliberation.
    
    Args:
        query: The user's query
        memory_service: The Graphiti memory service
        max_facts: Maximum number of facts to retrieve
        
    Returns:
        Dict with query, context, and metadata
    """
    context = []
    
    if memory_service:
        try:
            # Use search_memories (with 's') - the correct method name
            results = await memory_service.search_memories(query, limit=max_facts)
            if results:
                context = results
        except Exception as e:
            print(f"[Memory Augment] Error searching memory: {e}")
    
    return {
        "original_query": query,
        "context": context,
        "context_count": len(context),
        "augmented": len(context) > 0
    }


async def record_interaction_to_memory(
    query: str,
    response: str,
    memory_service,
    category: str = "fact",
    extract_entities: bool = True
) -> bool:
    """
    Record an interaction to memory for future retrieval.
    
    Args:
        query: The user's query
        response: The assistant's response
        memory_service: The Graphiti memory service
        category: Type of knowledge being stored
        extract_entities: Whether to extract and store entities
        
    Returns:
        True if successfully recorded
    """
    if not memory_service:
        return False
    
    try:
        # Create episode content
        episode_content = f"Q: {query}\nA: {response}"
        
        await memory_service.add_episode(
            content=episode_content,
            metadata={
                "type": "conversation",
                "category": category,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return True
    except Exception as e:
        print(f"[Memory Record] Error recording interaction: {e}")
        return False


# Factory function to create controller
def create_research_controller(memory_service=None, mcp_registry=None, llm_query_func=None):
    """Create a configured research controller instance."""
    return SelfImprovingResearchController(
        memory_service=memory_service,
        mcp_registry=mcp_registry,
        llm_query_func=llm_query_func
    )
