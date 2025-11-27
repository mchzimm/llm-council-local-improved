"""JSON-based storage for conversations."""

import json
import os
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "messages": []
    }

    # Save to file
    path = get_conversation_path(conversation_id)
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return None

    with open(path, 'r') as f:
        return json.load(f)


def save_conversation(conversation: Dict[str, Any]):
    """
    Save a conversation to storage.

    Args:
        conversation: Conversation dict to save
    """
    ensure_data_dir()

    path = get_conversation_path(conversation['id'])
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)


def update_conversation(conversation_id: str, conversation: Dict[str, Any]):
    """Update an existing conversation."""
    ensure_data_dir()
    conversation_path = get_conversation_path(conversation_id)
    
    with open(conversation_path, 'w') as f:
        json.dump(conversation, f, indent=2, default=str)


def delete_conversation(conversation_id: str) -> bool:
    """Permanently delete a conversation file."""
    try:
        ensure_data_dir()
        conversation_path = get_conversation_path(conversation_id)
        if os.path.exists(conversation_path):
            os.remove(conversation_path)
            return True
        return False
    except Exception:
        return False


def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only), including deleted status.

    Returns:
        List of conversation metadata dicts
    """
    ensure_data_dir()

    conversations = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            path = os.path.join(DATA_DIR, filename)
            with open(path, 'r') as f:
                data = json.load(f)
                # Return metadata including deleted status and normalize timestamps
                created_at = data["created_at"]
                if isinstance(created_at, (int, float)):
                    # Convert timestamp to ISO format string
                    created_at = datetime.fromtimestamp(created_at).isoformat()
                
                conversations.append({
                    "id": data["id"],
                    "created_at": created_at,
                    "title": data.get("title", "New Conversation"),
                    "message_count": len(data["messages"]),
                    "deleted": data.get("deleted", False),
                    "deleted_at": data.get("deleted_at")
                })

    # Sort by creation time, newest first - handle mixed string/float timestamps
    def get_sort_key(conv):
        created_at = conv["created_at"]
        if isinstance(created_at, str):
            try:
                # Try parsing ISO format
                from datetime import datetime
                return datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
            except:
                return 0
        elif isinstance(created_at, (int, float)):
            return float(created_at)
        else:
            return 0
    
    conversations.sort(key=get_sort_key, reverse=True)

    return conversations


def migrate_conversation_titles():
    """Update existing conversations with ID-based titles."""
    ensure_data_dir()
    migrated_count = 0
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            conversation_id = filename[:-5]  # Remove .json extension
            conversation = get_conversation(conversation_id)
            
            if conversation and conversation.get('title') == 'New Conversation':
                short_id = conversation_id[:8]
                conversation['title'] = f'Conversation {short_id}'
                update_conversation(conversation_id, conversation)
                migrated_count += 1
                print(f"Migrated conversation {conversation_id} to 'Conversation {short_id}'")
    
    print(f"Migration complete: {migrated_count} conversations updated")
    return migrated_count


def create_conversation_with_id_title():
    """Create a new conversation with ID-based title."""
    conversation_id = str(uuid.uuid4())
    short_id = conversation_id[:8]
    
    conversation = {
        "id": conversation_id,
        "created_at": datetime.now().isoformat(),
        "title": f"Conversation {short_id}",
        "messages": [],
        "title_status": "id_based",
        "title_generation_status": {
            "status": "pending",
            "timestamp": time.time()
        }
    }
    
    save_conversation(conversation)
    return conversation


def add_user_message(conversation_id: str, content: str):
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "user",
        "content": content
    })

    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any]
):
    """
    Add an assistant message with all 3 stages to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses
        stage2: List of model rankings
        stage3: Final synthesized response
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3
    })

    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["title"] = title
    save_conversation(conversation)


def save_final_answer_markdown(conversation_id: str, final_answer: str):
    """
    Save the final council answer as a markdown file.
    
    Args:
        conversation_id: Conversation identifier
        final_answer: The presenter's final formatted answer
    """
    import re
    
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    
    # Get conversation title (sanitize for filename)
    title = conversation.get("title", conversation_id)
    # Remove/replace characters not safe for filenames
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    safe_title = safe_title[:100]  # Limit length
    
    # Generate UTC timestamp
    utc_timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Create filename
    filename = f"{safe_title}__{utc_timestamp}.md"
    filepath = Path(DATA_DIR).parent / filename
    
    # Build markdown content
    user_query = ""
    for msg in conversation.get("messages", []):
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break
    
    markdown_content = f"""# {title}

**Generated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}

## User Query

{user_query}

## Final Council Answer

{final_answer}
"""
    
    # Write file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"[Storage] Saved final answer to: {filepath}")
    return str(filepath)
