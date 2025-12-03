"""Service for managing conversation tags."""

import re
from typing import List, Dict, Any, Optional, Set
from .lmstudio import query_model_with_retry
from .config_loader import load_config


class TagService:
    """Service for auto-generating and managing conversation tags."""
    
    # Common tag categories
    TAG_CATEGORIES = {
        "topic": ["programming", "ai", "science", "math", "writing", "design", "business", "health"],
        "type": ["question", "help", "tutorial", "discussion", "brainstorm", "debug"],
        "domain": ["frontend", "backend", "devops", "data", "ml", "security"],
        "language": ["python", "javascript", "typescript", "rust", "go", "java", "c++"],
    }
    
    # System tags (added by automated processes)
    SYSTEM_TAGS = {"#auto", "#test", "#dev", "#debug"}
    
    def __init__(self):
        self._existing_tags: Set[str] = set()
        self._config = None
        self._refresh_config()
    
    def _refresh_config(self):
        """Refresh configuration from file."""
        self._config = load_config()
    
    def extract_tags(self, content: str) -> List[str]:
        """Extract existing tags from message content."""
        # Look for tags in HTML comment format: <!-- tags: #tag1 #tag2 | ignore -->
        match = re.search(r'<!--\s*tags:\s*([^|]+)', content, re.IGNORECASE)
        if match:
            tag_str = match.group(1)
            return [t.lower() for t in re.findall(r'#\w+', tag_str)]
        return []
    
    def add_tags_to_content(self, content: str, tags: List[str]) -> str:
        """Add tags to message content in HTML comment format."""
        if not tags:
            return content
        
        # Normalize tags
        normalized_tags = [t if t.startswith('#') else f'#{t}' for t in tags]
        tag_str = ' '.join(normalized_tags)
        
        # Check if tags already exist in content
        existing_match = re.search(r'<!--\s*tags:\s*([^|]+)\|', content, re.IGNORECASE)
        if existing_match:
            # Update existing tags
            old_tag_section = existing_match.group(0)
            new_tag_section = f'<!-- tags: {tag_str} |'
            return content.replace(old_tag_section, new_tag_section)
        else:
            # Add new tags section at the end
            return f"{content}\n\n<!-- tags: {tag_str} | system:ignore -->"
    
    async def generate_tags(
        self,
        user_message: str,
        ai_response: str,
        existing_tags: Optional[List[str]] = None,
        max_tags: int = 5
    ) -> List[str]:
        """
        Generate tags for a conversation exchange.
        
        Args:
            user_message: The user's message
            ai_response: The AI's response
            existing_tags: Tags already assigned
            max_tags: Maximum number of tags to generate
            
        Returns:
            List of suggested tags
        """
        self._refresh_config()
        
        config = load_config()
        chairman_model = config['models']['chairman']['id']
        
        # Build prompt
        existing_str = ", ".join(existing_tags) if existing_tags else "none"
        known_tags = list(self._existing_tags)[:20]  # Limit to top 20 known tags
        known_str = ", ".join(known_tags) if known_tags else "none yet"
        
        messages = [
            {
                "role": "system",
                "content": f"""You are a tag generator for a conversation system.
Generate 2-5 relevant tags for categorizing this conversation exchange.

Rules:
1. Tags must start with # and be lowercase (e.g., #python, #debugging)
2. Tags should be short (1-2 words max)
3. Prefer existing tags when relevant: {known_str}
4. DO NOT duplicate existing tags: {existing_str}
5. Focus on: topic, technology, task type
6. Respond with ONLY the tags, space-separated

Examples:
- "#python #debugging #error-handling"
- "#javascript #react #frontend"
- "#writing #creative #story" """
            },
            {
                "role": "user",
                "content": f"""User message: "{user_message[:300]}"

AI response summary: "{ai_response[:200]}..."

Generate relevant tags:"""
            }
        ]
        
        try:
            response = await query_model_with_retry(
                model=chairman_model,
                messages=messages,
                for_title=True  # Use fast title-generation settings
            )
            
            if response and response.get('content'):
                # Extract tags from response
                raw_tags = re.findall(r'#\w+(?:-\w+)*', response['content'].lower())
                
                # Filter and clean
                clean_tags = []
                for tag in raw_tags:
                    # Skip system tags
                    if tag in self.SYSTEM_TAGS:
                        continue
                    # Skip existing tags
                    if existing_tags and tag in existing_tags:
                        continue
                    clean_tags.append(tag)
                    # Track for future suggestions
                    self._existing_tags.add(tag)
                
                return clean_tags[:max_tags]
            
            return []
            
        except Exception as e:
            print(f"[TagService] Error generating tags: {e}")
            return []
    
    async def check_missing_tags(
        self,
        user_message: str,
        ai_response: str,
        current_tags: List[str]
    ) -> List[str]:
        """
        Check if any important tags are missing and suggest additions.
        
        This is triggered by the sparkle emoji in the UI.
        """
        # If no tags exist, generate new ones
        if not current_tags:
            return await self.generate_tags(user_message, ai_response)
        
        # Otherwise, check for missing important tags
        return await self.generate_tags(
            user_message, 
            ai_response, 
            existing_tags=current_tags,
            max_tags=3  # Suggest fewer when some already exist
        )
    
    def get_all_known_tags(self) -> List[str]:
        """Get all known tags for autocomplete/suggestions."""
        return sorted(list(self._existing_tags))
    
    def load_tags_from_conversations(self, conversations: List[Dict[str, Any]]):
        """Load existing tags from conversation list to build tag vocabulary."""
        for conv in conversations:
            tags = conv.get("tags", [])
            for tag in tags:
                self._existing_tags.add(tag.lower() if not tag.startswith('#') else tag)


# Global instance
tag_service = TagService()
