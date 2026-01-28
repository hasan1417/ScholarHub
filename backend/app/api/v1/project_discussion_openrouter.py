"""
OpenRouter Discussion AI Endpoint

Provides AI assistant functionality using OpenRouter for multi-model support.
This is a separate endpoint for testing before migrating the main discussion page.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.database import SessionLocal, get_db
from app.models import (
    Project,
    ProjectDiscussionChannel,
    ProjectDiscussionAssistantExchange,
    User,
)
from app.schemas.project_discussion import (
    DiscussionAssistantCitation,
    DiscussionAssistantRequest,
    DiscussionAssistantResponse,
)
from app.services.ai_service import AIService
from app.services.discussion_ai.openrouter_orchestrator import (
    OpenRouterOrchestrator,
    get_available_models,
)
from app.services.subscription_service import SubscriptionService
from app.services.websocket_manager import connection_manager

# Import helper functions from main discussion module
from app.api.v1.project_discussion import (
    _get_channel_or_404,
    _display_name_for_user,
    _persist_assistant_exchange,
    _broadcast_discussion_event,
    _discussion_session_id,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared AI service instance
_discussion_ai_core = AIService()


class OpenRouterModelInfo(BaseModel):
    id: str
    name: str
    provider: str


@router.get("/projects/{project_id}/discussion-or/models")
def list_openrouter_models(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[OpenRouterModelInfo]:
    """List available OpenRouter models."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    return [OpenRouterModelInfo(**m) for m in get_available_models()]


@router.post(
    "/projects/{project_id}/discussion-or/channels/{channel_id}/assistant",
    response_model=DiscussionAssistantResponse,
)
def invoke_openrouter_assistant(
    project_id: str,
    channel_id: UUID,
    payload: DiscussionAssistantRequest,
    background_tasks: BackgroundTasks,
    model: str = Query("openai/gpt-5.2", description="OpenRouter model to use"),
    stream: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Invoke the AI assistant using OpenRouter.

    This endpoint mirrors the main discussion assistant but uses OpenRouter
    for multi-model support.
    """
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    # Check subscription limit for discussion AI calls
    allowed, current, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "discussion_ai_calls"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "discussion_ai_calls",
                "current": current,
                "limit": limit,
                "message": f"You have reached your AI assistant limit ({current}/{limit} calls this month). Upgrade to Pro for more AI calls.",
            },
        )

    display_name = _display_name_for_user(current_user)
    author_info = {
        "id": str(current_user.id),
        "name": {
            "first": current_user.first_name or "",
            "last": current_user.last_name or "",
            "display": display_name,
        },
    }
    logger.info(f"OpenRouter AI Assistant - User: {current_user.email}, model: {model}")
    logger.info(f"OpenRouter - recent_search_results received: {len(payload.recent_search_results) if payload.recent_search_results else 0} papers")

    # Convert search results to list of dicts
    search_results_list = None
    if payload.recent_search_results:
        search_results_list = [
            {
                "title": r.title,
                "authors": r.authors,
                "year": r.year,
                "source": r.source,
                "abstract": getattr(r, "abstract", None),
                "doi": getattr(r, "doi", None),
                "url": getattr(r, "url", None),
                "pdf_url": getattr(r, "pdf_url", None),
                "is_open_access": getattr(r, "is_open_access", None),
                "journal": getattr(r, "journal", None),
            }
            for r in payload.recent_search_results
        ]

    # Load previous conversation state
    previous_state_dict = None
    last_exchange = (
        db.query(ProjectDiscussionAssistantExchange)
        .filter(
            ProjectDiscussionAssistantExchange.project_id == project.id,
            ProjectDiscussionAssistantExchange.channel_id == channel.id,
        )
        .order_by(ProjectDiscussionAssistantExchange.created_at.desc())
        .first()
    )
    if last_exchange and last_exchange.conversation_state:
        previous_state_dict = last_exchange.conversation_state

    # Create OpenRouter orchestrator with user's API key if available
    user_api_key = current_user.openrouter_api_key
    orchestrator = OpenRouterOrchestrator(
        _discussion_ai_core,
        db,
        model=model,
        user_api_key=user_api_key,
    )

    # Convert conversation history if provided
    conversation_history = None
    if payload.conversation_history:
        conversation_history = [
            {"role": h.role, "content": h.content}
            for h in payload.conversation_history
        ]

    # Use streaming if requested
    if stream:
        exchange_id = str(uuid4())
        exchange_created_at = datetime.utcnow().isoformat() + "Z"

        # Save exchange immediately with status="processing"
        initial_response = DiscussionAssistantResponse(
            message="",
            citations=[],
            reasoning_used=False,
            model=model,
            usage=None,
            suggested_actions=[],
        )
        _persist_assistant_exchange(
            project.id,
            channel.id,
            current_user.id,
            exchange_id,
            payload.question,
            initial_response.model_dump(mode="json"),
            exchange_created_at,
            {},
            status="processing",
            status_message="Thinking",
        )
        asyncio.run(_broadcast_discussion_event(
            project.id,
            channel.id,
            "assistant_processing",
            {"exchange": {
                "id": exchange_id,
                "question": payload.question,
                "status": "processing",
                "status_message": "Thinking",
                "created_at": exchange_created_at,
                "author": author_info,
            }},
        ))

        # Use a queue to pass events from background thread to streaming response
        event_queue: queue.Queue = queue.Queue()
        processing_done = threading.Event()

        # Capture IDs before starting thread
        proj_id = project.id
        chan_id = channel.id
        user_id = current_user.id
        question_text = payload.question
        reasoning_enabled = payload.reasoning or False
        selected_model = model
        user_key = user_api_key  # Capture user's API key for the thread

        def run_ai_processing():
            """Background thread that runs AI and puts events in queue."""
            thread_db = SessionLocal()
            try:
                # Re-fetch objects in this thread's session
                thread_project = thread_db.query(Project).filter_by(id=proj_id).first()
                thread_channel = thread_db.query(ProjectDiscussionChannel).filter_by(id=chan_id).first()
                thread_user = thread_db.query(User).filter_by(id=user_id).first()

                if not thread_project or not thread_channel:
                    raise ValueError("Project or channel not found")

                # Create a new OpenRouterOrchestrator with thread's db session
                thread_orchestrator = OpenRouterOrchestrator(
                    _discussion_ai_core, thread_db, model=selected_model,
                    user_api_key=user_key,
                )

                final_result = None
                for event in thread_orchestrator.handle_message_streaming(
                    thread_project,
                    thread_channel,
                    question_text,
                    recent_search_results=search_results_list,
                    previous_state_dict=previous_state_dict,
                    conversation_history=conversation_history,
                    reasoning_mode=reasoning_enabled,
                    current_user=thread_user,
                ):
                    event_queue.put(event)
                    if event.get("type") == "result":
                        final_result = event.get("data", {})
                    elif event.get("type") == "status":
                        status_msg = event.get("message", "Processing...")
                        try:
                            exchange_record = thread_db.query(ProjectDiscussionAssistantExchange).filter_by(
                                id=UUID(exchange_id)
                            ).first()
                            if exchange_record:
                                exchange_record.status_message = status_msg
                                thread_db.commit()
                                asyncio.run(_broadcast_discussion_event(
                                    proj_id,
                                    chan_id,
                                    "assistant_status",
                                    {"exchange_id": exchange_id, "status_message": status_msg},
                                ))
                        except Exception as e:
                            logger.warning(f"Failed to update status message: {e}")

                # Processing complete - save result
                if final_result:
                    citations = [
                        DiscussionAssistantCitation(
                            origin=c.get("origin"),
                            origin_id=c.get("origin_id"),
                            label=c.get("label", ""),
                            resource_type=c.get("resource_type"),
                        )
                        for c in final_result.get("citations", [])
                    ]
                    suggested_actions = [
                        {
                            "action_type": a.get("type", a.get("action_type", "")),
                            "summary": a.get("summary", ""),
                            "payload": a.get("payload", {}),
                        }
                        for a in final_result.get("actions", [])
                    ]
                    response_model = DiscussionAssistantResponse(
                        message=final_result.get("message", ""),
                        citations=citations,
                        reasoning_used=final_result.get("reasoning_used", False),
                        model=final_result.get("model_used", selected_model),
                        usage=None,
                        suggested_actions=suggested_actions,
                    )
                    payload_dict = response_model.model_dump(mode="json")
                    conversation_state = final_result.get("conversation_state", {})

                    _persist_assistant_exchange(
                        proj_id,
                        chan_id,
                        user_id,
                        exchange_id,
                        question_text,
                        payload_dict,
                        exchange_created_at,
                        conversation_state,
                        status="completed",
                    )

                    asyncio.run(_broadcast_discussion_event(
                        proj_id,
                        chan_id,
                        "assistant_reply",
                        {"exchange": {
                            "id": exchange_id,
                            "question": question_text,
                            "response": payload_dict,
                            "created_at": exchange_created_at,
                            "author": author_info,
                            "status": "completed",
                        }},
                    ))

                    # Increment usage
                    try:
                        SubscriptionService.increment_usage(thread_db, user_id, "discussion_ai_calls")
                    except Exception:
                        pass

            except Exception as exc:
                logger.exception("OpenRouter AI processing failed", exc_info=exc)
                _persist_assistant_exchange(
                    proj_id,
                    chan_id,
                    user_id,
                    exchange_id,
                    question_text,
                    {"message": "An error occurred while processing your request.", "citations": [], "suggested_actions": []},
                    exchange_created_at,
                    {},
                    status="failed",
                    status_message="Processing failed. Please try again.",
                )
                asyncio.run(_broadcast_discussion_event(
                    proj_id,
                    chan_id,
                    "assistant_failed",
                    {"exchange_id": exchange_id, "error": "Processing failed"},
                ))
                event_queue.put({"type": "error", "message": "Processing failed"})
            finally:
                event_queue.put(None)  # Signal end
                processing_done.set()
                thread_db.close()

        # Start AI processing in background thread
        ai_thread = threading.Thread(target=run_ai_processing, daemon=True)
        ai_thread.start()

        def stream_events():
            """Stream events from the queue to the client."""
            try:
                while True:
                    try:
                        event = event_queue.get(timeout=0.5)
                    except queue.Empty:
                        if processing_done.is_set():
                            break
                        continue

                    if event is None:
                        break

                    if event.get("type") == "token":
                        yield "data: " + json.dumps({"type": "token", "content": event.get("content", "")}) + "\n\n"
                    elif event.get("type") == "status":
                        yield "data: " + json.dumps({"type": "status", "tool": event.get("tool", ""), "message": event.get("message", "Processing")}) + "\n\n"
                    elif event.get("type") == "result":
                        final_data = event.get("data", {})
                        # Debug logging
                        print(f"[Stream DEBUG] Received result event")
                        print(f"[Stream DEBUG] actions in final_data: {final_data.get('actions', [])}")
                        citations = [
                            DiscussionAssistantCitation(
                                origin=c.get("origin"),
                                origin_id=c.get("origin_id"),
                                label=c.get("label", ""),
                                resource_type=c.get("resource_type"),
                            )
                            for c in final_data.get("citations", [])
                        ]
                        suggested_actions = [
                            {
                                "action_type": a.get("type", a.get("action_type", "")),
                                "summary": a.get("summary", ""),
                                "payload": a.get("payload", {}),
                            }
                            for a in final_data.get("actions", [])
                        ]
                        print(f"[Stream DEBUG] suggested_actions: {len(suggested_actions)} items")
                        response_model = DiscussionAssistantResponse(
                            message=final_data.get("message", ""),
                            citations=citations,
                            reasoning_used=final_data.get("reasoning_used", False),
                            model=final_data.get("model_used", selected_model),
                            usage=None,
                            suggested_actions=suggested_actions,
                        )
                        yield "data: " + json.dumps({"type": "result", "payload": response_model.model_dump(mode="json")}) + "\n\n"
                    elif event.get("type") == "error":
                        yield "data: " + json.dumps({"type": "error", "message": event.get("message", "Error")}) + "\n\n"

            except GeneratorExit:
                logger.info(f"Client disconnected, AI processing continues in background for exchange {exchange_id}")
            except Exception as exc:
                logger.exception("Streaming error", exc_info=exc)
                yield "data: " + json.dumps({"type": "error", "message": "Stream error"}) + "\n\n"

        return StreamingResponse(stream_events(), media_type="text/event-stream")

    # Non-streaming mode
    result = orchestrator.handle_message(
        project,
        channel,
        payload.question,
        recent_search_results=search_results_list,
        previous_state_dict=previous_state_dict,
        conversation_history=conversation_history,
        reasoning_mode=payload.reasoning or False,
        current_user=current_user,
    )

    citations = [
        DiscussionAssistantCitation(
            origin=c.get("origin"),
            origin_id=c.get("origin_id"),
            label=c.get("label", ""),
            resource_type=c.get("resource_type"),
        )
        for c in result.get("citations", [])
    ]
    suggested_actions = [
        {
            "action_type": a.get("type", a.get("action_type", "")),
            "summary": a.get("summary", ""),
            "payload": a.get("payload", {}),
        }
        for a in result.get("actions", [])
    ]

    response = DiscussionAssistantResponse(
        message=result.get("message", ""),
        citations=citations,
        reasoning_used=result.get("reasoning_used", False),
        model=result.get("model_used", model),
        usage=None,
        suggested_actions=suggested_actions,
    )

    # Persist exchange
    exchange_id = str(uuid4())
    exchange_created_at = datetime.utcnow().isoformat() + "Z"
    _persist_assistant_exchange(
        project.id,
        channel.id,
        current_user.id,
        exchange_id,
        payload.question,
        response.model_dump(mode="json"),
        exchange_created_at,
        result.get("conversation_state", {}),
        status="completed",
    )

    # Increment usage
    try:
        SubscriptionService.increment_usage(db, current_user.id, "discussion_ai_calls")
    except Exception:
        pass

    return response
