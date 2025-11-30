"""Memory service for Graphiti knowledge graph integration."""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Set
from .mcp.registry import get_mcp_registry
from .config_loader import load_config
from .lmstudio import query_model_with_retry


# Human memory type definitions for categorization
MEMORY_TYPES = {
    "episodic": {
        "description": "Personal experiences, events, and specific moments in time",
        "examples": ["I went to a meeting yesterday", "The user asked about weather last week", "A conversation about their vacation"]
    },
    "semantic": {
        "description": "General knowledge, facts, concepts, and meanings",
        "examples": ["Paris is the capital of France", "Python is a programming language", "Definitions and explanations"]
    },
    "procedural": {
        "description": "How to do things, skills, processes, and step-by-step instructions",
        "examples": ["How to write code", "Steps to deploy an application", "Recipes and workflows"]
    },
    "priming": {
        "description": "Associations, patterns, and contextual cues that influence responses",
        "examples": ["User prefers concise answers", "Technical context suggests coding", "Previous topic establishes context"]
    },
    "emotional": {
        "description": "Feelings, sentiments, and emotional context",
        "examples": ["User seems frustrated", "Positive feedback about a feature", "Concern about a deadline"]
    },
    "prospective": {
        "description": "Future intentions, plans, reminders, and goals",
        "examples": ["User wants to learn ML next month", "Reminder to follow up", "Planned features to implement"]
    },
    "autobiographical": {
        "description": "Information about the user's identity, preferences, and personal details",
        "examples": ["User's name is Max", "Works as a software engineer", "Prefers dark mode"]
    },
    "spatial": {
        "description": "Location-based information, navigation, and spatial relationships",
        "examples": ["User is in San Francisco", "Server located in US-East", "File paths and directory structures"]
    }
}

# Base group prefix for memory types
MEMORY_GROUP_PREFIX = "llm_council"


class MemoryService:
    """Service for recording and retrieving memories via Graphiti MCP server."""
    
    GRAPHITI_SERVER_NAME = "graphiti"
    
    def __init__(self):
        self._initialized = False
        self._available = False
        self._confidence_model: Optional[str] = None
        self._confidence_threshold: float = 0.8
        self._max_memory_age_days: int = 30
        self._group_id: str = "llm_council"
        self._categorization_enabled: bool = True
        self._categorization_model: Optional[str] = None
    
    async def initialize(self) -> bool:
        """Initialize the memory service, checking Graphiti availability."""
        if self._initialized:
            return self._available
        
        # Load configuration
        config = load_config()
        memory_config = config.get("memory", {})
        
        # Get confidence settings
        confidence_config = config.get("models", {}).get("confidence", {})
        self._confidence_model = confidence_config.get("id", "").strip()
        self._confidence_threshold = memory_config.get("confidence_threshold", 0.8)
        self._max_memory_age_days = memory_config.get("max_memory_age_days", 30)
        self._group_id = memory_config.get("group_id", "llm_council")
        
        # Memory categorization settings
        self._categorization_enabled = memory_config.get("categorization_enabled", True)
        categorization_config = config.get("models", {}).get("categorization", {})
        self._categorization_model = categorization_config.get("id", "").strip()
        
        # If confidence model not set, use chairman as fallback
        if not self._confidence_model:
            self._confidence_model = config.get("models", {}).get("chairman", {}).get("id", "")
        
        # If categorization model not set, use chairman as fallback
        if not self._categorization_model:
            self._categorization_model = config.get("models", {}).get("chairman", {}).get("id", "")
        
        # Check if Graphiti server is available
        registry = get_mcp_registry()
        if self.GRAPHITI_SERVER_NAME in registry.clients:
            self._available = True
            print(f"[Memory] Graphiti memory service initialized (group: {self._group_id})")
        else:
            self._available = False
            print("[Memory] Graphiti server not available - memory features disabled")
        
        self._initialized = True
        return self._available
    
    @property
    def is_available(self) -> bool:
        """Check if memory service is available."""
        return self._available
    
    async def classify_memory_types(self, content: str) -> Set[str]:
        """
        Classify content into one or more memory types using LLM.
        
        Args:
            content: The content to classify
            
        Returns:
            Set of memory type names (e.g., {"episodic", "semantic"})
        """
        if not self._categorization_enabled or not self._categorization_model:
            return {"general"}  # Fallback to general category
        
        # Build classification prompt
        type_descriptions = "\n".join([
            f"- {name}: {info['description']} (examples: {', '.join(info['examples'][:2])})"
            for name, info in MEMORY_TYPES.items()
        ])
        
        prompt = f"""Classify the following content into one or more memory types.
Return ONLY the type names separated by commas, nothing else.

Memory Types:
{type_descriptions}

Content to classify:
"{content[:500]}"

Types (comma-separated):"""

        try:
            response = await query_model_with_retry(
                self._categorization_model,
                [{"role": "user", "content": prompt}],
                temperature=0.1
            )
            
            if response and response.get("content"):
                # Parse the response - extract valid memory types
                response_text = response["content"].strip().lower()
                found_types = set()
                
                for type_name in MEMORY_TYPES.keys():
                    if type_name in response_text:
                        found_types.add(type_name)
                
                if found_types:
                    print(f"[Memory] Classified as: {found_types}")
                    return found_types
                    
        except Exception as e:
            print(f"[Memory] Classification error: {e}")
        
        # Fallback to general
        return {"general"}
    
    def _get_group_id_for_type(self, memory_type: str) -> str:
        """Get the group ID for a specific memory type."""
        if memory_type == "general":
            return self._group_id
        return f"{MEMORY_GROUP_PREFIX}_{memory_type}"
    
    def _get_all_group_ids(self) -> List[str]:
        """Get all possible group IDs for searching."""
        groups = [self._group_id]  # Base group
        for type_name in MEMORY_TYPES.keys():
            groups.append(f"{MEMORY_GROUP_PREFIX}_{type_name}")
        return groups
    
    async def record_episode(
        self,
        content: str,
        source_description: str,
        episode_type: str = "message",
        reference_time: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Record an episode (message) to the Graphiti knowledge graph.
        Automatically classifies into memory types and stores in appropriate groups.
        
        Args:
            content: The message content
            source_description: Description of source (e.g., "user", "council:model_name", "chairman:model_name")
            episode_type: Type of episode (message, response, synthesis)
            reference_time: Timestamp for the episode (defaults to now)
            metadata: Additional metadata to include
            
        Returns:
            True if recording succeeded, False otherwise
        """
        if not self._available:
            return False
        
        if reference_time is None:
            reference_time = datetime.utcnow()
        
        # Classify content into memory types
        memory_types = await self.classify_memory_types(content)
        
        # Store in each classified type's group
        success_count = 0
        for memory_type in memory_types:
            group_id = self._get_group_id_for_type(memory_type)
            
            # Build memory data for Graphiti add_memory tool
            episode_data = {
                "name": f"{episode_type}_{reference_time.strftime('%Y%m%d_%H%M%S')}",
                "episode_body": content,
                "source": "llm_council",
                "source_description": source_description,
                "reference_time": reference_time.isoformat() + "Z",
                "group_id": group_id
            }
            
            # Add memory type to metadata
            episode_metadata = metadata.copy() if metadata else {}
            episode_metadata["memory_type"] = memory_type
            episode_metadata["all_types"] = list(memory_types)
            episode_data["metadata"] = json.dumps(episode_metadata)
            
            try:
                registry = get_mcp_registry()
                result = await registry.call_tool(f"{self.GRAPHITI_SERVER_NAME}.add_memory", episode_data)
                
                if result.get("success"):
                    print(f"[Memory] Recorded episode to {group_id}: {source_description}")
                    success_count += 1
                else:
                    print(f"[Memory] Failed to record to {group_id}: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"[Memory] Error recording to {group_id}: {e}")
        
        return success_count > 0
    
    async def search_memories(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for related memories across all memory type groups.
        
        Args:
            query: Search query
            limit: Maximum number of results per group
            
        Returns:
            List of memory results with relevance scores and memory type context
        """
        if not self._available:
            return []
        
        memories = []
        all_groups = self._get_all_group_ids()
        
        try:
            registry = get_mcp_registry()
            
            # Search across all memory type groups
            for group_id in all_groups:
                # Extract memory type from group_id
                if "_" in group_id and group_id != self._group_id:
                    memory_type = group_id.split("_")[-1]
                else:
                    memory_type = "general"
                
                # Search facts (relationships/edges)
                try:
                    facts_result = await registry.call_tool(
                        f"{self.GRAPHITI_SERVER_NAME}.search_memory_facts",
                        {"query": query, "group_id": group_id, "limit": limit // 2}
                    )
                    
                    if facts_result.get("success"):
                        output = facts_result.get("output", {})
                        if isinstance(output, dict) and "content" in output:
                            content = output["content"]
                            if isinstance(content, list) and len(content) > 0:
                                text = content[0].get("text", "")
                                try:
                                    facts = json.loads(text)
                                    if isinstance(facts, list):
                                        for fact in facts:
                                            memories.append({
                                                "type": "fact",
                                                "memory_type": memory_type,
                                                "group_id": group_id,
                                                "content": fact.get("fact", ""),
                                                "created_at": fact.get("created_at", ""),
                                                "valid_at": fact.get("valid_at", ""),
                                                "uuid": fact.get("uuid", "")
                                            })
                                except json.JSONDecodeError:
                                    pass
                except Exception as e:
                    print(f"[Memory] Error searching facts in {group_id}: {e}")
                
                # Search nodes (entities)
                try:
                    nodes_result = await registry.call_tool(
                        f"{self.GRAPHITI_SERVER_NAME}.search_nodes",
                        {"query": query, "group_id": group_id, "limit": limit // 2}
                    )
                    
                    if nodes_result.get("success"):
                        output = nodes_result.get("output", {})
                        if isinstance(output, dict) and "content" in output:
                            content = output["content"]
                            if isinstance(content, list) and len(content) > 0:
                                text = content[0].get("text", "")
                                try:
                                    nodes = json.loads(text)
                                    if isinstance(nodes, list):
                                        for node in nodes:
                                            memories.append({
                                                "type": "node",
                                                "memory_type": memory_type,
                                                "group_id": group_id,
                                                "content": node.get("summary", node.get("name", "")),
                                                "created_at": node.get("created_at", ""),
                                                "uuid": node.get("uuid", "")
                                            })
                                except json.JSONDecodeError:
                                    pass
                except Exception as e:
                    print(f"[Memory] Error searching nodes in {group_id}: {e}")
            
            # Log summary by memory type
            type_counts = {}
            for m in memories:
                mt = m.get("memory_type", "unknown")
                type_counts[mt] = type_counts.get(mt, 0) + 1
            
            if memories:
                types_summary = ", ".join([f"{k}:{v}" for k, v in type_counts.items()])
                print(f"[Memory] Found {len(memories)} memories across types: {types_summary}")
            
            return memories
            
        except Exception as e:
            print(f"[Memory] Error searching memories: {e}")
            return []
    
    async def calculate_confidence(
        self,
        query: str,
        memories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate confidence score for answering query from memories.
        
        Args:
            query: The user's query
            memories: List of retrieved memories
            
        Returns:
            Dict with 'confidence' (0-1), 'reasoning', 'recommended_answer'
        """
        if not memories:
            return {
                "confidence": 0.0,
                "reasoning": "No relevant memories found",
                "recommended_answer": None
            }
        
        # Format memories for the confidence model with memory type context
        memories_text = "\n".join([
            f"- [{m.get('memory_type', 'general')}:{m['type']}] {m['content']} (created: {m.get('created_at', 'unknown')})"
            for m in memories[:10]  # Limit to top 10 for prompt
        ])
        
        # Calculate age-based weights
        now = datetime.utcnow()
        max_age = timedelta(days=self._max_memory_age_days)
        
        weighted_memories = []
        for m in memories:
            created_at_str = m.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    age = now - created_at
                    if age > max_age:
                        recency_weight = 0.0
                    else:
                        recency_weight = 1.0 - (age.total_seconds() / max_age.total_seconds())
                    weighted_memories.append({**m, "recency_weight": recency_weight})
                except:
                    weighted_memories.append({**m, "recency_weight": 0.5})
            else:
                weighted_memories.append({**m, "recency_weight": 0.5})
        
        confidence_prompt = f"""You are evaluating whether stored memories can answer a user query with high confidence.

USER QUERY: {query}

RETRIEVED MEMORIES (with recency):
{memories_text}

EVALUATION CRITERIA:
1. RELEVANCE (0-1): How directly do the memories address the query?
2. COMPLETENESS (0-1): Do the memories contain enough information to fully answer?
3. RECENCY (0-1): Are the memories recent enough to be trusted? (older = lower)
4. CERTAINTY (0-1): How confident can we be that the memories are still accurate?

Respond with ONLY a JSON object:
{{
  "confidence": <overall score 0-1>,
  "reasoning": "<brief explanation>",
  "recommended_answer": "<answer to synthesize from memories if confidence >= 0.7, else null>"
}}

If confidence is below 0.7, set recommended_answer to null."""

        messages = [{"role": "user", "content": confidence_prompt}]
        
        try:
            response = await query_model_with_retry(
                self._confidence_model,
                messages,
                timeout=30.0,
                max_retries=1
            )
            
            if not response or not response.get("content"):
                return {
                    "confidence": 0.0,
                    "reasoning": "Confidence model failed to respond",
                    "recommended_answer": None
                }
            
            content = response["content"]
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                # Clamp confidence to 0-1
                result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0))))
                return result
            
            return {
                "confidence": 0.0,
                "reasoning": "Failed to parse confidence response",
                "recommended_answer": None
            }
            
        except Exception as e:
            print(f"[Memory] Error calculating confidence: {e}")
            return {
                "confidence": 0.0,
                "reasoning": f"Error: {str(e)}",
                "recommended_answer": None
            }
    
    async def get_memory_response(
        self,
        query: str,
        on_event: Optional[Callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to answer a query from memory if confidence is high enough.
        
        Args:
            query: The user's query
            on_event: Optional callback for streaming events
            
        Returns:
            Dict with 'response', 'confidence', 'source': 'memory' if successful,
            None if confidence is too low or memory unavailable
        """
        if not self._available:
            return None
        
        if on_event:
            on_event("memory_check_start", {"query": query})
        
        # Search for related memories
        memories = await self.search_memories(query)
        
        if not memories:
            if on_event:
                on_event("memory_check_complete", {
                    "found_memories": False,
                    "confidence": 0.0
                })
            return None
        
        if on_event:
            on_event("memory_search_complete", {
                "found_memories": len(memories),
                "sample": [m["content"][:100] for m in memories[:3]]
            })
        
        # Calculate confidence
        confidence_result = await self.calculate_confidence(query, memories)
        confidence = confidence_result.get("confidence", 0.0)
        
        if on_event:
            on_event("memory_confidence_calculated", {
                "confidence": confidence,
                "threshold": self._confidence_threshold,
                "reasoning": confidence_result.get("reasoning", "")
            })
        
        # Check if confidence exceeds threshold
        if confidence >= self._confidence_threshold:
            recommended_answer = confidence_result.get("recommended_answer")
            if recommended_answer:
                if on_event:
                    on_event("memory_response_generated", {
                        "confidence": confidence,
                        "source": "memory"
                    })
                return {
                    "response": recommended_answer,
                    "confidence": confidence,
                    "source": "memory",
                    "memories_used": len(memories),
                    "reasoning": confidence_result.get("reasoning", "")
                }
        
        if on_event:
            on_event("memory_check_complete", {
                "found_memories": len(memories),
                "confidence": confidence,
                "below_threshold": True
            })
        
        return None
    
    async def record_user_message(self, content: str, conversation_id: str):
        """Record a user message asynchronously."""
        await self.record_episode(
            content=content,
            source_description="user",
            episode_type="user_message",
            metadata={"conversation_id": conversation_id}
        )
    
    async def record_council_response(
        self,
        content: str,
        model: str,
        stage: int,
        conversation_id: str
    ):
        """Record a council member's response asynchronously."""
        await self.record_episode(
            content=content,
            source_description=f"council:{model}",
            episode_type=f"stage{stage}_response",
            metadata={"conversation_id": conversation_id, "model": model, "stage": stage}
        )
    
    async def record_chairman_synthesis(
        self,
        content: str,
        model: str,
        conversation_id: str
    ):
        """Record the chairman's final synthesis asynchronously."""
        await self.record_episode(
            content=content,
            source_description=f"chairman:{model}",
            episode_type="chairman_synthesis",
            metadata={"conversation_id": conversation_id, "model": model}
        )
    
    async def record_direct_response(
        self,
        query: str,
        response: str,
        model: str,
        conversation_id: str
    ):
        """Record a direct response (non-deliberation path) asynchronously."""
        # Record both query and response as a single episode
        combined = f"Q: {query}\n\nA: {response}"
        await self.record_episode(
            content=combined,
            source_description=f"direct:{model}",
            episode_type="direct_response",
            metadata={"conversation_id": conversation_id, "model": model}
        )


# Singleton instance
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Get the global memory service instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


async def initialize_memory() -> bool:
    """Initialize the global memory service."""
    service = get_memory_service()
    return await service.initialize()
