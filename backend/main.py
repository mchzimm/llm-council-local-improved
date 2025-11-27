"""FastAPI backend for LLM Council with background title generation."""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from contextlib import asynccontextmanager
import uuid
import json
import asyncio
import time
import sys

from . import storage
from .council import (
    run_full_council, stage1_collect_responses, stage2_collect_rankings, 
    stage3_synthesize_final, calculate_aggregate_rankings,
    stage1_collect_responses_streaming, stage2_collect_rankings_streaming,
    stage3_synthesize_streaming
)
from .title_generation import title_service
from .model_validator import validate_models
from .config_loader import load_config
from .model_metrics import get_all_metrics, get_model_ranking

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifespan events."""
    # Startup
    print("🚀 Starting LLM Council API...")
    
    # Validate models and connectivity
    print("🔍 Validating models and server connectivity...")
    try:
        config = load_config()
        success, message, validated_models = validate_models(config)
        
        if not success:
            print(f"❌ Model validation failed: {message}")
            print("🛑 Please check your LLM server and model configuration.")
            print("💡 Troubleshooting:")
            print("   - Ensure LM Studio/Ollama is running")
            print("   - Check if models are loaded in your LLM server")
            print("   - Verify network connectivity")
            print("   - Check config.json model IDs match available models")
            print("   - Check per-model connection parameters if configured")
            sys.exit(1)
        
        # The validation process now handles per-model configuration
        print(f"✅ Model validation successful: {message}")
        if validated_models:
            print("📊 Validated models:")
            for model_id, connection_info in validated_models.items():
                endpoint = connection_info["api_endpoint"]
                print(f"   - {model_id} → {endpoint}")
        
    except Exception as e:
        print(f"❌ Error during model validation: {e}")
        print("🛑 Startup failed. Please check your configuration.")
        sys.exit(1)
    
    try:
        # Title generation service is initialized on demand
        print("✅ LLM Council API started successfully!")
    except Exception as e:
        print(f"❌ Error during startup: {e}")
        sys.exit(1)
    
    yield
    
    # Shutdown
    print("🛑 Shutting down LLM Council API...")
    print("✅ Services cleaned up")

app = FastAPI(title="LLM Council API", lifespan=lifespan)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/metrics")
async def get_metrics():
    """Get all model quality metrics."""
    return get_all_metrics()


@app.get("/api/metrics/ranking")
async def get_ranking():
    """Get model ranking with key metrics."""
    return get_model_ranking()


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all active conversations (metadata only, excluding deleted)."""
    all_conversations = storage.list_conversations()
    # Filter out deleted conversations
    active_conversations = [
        conv for conv in all_conversations 
        if not conv.get("deleted", False)
    ]
    return active_conversations


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation with ID-based title."""
    conversation = storage.create_conversation_with_id_title()
    
    # Don't queue empty conversations for title generation
    # Title generation will be triggered when the first message is added
    
    return conversation


@app.post("/api/conversations/migrate-titles")
async def migrate_conversation_titles():
    """Migrate existing conversations to ID-based titles."""
    try:
        count = storage.migrate_conversation_titles()
        return {"success": True, "migrated_count": count, "message": f"Migrated {count} conversations"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations/deleted")
async def list_deleted_conversations():
    """List all deleted conversations."""
    try:
        all_conversations = storage.list_conversations()
        deleted_conversations = [
            conv for conv in all_conversations 
            if conv.get("deleted", False)
        ]
        return deleted_conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message and conversation has generic title
    is_first_message = len(conversation["messages"]) == 0
    current_title = conversation.get("title", "").strip()
    
    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message and has generic title, trigger immediate title generation
    if is_first_message and current_title.startswith("Conversation "):
        title_service = get_title_service()
        # Run in background without blocking the council process
        asyncio.create_task(title_service.generate_title_immediate(conversation_id, request.content))

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message and conversation has generic title
    is_first_message = len(conversation["messages"]) == 0
    current_title = conversation.get("title", "").strip()

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # **SEQUENTIAL PROCESSING**: Generate title BEFORE council deliberation
            if is_first_message and current_title.startswith("Conversation "):
                yield f"data: {json.dumps({'type': 'title_generation_start'})}\n\n"
                
                try:
                    new_title = await title_service.generate_title(
                        conversation_id=conversation_id,
                        user_message=request.content,
                        websocket_manager=None  # Direct streaming instead
                    )
                    
                    if new_title:
                        # Update conversation title immediately
                        storage.update_conversation_title(conversation_id, new_title)
                        yield f"data: {json.dumps({'type': 'title_complete', 'title': new_title})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'title_error', 'error': 'Failed to generate title'})}\n\n"
                        
                except Exception as e:
                    print(f"Title generation error: {e}")
                    yield f"data: {json.dumps({'type': 'title_error', 'error': str(e)})}\n\n"

            # Now proceed with council deliberation
            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            print(f"Stream error: {e}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/conversations/{conversation_id}/message/stream-tokens")
async def send_message_stream_tokens(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream tokens from all stages in real-time.
    Returns Server-Sent Events for each token as it's generated.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message and conversation has generic title
    is_first_message = len(conversation["messages"]) == 0
    current_title = conversation.get("title", "").strip()

    async def token_event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Generate title first if needed
            if is_first_message and current_title.startswith("Conversation "):
                yield f"data: {json.dumps({'type': 'title_generation_start'})}\n\n"
                
                try:
                    new_title = await title_service.generate_title(
                        conversation_id=conversation_id,
                        user_message=request.content,
                        websocket_manager=None
                    )
                    
                    if new_title:
                        storage.update_conversation_title(conversation_id, new_title)
                        yield f"data: {json.dumps({'type': 'title_complete', 'title': new_title})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'title_error', 'error': 'Failed to generate title'})}\n\n"
                        
                except Exception as e:
                    print(f"Title generation error: {e}")
                    yield f"data: {json.dumps({'type': 'title_error', 'error': str(e)})}\n\n"

            # Collect events from streaming stages
            events_queue = asyncio.Queue()
            
            def on_event(event_type: str, data: dict):
                """Push events to queue for SSE streaming."""
                events_queue.put_nowait((event_type, data))
            
            # Stage 1: Stream individual responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            
            stage1_task = asyncio.create_task(
                stage1_collect_responses_streaming(request.content, on_event)
            )
            
            # Stream stage 1 events
            stage1_results = None
            while stage1_results is None:
                try:
                    event_type, data = await asyncio.wait_for(
                        events_queue.get(), timeout=0.1
                    )
                    yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
                except asyncio.TimeoutError:
                    if stage1_task.done():
                        stage1_results = stage1_task.result()
            
            # Drain remaining stage1 events
            while not events_queue.empty():
                event_type, data = events_queue.get_nowait()
                yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
            
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Stream rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            
            stage2_task = asyncio.create_task(
                stage2_collect_rankings_streaming(request.content, stage1_results, on_event)
            )
            
            stage2_results = None
            label_to_model = None
            while stage2_results is None:
                try:
                    event_type, data = await asyncio.wait_for(
                        events_queue.get(), timeout=0.1
                    )
                    yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
                except asyncio.TimeoutError:
                    if stage2_task.done():
                        stage2_results, label_to_model = stage2_task.result()
            
            # Drain remaining stage2 events
            while not events_queue.empty():
                event_type, data = events_queue.get_nowait()
                yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
            
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Stream final synthesis
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            
            stage3_task = asyncio.create_task(
                stage3_synthesize_streaming(request.content, stage1_results, stage2_results, on_event)
            )
            
            stage3_result = None
            while stage3_result is None:
                try:
                    event_type, data = await asyncio.wait_for(
                        events_queue.get(), timeout=0.1
                    )
                    yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
                except asyncio.TimeoutError:
                    if stage3_task.done():
                        stage3_result = stage3_task.result()
            
            # Drain remaining stage3 events
            while not events_queue.empty():
                event_type, data = events_queue.get_nowait()
                yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
            
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )
            
            # Save final answer as markdown file
            if stage3_result and stage3_result.get("response"):
                try:
                    storage.save_final_answer_markdown(
                        conversation_id, 
                        stage3_result["response"]
                    )
                except Exception as md_err:
                    print(f"[Storage] Failed to save markdown: {md_err}")

            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            print(f"Token stream error: {e}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        token_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/title-queue/status")
async def get_title_queue_status():
    """Get current title generation status."""
    return {
        "enabled": True,
        "service_type": "direct",
        "description": "Direct title generation without queue"
    }


@app.post("/api/conversations/{conversation_id}/generate-title")
async def trigger_title_generation(conversation_id: str):
    """Manually trigger title generation for a conversation."""
    try:
        conversation = storage.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get the first user message for title generation
        user_messages = [msg for msg in conversation["messages"] if msg["role"] == "user"]
        if not user_messages:
            return {"success": False, "message": "No user messages found for title generation"}
        
        first_message = user_messages[0]["content"]
        new_title = await title_service.generate_title(
            conversation_id=conversation_id,
            user_message=first_message
        )
        
        if new_title:
            storage.update_conversation_title(conversation_id, new_title)
            return {"success": True, "message": f"Title updated to: {new_title}", "title": new_title}
        else:
            return {"success": False, "message": "Failed to generate title"}
            
    except Exception as e:
        print(f"Manual title generation error: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}


@app.get("/api/conversations/{conversation_id}/title-status")
async def get_conversation_title_status(conversation_id: str):
    """Get title generation status for a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {
        "conversation_id": conversation_id,
        "title": conversation.get("title", ""),
        "title_status": conversation.get("title_status", "pending"),
        "title_generation_status": conversation.get("title_generation_status", {}),
        "title_generated_at": conversation.get("title_generated_at")
    }


@app.websocket("/ws/title-updates")
async def websocket_title_updates(websocket: WebSocket):
    """WebSocket endpoint for real-time title generation updates."""
    await websocket.accept()
    
    client_id = str(uuid.uuid4())
    print(f"WebSocket client connected: {client_id}")
    
    try:
        # Keep the connection alive and handle any incoming messages
        while True:
            try:
                # Wait for any messages (ping/pong, etc.)
                message = await websocket.receive_text()
                # Echo back for ping/pong
                await websocket.send_text(f"pong: {message}")
            except WebSocketDisconnect:
                break
    except Exception as e:
        print(f"WebSocket error for client {client_id}: {e}")
    finally:
        print(f"WebSocket client disconnected: {client_id}")



if __name__ == "__main__":
    import uvicorn
    
    # When running directly, we need to handle the lifespan manually
    # The uvicorn command will handle it properly automatically
    print("⚠️  Warning: Running backend directly. For full functionality, use:")
    print("   uvicorn backend.main:app --host 0.0.0.0 --port 8001")
    print("   or run: ./start.sh")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8001)


@app.patch("/api/conversations/{conversation_id}/delete")
async def soft_delete_conversation(conversation_id: str):
    """Soft delete a conversation (move to recycle bin)."""
    try:
        conversation = storage.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Mark as deleted
        conversation["deleted"] = True
        conversation["deleted_at"] = time.time()
        storage.update_conversation(conversation_id, conversation)
        
        return {"success": True, "message": "Conversation moved to recycle bin"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/conversations/{conversation_id}/restore")
async def restore_conversation(conversation_id: str):
    """Restore a conversation from recycle bin."""
    try:
        conversation = storage.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Remove deleted flag
        conversation["deleted"] = False
        if "deleted_at" in conversation:
            del conversation["deleted_at"]
        storage.update_conversation(conversation_id, conversation)
        
        return {"success": True, "message": "Conversation restored"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/conversations/{conversation_id}/permanent")
async def permanently_delete_conversation(conversation_id: str):
    """Permanently delete a conversation (cannot be restored)."""
    try:
        success = storage.delete_conversation(conversation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {"success": True, "message": "Conversation permanently deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
