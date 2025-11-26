"""Dedicated service for generating conversation titles with proper error handling and retries."""

import asyncio
import time
from typing import Optional, Dict, Any
from .lmstudio import query_model_with_retry
from .config_loader import load_config


class TitleGenerationService:
    """Service for generating conversation titles with circuit breaker and retry logic."""
    
    def __init__(self):
        self._failure_counts = {}
        self._circuit_breaker_time = {}
        self._config = None
        self._refresh_config()
    
    def _refresh_config(self):
        """Refresh configuration from file."""
        self._config = load_config()
    
    def _is_circuit_open(self, model: str) -> bool:
        """Check if circuit breaker is open for a model."""
        config = self._config.get('timeout_config', {})
        threshold = config.get('circuit_breaker_threshold', 5)
        
        failure_count = self._failure_counts.get(model, 0)
        if failure_count >= threshold:
            # Circuit is open, check if enough time has passed to try again
            last_failure = self._circuit_breaker_time.get(model, 0)
            if time.time() - last_failure < 60:  # 1 minute cooldown
                return True
            else:
                # Reset circuit breaker
                self._failure_counts[model] = 0
                return False
        
        return False
    
    def _record_success(self, model: str):
        """Record successful request for circuit breaker."""
        if model in self._failure_counts:
            self._failure_counts[model] = 0
    
    def _record_failure(self, model: str):
        """Record failed request for circuit breaker."""
        self._failure_counts[model] = self._failure_counts.get(model, 0) + 1
        self._circuit_breaker_time[model] = time.time()
    
    async def generate_title(
        self,
        conversation_id: str,
        user_message: str,
        websocket_manager=None
    ) -> Optional[str]:
        """
        Generate a title for the conversation.
        
        Args:
            conversation_id: ID of the conversation
            user_message: The user's message to base the title on
            websocket_manager: WebSocket manager for progress updates
            
        Returns:
            Generated title or None if failed
        """
        self._refresh_config()
        
        # Get chairman model for title generation
        config = load_config()
        chairman_model = config['models']['chairman']['id']
        
        # Check circuit breaker
        if self._is_circuit_open(chairman_model):
            print(f"Circuit breaker is open for model {chairman_model}, skipping title generation")
            if websocket_manager:
                await websocket_manager.send_title_update({
                    'type': 'title_progress',
                    'conversation_id': conversation_id,
                    'status': 'circuit_breaker_open',
                    'timestamp': time.time()
                })
            return None
        
        # Send progress update
        if websocket_manager:
            await websocket_manager.send_title_update({
                'type': 'title_progress',
                'conversation_id': conversation_id,
                'status': 'generating_title',
                'timestamp': time.time()
            })
        
        # Create title generation prompt
        messages = [
            {
                "role": "system",
                "content": "Generate a short, descriptive title (3-5 words) for a conversation based on the user's message. Only respond with the title, nothing else."
            },
            {
                "role": "user",
                "content": f"User message: {user_message}\n\nGenerate a short title for this conversation:"
            }
        ]
        
        try:
            # Send thinking status for thinking models
            if any(keyword in chairman_model.lower() for keyword in ['thinking', 'reasoning', 'o1']):
                if websocket_manager:
                    await websocket_manager.send_title_update({
                        'type': 'title_progress',
                        'conversation_id': conversation_id,
                        'status': 'thinking_title',
                        'timestamp': time.time()
                    })
            
            # Generate title with retry logic
            response = await query_model_with_retry(
                model=chairman_model,
                messages=messages,
                for_title=True
            )
            
            if response and response.get('content'):
                title = response['content'].strip()
                
                # Clean up title (remove quotes, extra whitespace, etc.)
                title = self._clean_title(title)
                
                if title:
                    self._record_success(chairman_model)
                    if websocket_manager:
                        await websocket_manager.send_title_update({
                            'type': 'title_complete',
                            'conversation_id': conversation_id,
                            'title': title,
                            'timestamp': time.time()
                        })
                    return title
            
            # If we get here, generation failed
            self._record_failure(chairman_model)
            if websocket_manager:
                await websocket_manager.send_title_update({
                    'type': 'title_error',
                    'conversation_id': conversation_id,
                    'error': 'Empty or invalid response',
                    'timestamp': time.time()
                })
            
            return None
            
        except Exception as e:
            print(f"Error generating title: {e}")
            self._record_failure(chairman_model)
            if websocket_manager:
                await websocket_manager.send_title_update({
                    'type': 'title_error',
                    'conversation_id': conversation_id,
                    'error': str(e),
                    'timestamp': time.time()
                })
            return None
    
    def _clean_title(self, title: str) -> str:
        """Clean and validate the generated title."""
        if not title:
            return ""
        
        # Remove common prefixes/suffixes
        title = title.strip()
        
        # Remove quotes
        if title.startswith('"') and title.endswith('"'):
            title = title[1:-1]
        if title.startswith("'") and title.endswith("'"):
            title = title[1:-1]
        
        # Remove "Title:" prefix if present
        if title.lower().startswith('title:'):
            title = title[6:].strip()
        
        # Remove HTML tags if present
        import re
        title = re.sub(r'<[^>]+>', '', title)
        
        # Limit length (max 50 characters for UI)
        if len(title) > 50:
            title = title[:47] + "..."
        
        # Ensure it's not empty after cleaning
        return title.strip() if title.strip() else ""


# Global instance
title_service = TitleGenerationService()