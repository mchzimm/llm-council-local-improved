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


def soft_delete_conversation(conversation_id: str) -> bool:
    """Soft delete a conversation (move to recycle bin)."""
    try:
        conversation = get_conversation(conversation_id)
        if not conversation:
            return False
        
        # Mark as deleted
        conversation["deleted"] = True
        conversation["deleted_at"] = time.time()
        save_conversation(conversation)
        return True
    except Exception as e:
        print(f"Error soft deleting {conversation_id}: {e}")
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
                
                # Extract tags from first user message (for CFS filtering)
                tags = []
                for msg in data.get("messages", []):
                    if msg.get("role") == "user" and msg.get("content"):
                        import re
                        match = re.search(r'<!--\s*tags:\s*([^|]+)', msg["content"], re.IGNORECASE)
                        if match:
                            tag_str = match.group(1)
                            found_tags = re.findall(r'#\w+', tag_str)
                            tags = [t.lower() for t in found_tags]
                        break  # Only check first user message
                
                conversations.append({
                    "id": data["id"],
                    "created_at": created_at,
                    "title": data.get("title", "New Conversation"),
                    "message_count": len(data["messages"]),
                    "deleted": data.get("deleted", False),
                    "deleted_at": data.get("deleted_at"),
                    "tags": tags
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
    stage3: Dict[str, Any],
    tool_result: Optional[Dict[str, Any]] = None
):
    """
    Add an assistant message with all 3 stages to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses
        stage2: List of model rankings
        stage3: Final synthesized response
        tool_result: Optional tool execution result
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3
    }
    
    # Include tool_result if present
    if tool_result:
        message["tool_result"] = tool_result

    conversation["messages"].append(message)

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


def find_duplicate_conversations() -> Dict[str, List[Dict[str, Any]]]:
    """
    Find conversations with the same user queries (potential duplicates).
    
    Conversations are considered duplicates if they have:
    1. The same number of user messages
    2. The same content in each user message (in order)
    
    Returns:
        Dict mapping a "signature" (hash of queries) to list of matching conversations
    """
    ensure_data_dir()
    
    import hashlib
    
    # Group conversations by their user queries signature
    signature_groups = {}
    
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith('.json'):
            continue
            
        path = os.path.join(DATA_DIR, filename)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                
            # Skip deleted conversations
            if data.get("deleted", False):
                continue
                
            # Extract user queries
            user_queries = []
            for msg in data.get("messages", []):
                if msg.get("role") == "user":
                    user_queries.append(msg.get("content", "").strip())
            
            # Create signature from queries
            if not user_queries:
                continue  # Skip empty conversations
                
            signature = hashlib.md5("|".join(user_queries).encode()).hexdigest()
            
            if signature not in signature_groups:
                signature_groups[signature] = []
            
            # Get created_at for sorting
            created_at = data.get("created_at", "")
            if isinstance(created_at, str):
                try:
                    from datetime import datetime
                    created_at_ts = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                except:
                    created_at_ts = 0
            else:
                created_at_ts = float(created_at) if created_at else 0
                
            signature_groups[signature].append({
                "id": data["id"],
                "title": data.get("title", "New Conversation"),
                "query_count": len(user_queries),
                "first_query": user_queries[0][:100] if user_queries else "",
                "created_at": data.get("created_at"),
                "created_at_ts": created_at_ts
            })
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            continue
    
    # Filter to only groups with duplicates (more than 1 conversation)
    duplicates = {sig: convs for sig, convs in signature_groups.items() if len(convs) > 1}
    
    # Sort each group by creation time (newest first)
    for sig in duplicates:
        duplicates[sig].sort(key=lambda x: x["created_at_ts"], reverse=True)
    
    return duplicates


def delete_duplicate_conversations(keep_newest: bool = True) -> Dict[str, Any]:
    """
    Find and soft-delete duplicate conversations.
    
    Args:
        keep_newest: If True, keep the newest conversation in each duplicate group.
                    If False, keep the oldest.
    
    Returns:
        Dict with deletion statistics
    """
    duplicates = find_duplicate_conversations()
    
    deleted_count = 0
    kept_count = 0
    deleted_ids = []
    
    for signature, conversations in duplicates.items():
        if len(conversations) <= 1:
            continue
        
        # Sort by creation time
        conversations.sort(key=lambda x: x["created_at_ts"], reverse=keep_newest)
        
        # Keep the first one (newest or oldest depending on keep_newest)
        kept_count += 1
        
        # Delete the rest
        for conv in conversations[1:]:
            try:
                soft_delete_conversation(conv["id"])
                deleted_count += 1
                deleted_ids.append(conv["id"])
            except Exception as e:
                print(f"Error deleting {conv['id']}: {e}")
    
    return {
        "duplicate_groups_found": len(duplicates),
        "conversations_deleted": deleted_count,
        "conversations_kept": kept_count,
        "deleted_ids": deleted_ids
    }
