"""FastAPI backend for LLM Council with background title generation."""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
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
    stage3_synthesize_streaming,
    classify_message, chairman_direct_response, check_and_execute_tools,
    assess_tool_needs_mid_deliberation
)
from .title_service import (
    get_title_service, 
    initialize_title_service, 
    shutdown_title_service
)
# Also import the instance for direct use
from .title_generation import title_service
from .model_validator import validate_models
from .config_loader import load_config, get_memory_config
from .model_metrics import get_all_metrics, get_model_ranking, cleanup_invalid_models
from .mcp.registry import get_mcp_registry, initialize_mcp, shutdown_mcp
from .memory_service import get_memory_service, initialize_memory

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifespan events."""
    # Startup
    print("🚀 Starting LLM Council API...")
    
    # Clean up invalid models from metrics
    print("🧹 Cleaning up invalid model entries from metrics...")
    cleanup_invalid_models()
    
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
    
    # Initialize MCP servers
    print("🔌 Initializing MCP servers...")
    try:
        mcp_status = await initialize_mcp()
        if mcp_status.get("enabled"):
            print(f"✅ MCP initialized: {len(mcp_status.get('tools', []))} tools available")
            for tool in mcp_status.get("tool_details", []):
                print(f"   - {tool['name']}: {tool['description']}")
        else:
            print("ℹ️  MCP disabled (no servers configured)")
    except Exception as e:
        print(f"⚠️  MCP initialization failed: {e} (continuing without MCP)")
    
    # Initialize Memory service (depends on MCP being initialized first)
    print("🧠 Initializing memory service...")
    try:
        memory_config = get_memory_config()
        if memory_config.get("enabled", True):
            memory_available = await initialize_memory()
            if memory_available:
                print(f"✅ Memory service initialized (threshold: {memory_config.get('confidence_threshold', 0.8)})")
            else:
                print("ℹ️  Memory service unavailable (Graphiti not connected)")
        else:
            print("ℹ️  Memory service disabled in config")
    except Exception as e:
        print(f"⚠️  Memory initialization failed: {e} (continuing without memory)")
    
    # Initialize Title generation service and scan for untitled conversations
    print("📝 Initializing title generation service...")
    try:
        await initialize_title_service()
        print("✅ Title generation service started")
    except Exception as e:
        print(f"⚠️  Title service initialization failed: {e} (continuing without auto-titles)")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down LLM Council API...")
    await shutdown_title_service()
    await shutdown_mcp()
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
    truncate_at: Optional[int] = None  # Index to truncate messages before re-run
    skip_user_message: bool = False  # Skip adding user message (for re-runs)
    regenerate_title: bool = False  # Force title regeneration (for edits)


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


@app.get("/api/mcp/status")
async def get_mcp_status():
    """Get MCP registry status and available tools."""
    registry = get_mcp_registry()
    return registry._get_status()


@app.post("/api/mcp/call")
async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]):
    """Call an MCP tool directly."""
    registry = get_mcp_registry()
    result = await registry.call_tool(tool_name, arguments)
    return result


@app.get("/api/memory/status")
async def get_memory_status():
    """Get memory service status and configuration."""
    memory_service = get_memory_service()
    memory_config = get_memory_config()
    return {
        "available": memory_service.is_available,
        "enabled": memory_config.get("enabled", True),
        "confidence_threshold": memory_config.get("confidence_threshold", 0.8),
        "max_memory_age_days": memory_config.get("max_memory_age_days", 30),
        "group_id": memory_config.get("group_id", "llm_council"),
        "record_user_messages": memory_config.get("record_user_messages", True),
        "record_council_responses": memory_config.get("record_council_responses", True),
        "record_chairman_synthesis": memory_config.get("record_chairman_synthesis", True)
    }


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


@app.get("/api/conversations/duplicates")
async def get_duplicate_conversations():
    """Find conversations with identical user queries (potential duplicates)."""
    try:
        duplicates = storage.find_duplicate_conversations()
        return {
            "duplicate_groups": len(duplicates),
            "groups": [
                {
                    "signature": sig,
                    "query_count": convs[0]["query_count"] if convs else 0,
                    "first_query": convs[0]["first_query"] if convs else "",
                    "conversations": convs
                }
                for sig, convs in duplicates.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/conversations/duplicates/delete")
async def delete_duplicate_conversations(keep_newest: bool = True):
    """Delete all duplicate conversations, keeping one copy of each.
    
    Args:
        keep_newest: If true, keep the newest conversation in each group.
                    If false, keep the oldest.
    """
    try:
        result = storage.delete_duplicate_conversations(keep_newest=keep_newest)
        return result
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
    Send a message with intelligent routing.
    Simple/factual queries get direct responses; complex queries use council deliberation.
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

    # If this is the first message and has generic title, trigger title generation
    if is_first_message and current_title.startswith("Conversation "):
        asyncio.create_task(title_service.generate_title(conversation_id, request.content))

    # Classify the message to determine routing
    classification = await classify_message(request.content)
    msg_type = classification.get("type", "deliberation")
    
    # Check for tool usage - also force tool check for websearch keywords
    tool_result = None
    needs_tool_check = (
        classification.get("requires_tools", False) or 
        msg_type in ["factual", "chat"] or
        _requires_websearch(request.content)  # Force check for news/events queries
    )
    if needs_tool_check:
        tool_result = await check_and_execute_tools(request.content)
    
    # Route based on message type
    if msg_type in ["factual", "chat"]:
        # Direct response path - skip council deliberation
        direct_result = await chairman_direct_response(request.content, tool_result)
        
        # Save as simplified assistant message (include tool_result)
        storage.add_assistant_message(
            conversation_id,
            [],  # No stage1
            [],  # No stage2
            direct_result,
            tool_result  # Include tool result for persistence
        )
        
        return {
            "type": "direct",
            "direct_response": direct_result,
            "tool_result": tool_result,
            "classification": classification,
            "stage1": [],
            "stage2": [],
            "stage3": direct_result,
            "metadata": {"response_type": "direct"}
        }
    
    # Deliberation path - full 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
        tool_result  # Include tool result for persistence
    )

    return {
        "type": "deliberation",
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "tool_result": tool_result,
        "classification": classification,
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
    # Check if title needs generation (generic title pattern)
    needs_title = current_title.startswith("Conversation ") or not current_title

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # **SEQUENTIAL PROCESSING**: Generate title BEFORE council deliberation
            if needs_title:
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

            # Save complete assistant message (include tool_result)
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                tool_result  # Include tool result for persistence
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

    # Handle message truncation for re-runs
    if request.truncate_at is not None:
        # Truncate messages to keep only messages up to and including truncate_at index
        conversation["messages"] = conversation["messages"][:request.truncate_at + 1]
        storage.save_conversation(conversation)

    # Check if this is the first message and conversation has generic title
    is_first_message = len(conversation["messages"]) == 0
    current_title = conversation.get("title", "").strip()
    # Check if title needs generation (generic title pattern or forced regeneration)
    needs_title = current_title.startswith("Conversation ") or not current_title or request.regenerate_title

    async def token_event_generator():
        try:
            # Add user message (unless skipping for re-runs where user message already exists)
            if not request.skip_user_message:
                storage.add_user_message(conversation_id, request.content)

            # Generate title if needed (first message, generic title, or forced regeneration)
            if needs_title:
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
            
            # ===== PHASE -1: Check memory for quick response =====
            memory_service = get_memory_service()
            memory_config = get_memory_config()
            
            if memory_service.is_available and memory_config.get("enabled", True):
                yield f"data: {json.dumps({'type': 'memory_check_start'})}\n\n"
                
                memory_response = await memory_service.get_memory_response(request.content, on_event)
                
                # Stream any memory events
                while not events_queue.empty():
                    event_type, data = events_queue.get_nowait()
                    yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
                
                if memory_response:
                    # High confidence memory response - skip standard workflow
                    yield f"data: {json.dumps({'type': 'memory_response_start', 'confidence': memory_response['confidence']})}\n\n"
                    
                    direct_result = {
                        "model": "memory",
                        "response": memory_response["response"],
                        "type": "memory",
                        "confidence": memory_response["confidence"],
                        "memories_used": memory_response.get("memories_used", 0)
                    }
                    
                    yield f"data: {json.dumps({'type': 'memory_response_complete', 'data': direct_result})}\n\n"
                    
                    # Save as assistant message
                    storage.add_assistant_message(
                        conversation_id,
                        [],  # No stage1
                        [],  # No stage2
                        direct_result,
                        None  # No tool result
                    )
                    
                    yield f"data: {json.dumps({'type': 'complete', 'response_type': 'memory'})}\n\n"
                    return
                else:
                    yield f"data: {json.dumps({'type': 'memory_check_complete', 'using_memory': False})}\n\n"
            
            # Record user message to memory (async, non-blocking)
            if memory_service.is_available and memory_config.get("record_user_messages", True):
                asyncio.create_task(memory_service.record_user_message(request.content, conversation_id))
            
            # ===== PHASE 0: Classify message =====
            yield f"data: {json.dumps({'type': 'classification_start'})}\n\n"
            
            classification = await classify_message(request.content, on_event)
            yield f"data: {json.dumps({'type': 'classification_complete', 'classification': classification})}\n\n"
            
            # Always check for tool usage using LLM-based confidence scoring
            # The new system uses expectation analysis to determine if tools can help
            tool_result = None
            yield f"data: {json.dumps({'type': 'tool_check_start'})}\n\n"
            tool_result = await check_and_execute_tools(request.content, on_event)
            
            # Stream any tool events
            while not events_queue.empty():
                event_type, data = events_queue.get_nowait()
                yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
            
            # Send tool_result event for frontend display if tool was used successfully
            if tool_result and tool_result.get('success'):
                from .council import format_tool_result_for_prompt
                tool_context = format_tool_result_for_prompt(tool_result)
                tool_name = f"{tool_result.get('server')}.{tool_result.get('tool')}"
                tool_event = {
                    'type': 'tool_result',
                    'tool': tool_name,
                    'input': tool_result.get('input'),
                    'output': tool_result.get('output'),
                    'formatted': tool_context
                }
                yield f"data: {json.dumps(tool_event)}\n\n"
            
            # ===== ROUTING DECISION =====
            msg_type = classification.get("type", "deliberation")
            
            if msg_type in ["factual", "chat"]:
                # Direct response path - skip council deliberation
                yield f"data: {json.dumps({'type': 'direct_response_start', 'reason': classification.get('reasoning', 'Simple query')})}\n\n"
                
                direct_task = asyncio.create_task(
                    chairman_direct_response(request.content, tool_result, on_event)
                )
                
                direct_result = None
                while direct_result is None:
                    try:
                        event_type, data = await asyncio.wait_for(
                            events_queue.get(), timeout=0.1
                        )
                        yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
                    except asyncio.TimeoutError:
                        if direct_task.done():
                            direct_result = direct_task.result()
                
                # Drain remaining events
                while not events_queue.empty():
                    event_type, data = events_queue.get_nowait()
                    yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
                
                yield f"data: {json.dumps({'type': 'direct_response_complete', 'data': direct_result})}\n\n"
                
                # Save as a simplified assistant message (direct response, include tool_result)
                storage.add_assistant_message(
                    conversation_id,
                    [],  # No stage1 results
                    [],  # No stage2 results
                    direct_result,  # Direct response as stage3
                    tool_result  # Include tool result for persistence
                )
                
                # Save final answer as markdown
                if direct_result and direct_result.get("response"):
                    try:
                        storage.save_final_answer_markdown(
                            conversation_id, 
                            direct_result["response"]
                        )
                    except Exception as md_err:
                        print(f"[Storage] Failed to save markdown: {md_err}")
                
                # Record direct response to memory (async, non-blocking)
                if memory_service.is_available and memory_config.get("record_chairman_synthesis", True):
                    model_name = direct_result.get("model", "unknown")
                    response_text = direct_result.get("response", "")
                    asyncio.create_task(memory_service.record_direct_response(
                        request.content, response_text, model_name, conversation_id
                    ))
                
                yield f"data: {json.dumps({'type': 'complete', 'response_type': 'direct'})}\n\n"
                return
            
            # ===== DELIBERATION PATH =====
            yield f"data: {json.dumps({'type': 'deliberation_start', 'reason': classification.get('reasoning', 'Complex query')})}\n\n"
            
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
            
            # ===== MID-DELIBERATION TOOL ASSESSMENT (after Stage 1) =====
            # Check if additional tools would help before Stage 2
            # Only consider websearch for mid-deliberation (other tools should be used upfront)
            stage1_summary = "\n".join([f"- {r.get('model', 'unknown')}: {r.get('response', '')[:200]}..." for r in stage1_results])
            registry = get_mcp_registry()
            available_tools = registry.get_tool_descriptions() if registry.all_tools else ""
            
            previous_tools = [tool_result] if tool_result and tool_result.get('success') else []
            mid_assessment = await assess_tool_needs_mid_deliberation(
                request.content, "stage1", stage1_summary, available_tools, previous_tools
            )
            
            mid_tool_results = []
            if mid_assessment and mid_assessment.get('needs_tool'):
                tool_name = mid_assessment.get('tool_name', '')
                # Only execute websearch mid-deliberation (other tools should be used upfront)
                if 'websearch' in tool_name.lower() or 'search' in tool_name.lower():
                    yield f"data: {json.dumps({'type': 'mid_deliberation_tool_start', 'stage': 'stage1', 'tool': tool_name})}\n\n"
                    
                    try:
                        # Execute websearch directly
                        search_result = await registry.call_tool(
                            'websearch.search',
                            {'query': request.content}
                        )
                        
                        if search_result and search_result.get('success'):
                            mid_tool_results.append(search_result)
                            yield f"data: {json.dumps({'type': 'mid_deliberation_tool_complete', 'stage': 'stage1', 'tool': tool_name, 'success': True})}\n\n"
                    except Exception as e:
                        print(f"[Mid-Deliberation] Tool execution failed: {e}")
                        yield f"data: {json.dumps({'type': 'mid_deliberation_tool_complete', 'stage': 'stage1', 'tool': tool_name, 'success': False, 'error': str(e)})}\n\n"

            # Stage 2: Stream rankings with multi-round deliberation
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            
            stage2_task = asyncio.create_task(
                stage2_collect_rankings_streaming(request.content, stage1_results, on_event)
            )
            
            stage2_results = None
            label_to_model = None
            deliberation_metadata = None
            while stage2_results is None:
                try:
                    event_type, data = await asyncio.wait_for(
                        events_queue.get(), timeout=0.1
                    )
                    yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
                except asyncio.TimeoutError:
                    if stage2_task.done():
                        stage2_results, label_to_model, deliberation_metadata = stage2_task.result()
            
            # Drain remaining stage2 events
            while not events_queue.empty():
                event_type, data = events_queue.get_nowait()
                yield f"data: {json.dumps({'type': event_type, **data})}\n\n"
            
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings, 'deliberation': deliberation_metadata}})}\n\n"
            
            # ===== MID-DELIBERATION TOOL ASSESSMENT (after Stage 2, before synthesis) =====
            # Check if additional context would help the synthesis
            stage2_summary = "\n".join([f"- {r.get('model', 'unknown')}: ranked responses" for r in stage2_results[:3]])
            
            # Combine all previous tool results
            all_previous_tools = previous_tools + mid_tool_results
            mid_assessment_2 = await assess_tool_needs_mid_deliberation(
                request.content, "stage2", stage2_summary, available_tools, all_previous_tools
            )
            
            if mid_assessment_2 and mid_assessment_2.get('needs_tool'):
                tool_name = mid_assessment_2.get('tool_name', '')
                # Only execute websearch mid-deliberation
                if 'websearch' in tool_name.lower() or 'search' in tool_name.lower():
                    yield f"data: {json.dumps({'type': 'mid_deliberation_tool_start', 'stage': 'stage2', 'tool': tool_name})}\n\n"
                    
                    try:
                        search_result = await registry.call_tool(
                            'websearch.search',
                            {'query': request.content}
                        )
                        
                        if search_result and search_result.get('success'):
                            mid_tool_results.append(search_result)
                            yield f"data: {json.dumps({'type': 'mid_deliberation_tool_complete', 'stage': 'stage2', 'tool': tool_name, 'success': True})}\n\n"
                    except Exception as e:
                        print(f"[Mid-Deliberation] Tool execution failed: {e}")
                        yield f"data: {json.dumps({'type': 'mid_deliberation_tool_complete', 'stage': 'stage2', 'tool': tool_name, 'success': False, 'error': str(e)})}\n\n"

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

            # Save complete assistant message (include tool_result)
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                tool_result  # Include tool result for persistence
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

            # Record council responses and chairman synthesis to memory (async, non-blocking)
            if memory_service.is_available:
                # Record council member responses (Stage 1)
                if memory_config.get("record_council_responses", True) and stage1_results:
                    for result in stage1_results:
                        asyncio.create_task(memory_service.record_council_response(
                            result.get("response", ""),
                            result.get("model", "unknown"),
                            1,  # Stage 1
                            conversation_id
                        ))
                
                # Record chairman synthesis (Stage 3)
                if memory_config.get("record_chairman_synthesis", True) and stage3_result:
                    asyncio.create_task(memory_service.record_chairman_synthesis(
                        stage3_result.get("response", ""),
                        stage3_result.get("model", "unknown"),
                        conversation_id
                    ))

            yield f"data: {json.dumps({'type': 'complete', 'response_type': 'deliberation'})}\n\n"

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
    
    # Silently manage WebSocket connections (no console spam)
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
    except Exception:
        pass  # Silently handle WebSocket errors



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
