"""Background title generation service for conversations."""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from .config_loader import get_chairman_model, load_config
from .lmstudio import query_model
from .storage import (
    get_conversation as load_conversation, 
    update_conversation, 
    list_conversations,
    find_duplicate_conversations
)

@dataclass
class TitleGenerationTask:
    conversation_id: str
    priority: int = 0
    attempts: int = 0
    queued_at: float = None
    
    def __post_init__(self):
        if self.queued_at is None:
            self.queued_at = time.time()

class TitleGenerationService:
    """Background service for generating meaningful conversation titles."""
    
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Set[str] = set()
        self.websocket_connections: Dict[str, List] = {}
        self.config = load_config().get("title_generation", {})
        self.enabled = self.config.get("enabled", True)
        self.max_concurrent = self.config.get("max_concurrent", 2)
        self.timeout_seconds = self.config.get("timeout_seconds", 60)
        self.retry_attempts = self.config.get("retry_attempts", 3)
        self.thinking_models = self.config.get("thinking_models", ["thinking", "reasoning", "o1"])
        self.background_task: Optional[asyncio.Task] = None
        print(f"TitleGenerationService initialized: enabled={self.enabled}, max_concurrent={self.max_concurrent}")
    
    async def start_background_worker(self):
        """Start the background title generation worker."""
        if not self.enabled:
            print("Title generation service disabled in configuration")
            return
        
        if self.background_task and not self.background_task.done():
            print("Background worker already running")
            return
        
        self.background_task = asyncio.create_task(self._background_worker())
        print("Started background title generation worker")
    
    async def stop_background_worker(self):
        """Stop the background worker."""
        if self.background_task and not self.background_task.done():
            self.background_task.cancel()
            try:
                await self.background_task
            except asyncio.CancelledError:
                pass
        print("Stopped background title generation worker")
    
    async def generate_title_immediate(self, conversation_id: str, user_message: str) -> bool:
        """Generate title immediately for active conversation with priority processing."""
        if not self.enabled:
            return False
            
        if conversation_id in self.active_tasks:
            print(f"Title generation already in progress for {conversation_id}")
            return False
        
        try:
            # Load conversation to verify it exists and needs title
            conversation = load_conversation(conversation_id)
            if not conversation:
                print(f"Conversation {conversation_id} not found for immediate generation")
                return False
            
            # Verify the user message is provided
            if not user_message or not user_message.strip():
                print(f"No user message provided for immediate title generation of {conversation_id}")
                return False
            
            current_title = conversation.get("title", "").strip()
            if not self._is_generic_title(current_title):
                print(f"Conversation {conversation_id} already has meaningful title: {current_title}")
                return False
            
            # Add to active tasks immediately
            self.active_tasks.add(conversation_id)
            
            # Broadcast that we're starting title generation
            await self._broadcast_status_update(conversation_id, "generating_immediate")
            
            # Create background task for immediate processing
            asyncio.create_task(self._process_immediate_title_generation(conversation_id, user_message))
            
            print(f"Started immediate title generation for conversation {conversation_id}")
            return True
            
        except Exception as e:
            print(f"Error starting immediate title generation for {conversation_id}: {e}")
            self.active_tasks.discard(conversation_id)
            await self._broadcast_status_update(conversation_id, "error", {"error": str(e)})
            return False
    
    async def _process_immediate_title_generation(self, conversation_id: str, user_message: str):
        """Process immediate title generation in background."""
        try:
            # Load fresh conversation data
            conversation = load_conversation(conversation_id)
            if not conversation:
                print(f"Conversation {conversation_id} not found during immediate processing")
                return
            
            # Get chairman model and determine if it's a thinking model
            chairman_model = get_chairman_model()
            is_thinking = self._is_thinking_model(chairman_model)
            
            if is_thinking:
                await self._broadcast_status_update(conversation_id, "thinking_immediate")
            
            # Generate title with the user message as context
            title = await self._generate_title_from_message(user_message, conversation_id, is_thinking)
            
            if title:
                # Update conversation with new title
                conversation["title"] = title
                conversation["title_status"] = "complete"
                conversation["title_generated_at"] = time.time()
                conversation["title_generation_method"] = "immediate"
                
                update_conversation(conversation_id, conversation)
                
                await self._broadcast_status_update(conversation_id, "complete_immediate", {"title": title})
                print(f"Generated immediate title for {conversation_id}: {title}")
            else:
                # Fallback to queued generation
                await self._broadcast_status_update(conversation_id, "fallback_to_queue")
                await self.queue_title_generation(conversation_id, priority=10)  # High priority
                print(f"Immediate title generation failed for {conversation_id}, falling back to queue")
        
        except Exception as e:
            print(f"Error in immediate title generation for {conversation_id}: {e}")
            await self._broadcast_status_update(conversation_id, "error_immediate", {"error": str(e)})
            # Fallback to queued generation
            await self.queue_title_generation(conversation_id, priority=10)
        
        finally:
            self.active_tasks.discard(conversation_id)
    
    async def _generate_title_from_message(self, user_message: str, conversation_id: str, is_thinking: bool) -> Optional[str]:
        """Generate title directly from user message with streaming."""
        try:
            chairman_model = get_chairman_model()
            
            # Create a focused prompt for title generation
            prompt = f"""Generate a concise, meaningful title for a conversation that starts with this user message:

"{user_message}"

Requirements:
- 3-5 words maximum
- Descriptive and specific 
- No quotes around the title
- Focus on the main topic/intent

Title:"""
            
            messages = [{"role": "user", "content": prompt}]
            
            # Use the same approach as background generation
            response = await query_model(chairman_model, messages, timeout=self.timeout_seconds)
            
            if not response or not response.get('content'):
                return None
            
            # Extract and clean the title
            title = response['content'].strip()
            
            # Progress update with partial title
            await self._broadcast_status_update(conversation_id, "title_progress", {
                "partial_title": title
            })
            
            # Clean up the generated title
            title = self._clean_generated_title(title)
            
            if len(title) > 50:  # Too long, take first part
                title = title[:47] + "..."
            
            if len(title) < 3:  # Too short, invalid
                return None
                
            return title
            
        except Exception as e:
            print(f"Error generating title from message: {e}")
            return None
    async def queue_title_generation(self, conversation_id: str, priority: int = 0) -> bool:
        """Queue a conversation for title generation."""
        if not self.enabled:
            return False
        
        if conversation_id in self.active_tasks:
            print(f"Title generation already in progress for {conversation_id}")
            return False
        
        # Check if conversation needs title generation
        try:
            conversation = load_conversation(conversation_id)
            if not conversation:
                print(f"Conversation {conversation_id} not found")
                return False
            
            # Check if conversation has messages before queueing
            messages = conversation.get("messages", [])
            if not messages:
                print(f"Conversation {conversation_id} has no messages, skipping title generation")
                return False
            
            # Check if there are any user messages
            has_user_message = any(msg.get("role") == "user" for msg in messages)
            if not has_user_message:
                print(f"Conversation {conversation_id} has no user messages, skipping title generation")
                return False
            
            # Check if already has a meaningful title
            current_title = conversation.get("title", "").strip()
            if current_title and not self._is_generic_title(current_title):
                print(f"Conversation {conversation_id} already has meaningful title: {current_title}")
                return False
            
            task = TitleGenerationTask(conversation_id=conversation_id, priority=priority)
            await self.queue.put(task)
            await self._broadcast_status_update(conversation_id, "queued")
            print(f"Queued title generation for conversation {conversation_id}")
            return True
            
        except Exception as e:
            print(f"Error queuing title generation for {conversation_id}: {e}")
            return False
    
    async def queue_untitled_conversations(self):
        """Queue all conversations that need titles, excluding duplicates."""
        if not self.enabled:
            return
        
        print("Scanning for conversations that need titles...")
        conversations = list_conversations()
        queued_count = 0
        
        # Get IDs of duplicate conversations (not the newest in each group)
        duplicate_ids = set()
        try:
            duplicates = find_duplicate_conversations()
            for sig, convs in duplicates.items():
                # Skip the newest (first after sorting), mark rest as duplicates
                for conv in convs[1:]:
                    duplicate_ids.add(conv["id"])
            if duplicate_ids:
                print(f"Excluding {len(duplicate_ids)} duplicate conversations from title generation")
        except Exception as e:
            print(f"Warning: Could not check duplicates: {e}")
        
        for conversation in conversations:
            try:
                conv_id = conversation.get("id")
                if not conv_id:
                    continue
                
                # Skip duplicates
                if conv_id in duplicate_ids:
                    continue
                    
                if self._needs_title_generation(conversation):
                    await self.queue_title_generation(conv_id, priority=1)
                    queued_count += 1
            except Exception as e:
                print(f"Error checking conversation {conversation.get('id', 'unknown')}: {e}")
        
        print(f"Queued {queued_count} conversations for title generation")
    
    def _needs_title_generation(self, conversation: Dict) -> bool:
        """Check if conversation needs title generation.
        
        Works with both full conversation dicts and metadata-only dicts.
        """
        # Don't generate titles for deleted conversations
        if conversation.get("deleted", False):
            return False
        
        # Check for messages - handle both full conversation and metadata
        messages = conversation.get("messages", [])
        message_count = conversation.get("message_count", len(messages))
        
        if message_count == 0:
            return False
        
        # If we have the full messages array, check for user messages
        if messages:
            has_user_message = any(msg.get("role") == "user" for msg in messages)
            if not has_user_message:
                return False
        # If we only have metadata with message_count > 0, assume there's user content
        
        title = conversation.get("title", "").strip()
        if not title:
            return True
        
        # Check for generic titles
        if self._is_generic_title(title):
            return True
        
        # Check title generation status
        title_status = conversation.get("title_status", "pending")
        if title_status in ["pending", "error"]:
            return True
        
        return False
    
    def _is_generic_title(self, title: str) -> bool:
        """Check if title is generic and needs replacement."""
        if not title:
            return True
            
        title_lower = title.lower().strip()
        
        # Check for exact generic titles
        generic_titles = [
            "new conversation", "untitled", "conversation", "chat", 
            "new chat", "unnamed", "no title"
        ]
        
        if title_lower in generic_titles:
            return True
        
        # Check for ID-based titles like "Conversation abc12345"
        import re
        if re.match(r'^conversation\s+[a-f0-9]{8}$', title_lower):
            return True
            
        return False
    
    def _is_thinking_model(self, model_id: str) -> bool:
        """Check if model is a thinking/reasoning model."""
        model_lower = model_id.lower()
        return any(keyword in model_lower for keyword in self.thinking_models)
    
    async def _background_worker(self):
        """Main background worker loop."""
        active_workers = []
        
        try:
            while True:
                # Clean up completed workers
                active_workers = [task for task in active_workers if not task.done()]
                
                # Start new workers if we have capacity and tasks
                while len(active_workers) < self.max_concurrent:
                    try:
                        # Wait for next task with timeout
                        task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                        worker = asyncio.create_task(self._process_title_task(task))
                        active_workers.append(worker)
                    except asyncio.TimeoutError:
                        break  # No tasks available, continue loop
                
                # Wait a bit before checking again
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            print("Background worker cancelled, cleaning up...")
            # Cancel all active workers
            for worker in active_workers:
                worker.cancel()
            # Wait for them to finish
            await asyncio.gather(*active_workers, return_exceptions=True)
            raise
        except Exception as e:
            print(f"Background worker error: {e}")
    
    async def _process_title_task(self, task: TitleGenerationTask):
        """Process a single title generation task."""
        conversation_id = task.conversation_id
        
        try:
            self.active_tasks.add(conversation_id)
            await self._broadcast_status_update(conversation_id, "generating")
            
            # Load conversation
            conversation = load_conversation(conversation_id)
            if not conversation:
                print(f"Conversation {conversation_id} not found during processing")
                return
            
            # Generate title with streaming
            chairman_model = get_chairman_model()
            is_thinking = self._is_thinking_model(chairman_model)
            
            await self._broadcast_status_update(conversation_id, "thinking" if is_thinking else "generating")
            
            title = await self._generate_title_streaming(conversation, conversation_id, is_thinking)
            
            if title:
                # Update conversation with new title
                conversation["title"] = title
                conversation["title_status"] = "complete"
                conversation["title_generated_at"] = time.time()
                conversation["title_generation_attempts"] = task.attempts + 1
                
                update_conversation(conversation_id, conversation)
                
                await self._broadcast_status_update(conversation_id, "complete", {"title": title})
                print(f"Generated title for {conversation_id}: {title}")
            else:
                # Handle failure
                if task.attempts < self.retry_attempts - 1:
                    # Retry
                    retry_task = TitleGenerationTask(
                        conversation_id=conversation_id,
                        priority=task.priority + 1,
                        attempts=task.attempts + 1
                    )
                    await self.queue.put(retry_task)
                    await self._broadcast_status_update(conversation_id, "retry")
                    print(f"Retrying title generation for {conversation_id} (attempt {task.attempts + 2})")
                else:
                    # Give up
                    conversation["title_status"] = "error"
                    update_conversation(conversation_id, conversation)
                    await self._broadcast_status_update(conversation_id, "error")
                    print(f"Failed to generate title for {conversation_id} after {self.retry_attempts} attempts")
        
        except Exception as e:
            print(f"Error processing title task for {conversation_id}: {e}")
            await self._broadcast_status_update(conversation_id, "error", {"error": str(e)})
        
        finally:
            self.active_tasks.discard(conversation_id)
    
    async def _generate_title_streaming(self, conversation: Dict, conversation_id: str, is_thinking: bool) -> Optional[str]:
        """Generate title with streaming progress."""
        try:
            # Get first user message for context
            messages = conversation.get("messages", [])
            first_user_message = None
            for msg in messages:
                if msg.get("role") == "user":
                    first_user_message = msg.get("content", "")
                    break
            
            if not first_user_message:
                return None
            
            # Create title generation prompt
            prompt = self._create_title_prompt(first_user_message, conversation)
            
            # Stream thinking process if applicable
            if is_thinking:
                await self._broadcast_progress(conversation_id, "Starting title analysis...")
            
            # Generate title using chairman model
            chairman_model = get_chairman_model()
            messages_for_model = [{"role": "user", "content": prompt}]
            
            # For this implementation, we'll use the existing query_model
            # In a full streaming implementation, we'd need streaming support
            response = await query_model(chairman_model, messages_for_model, timeout=self.timeout_seconds)
            
            if not response or not response.get('content'):
                return None
            
            # Extract title from response
            content = response['content'].strip()
            title = self._extract_title_from_response(content)
            
            if is_thinking:
                # Simulate thinking process streaming
                await self._broadcast_thinking(conversation_id, content)
                await asyncio.sleep(0.5)  # Brief pause for UX
            
            return title
        
        except Exception as e:
            print(f"Error generating title: {e}")
            return None
    
    def _create_title_prompt(self, first_message: str, conversation: Dict) -> str:
        """Create prompt for title generation."""
        message_count = len(conversation.get("messages", []))
        
        prompt = f"""Based on this conversation starter, generate a concise, meaningful title (3-5 words maximum).

The title should:
- Capture the main topic or question
- Be specific but concise  
- Use clear, descriptive language
- Avoid generic phrases

First message: "{first_message[:200]}..."
Total messages in conversation: {message_count}

Think through the key topic, then provide just the title (no quotes or explanation):"""
        
        return prompt
    
    def _extract_title_from_response(self, content: str) -> Optional[str]:
        """Extract clean title from model response."""
        # Split by lines and find the title
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        # Look for the last non-empty line (usually the title)
        if lines:
            title = lines[-1]
            
            # Clean up the title - remove various markers and tags
            title = title.strip('"\'`')  # Remove quotes
            title = title.replace("Title:", "").replace("title:", "")
            title = title.replace("TITLE:", "").replace("Title ", "")
            
            # Remove HTML-like tags (e.g., <title>, </title>)
            import re
            title = re.sub(r'<[^>]*>', '', title)
            title = re.sub(r'</[^>]*>', '', title)
            
            # Remove common prefixes
            prefixes_to_remove = [
                "title:", "Title:", "TITLE:", 
                "generated title:", "Generated Title:",
                "conversation title:", "Conversation Title:",
                "final title:", "Final Title:"
            ]
            
            for prefix in prefixes_to_remove:
                if title.lower().startswith(prefix.lower()):
                    title = title[len(prefix):].strip()
            
            title = title.strip('"\'`.,;:-_')  # Remove more punctuation
            
            # Validate length and content
            word_count = len(title.split())
            if 2 <= word_count <= 8 and len(title) <= 60 and title:
                # Make sure it's not just punctuation or numbers
                if re.match(r'^[a-zA-Z].*[a-zA-Z]', title):
                    return title
        
        # Fallback: try to extract from any line that looks like a title
        for line in lines:
            cleaned = line.strip('"\'`.,;:-_')
            # Remove tags from this line too
            cleaned = re.sub(r'<[^>]*>', '', cleaned)
            cleaned = re.sub(r'</[^>]*>', '', cleaned)
            
            # Remove prefixes from this line
            for prefix in ["title:", "Title:", "TITLE:"]:
                if cleaned.lower().startswith(prefix.lower()):
                    cleaned = cleaned[len(prefix):].strip()
            
            word_count = len(cleaned.split())
            if 2 <= word_count <= 8 and len(cleaned) <= 60 and cleaned:
                if re.match(r'^[a-zA-Z].*[a-zA-Z]', cleaned):
                    return cleaned.strip()
        
        return None
    
    async def _broadcast_status_update(self, conversation_id: str, status: str, data: Dict = None):
        """Broadcast status update to connected WebSocket clients."""
        update_data = {
            "type": "title_progress",
            "conversation_id": conversation_id,
            "status": status,
            "timestamp": time.time()
        }
        if data:
            update_data.update(data)
        
        print(f"Title status update: {update_data}")
        
        # Broadcast to WebSocket clients
        if "all" in self.websocket_connections:
            disconnected_clients = []
            for connection in self.websocket_connections["all"]:
                try:
                    await connection["websocket"].send_text(json.dumps(update_data))
                except Exception as e:
                    print(f"Error sending WebSocket message to {connection['id']}: {e}")
                    disconnected_clients.append(connection["id"])
            
            # Remove disconnected clients
            for client_id in disconnected_clients:
                self.unregister_websocket(client_id)
        
        # Store status in conversation metadata for UI polling (fallback)
        try:
            conversation = load_conversation(conversation_id)
            if conversation:
                if "title_generation_status" not in conversation:
                    conversation["title_generation_status"] = {}
                conversation["title_generation_status"]["status"] = status
                conversation["title_generation_status"]["timestamp"] = time.time()
                if data:
                    conversation["title_generation_status"].update(data)
                update_conversation(conversation_id, conversation)
        except Exception as e:
            print(f"Error updating title generation status: {e}")
    
    async def _broadcast_progress(self, conversation_id: str, message: str):
        """Broadcast progress message."""
        await self._broadcast_status_update(conversation_id, "progress", {"message": message})
    
    async def _broadcast_thinking(self, conversation_id: str, thinking_content: str):
        """Broadcast thinking process content."""
        await self._broadcast_status_update(conversation_id, "thinking", {"thinking": thinking_content})
    
    def get_queue_status(self) -> Dict:
        """Get current status of the title generation queue."""
        return {
            "enabled": self.enabled,
            "queue_size": self.queue.qsize(),
            "active_tasks": len(self.active_tasks),
            "max_concurrent": self.max_concurrent,
            "active_conversation_ids": list(self.active_tasks)
        }
    
    def _clean_generated_title(self, title: str) -> str:
        """Clean and format generated title."""
        if not title:
            return ""
        
        title = title.strip()
        
        # Remove common prefixes/suffixes
        prefixes_to_remove = [
            "title:", "Title:", "TITLE:",
            "conversation:", "Conversation:", "CONVERSATION:",
            "topic:", "Topic:", "TOPIC:",
            "\"", "'", "`"
        ]
        
        for prefix in prefixes_to_remove:
            if title.startswith(prefix):
                title = title[len(prefix):].strip()
        
        # Remove trailing quotes and periods
        title = title.rstrip('"\'`.;:')
        
        # Capitalize first letter
        if title:
            title = title[0].upper() + title[1:]
        
        return title
    
    def register_websocket(self, client_id: str, websocket):
        """Register a WebSocket connection for real-time updates."""
        if "all" not in self.websocket_connections:
            self.websocket_connections["all"] = []
        self.websocket_connections["all"].append({"id": client_id, "websocket": websocket})
        print(f"Registered WebSocket client {client_id}")
    
    def unregister_websocket(self, client_id: str):
        """Unregister a WebSocket connection."""
        for conversation_id, connections in self.websocket_connections.items():
            self.websocket_connections[conversation_id] = [
                conn for conn in connections if conn["id"] != client_id
            ]
        print(f"Unregistered WebSocket client {client_id}")

# Global service instance
_title_service: Optional[TitleGenerationService] = None

def get_title_service() -> TitleGenerationService:
    """Get the global title generation service instance."""
    global _title_service
    if _title_service is None:
        _title_service = TitleGenerationService()
    return _title_service

async def initialize_title_service():
    """Initialize and start the title generation service."""
    service = get_title_service()
    await service.start_background_worker()
    await service.queue_untitled_conversations()
    return service

async def shutdown_title_service():
    """Shutdown the title generation service."""
    global _title_service
    if _title_service:
        await _title_service.stop_background_worker()
        _title_service = None