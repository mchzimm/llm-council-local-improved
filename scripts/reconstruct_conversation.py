#!/usr/bin/env python3
"""
Conversation Reconstruction Script

Extracts user messages from an existing conversation and re-runs each through
the current system, creating a new conversation with updated responses reflecting
the latest processing pipeline (v0.40.0+).

Usage:
    python -m scripts.reconstruct_conversation <conversation_id>
    python -m scripts.reconstruct_conversation <conversation_id> --dry-run
    python -m scripts.reconstruct_conversation <conversation_id> --stream
"""

import argparse
import asyncio
import json
import sys
import os
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx


# Configuration
API_BASE_URL = "http://localhost:8001"
CONVERSATIONS_DIR = project_root / "data" / "conversations"


def find_conversation(conversation_id: str) -> Path | None:
    """Find conversation file by partial or full ID."""
    # Try exact match first
    exact_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
    if exact_path.exists():
        return exact_path
    
    # Try partial match
    for file in CONVERSATIONS_DIR.glob("*.json"):
        if file.stem.startswith(conversation_id):
            return file
    
    return None


def extract_user_messages(conversation_path: Path) -> list[str]:
    """Extract all user messages from a conversation file."""
    with open(conversation_path) as f:
        data = json.load(f)
    
    messages = data.get("messages", [])
    user_messages = [
        msg.get("content", "")
        for msg in messages
        if msg.get("role") == "user"
    ]
    
    return user_messages


async def create_new_conversation() -> str:
    """Create a new conversation via API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/api/conversations",
            json={}  # Empty body required by API
        )
        response.raise_for_status()
        data = response.json()
        return data["id"]


async def send_message(conversation_id: str, message: str, use_stream: bool = False) -> dict:
    """Send a message to the conversation."""
    endpoint = f"{API_BASE_URL}/api/conversations/{conversation_id}/message"
    if use_stream:
        endpoint += "/stream"
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            endpoint,
            json={"content": message}
        )
        
        if use_stream:
            # Handle streaming response - collect all chunks
            full_response = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        chunk_data = json.loads(line[6:])
                        if chunk_data.get("type") == "complete":
                            return chunk_data
                        elif chunk_data.get("type") == "token":
                            full_response += chunk_data.get("content", "")
                    except json.JSONDecodeError:
                        continue
            return {"content": full_response}
        else:
            response.raise_for_status()
            return response.json()


async def reconstruct_conversation(
    source_id: str,
    dry_run: bool = False,
    use_stream: bool = False,
    verbose: bool = True
) -> dict:
    """
    Reconstruct a conversation by re-running all user messages.
    
    Args:
        source_id: Source conversation ID (full or partial)
        dry_run: If True, only show what would be done without executing
        use_stream: If True, use streaming endpoint
        verbose: If True, print progress
    
    Returns:
        dict with reconstruction details
    """
    # Find source conversation
    source_path = find_conversation(source_id)
    if not source_path:
        raise ValueError(f"Conversation not found: {source_id}")
    
    full_source_id = source_path.stem
    
    if verbose:
        print(f"📁 Source conversation: {full_source_id}")
        print(f"   File: {source_path}")
    
    # Extract user messages
    user_messages = extract_user_messages(source_path)
    
    if verbose:
        print(f"\n📝 Found {len(user_messages)} user messages:")
        for i, msg in enumerate(user_messages, 1):
            preview = msg[:80] + "..." if len(msg) > 80 else msg
            print(f"   {i}. {preview}")
    
    if dry_run:
        print("\n🔍 DRY RUN - No changes made")
        return {
            "source_id": full_source_id,
            "user_messages": len(user_messages),
            "dry_run": True,
            "new_conversation_id": None
        }
    
    # Create new conversation
    if verbose:
        print("\n🆕 Creating new conversation...")
    
    new_conversation_id = await create_new_conversation()
    
    if verbose:
        print(f"   New ID: {new_conversation_id}")
        print("\n🔄 Re-running messages through current pipeline...\n")
    
    # Process each user message
    results = []
    for i, message in enumerate(user_messages, 1):
        if verbose:
            print(f"   [{i}/{len(user_messages)}] Processing: {message[:50]}...")
        
        try:
            response = await send_message(new_conversation_id, message, use_stream)
            response_type = response.get("type", "unknown")
            results.append({
                "message": message,
                "success": True,
                "type": response_type
            })
            if verbose:
                print(f"            ✅ {response_type} response generated")
        except Exception as e:
            results.append({
                "message": message,
                "success": False,
                "error": str(e)
            })
            if verbose:
                print(f"            ❌ Error: {e}")
    
    # Summary
    successful = sum(1 for r in results if r["success"])
    
    if verbose:
        print(f"\n✅ Reconstruction complete!")
        print(f"   Source: {full_source_id[:8]}...")
        print(f"   New:    {new_conversation_id[:8]}...")
        print(f"   Messages: {successful}/{len(user_messages)} processed successfully")
    
    return {
        "source_id": full_source_id,
        "new_conversation_id": new_conversation_id,
        "user_messages": len(user_messages),
        "successful": successful,
        "results": results
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct a conversation with the current processing pipeline"
    )
    parser.add_argument(
        "conversation_id",
        help="Source conversation ID (full UUID or partial prefix)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use streaming endpoint for message processing"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output"
    )
    
    args = parser.parse_args()
    
    try:
        result = asyncio.run(reconstruct_conversation(
            args.conversation_id,
            dry_run=args.dry_run,
            use_stream=args.stream,
            verbose=not args.quiet
        ))
        
        if args.quiet:
            print(json.dumps(result, indent=2))
        
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"❌ API Error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print("❌ Could not connect to API. Is the server running?", file=sys.stderr)
        print("   Start with: ./start.sh", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
