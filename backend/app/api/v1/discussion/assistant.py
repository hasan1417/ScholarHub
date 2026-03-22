"""Discussion AI assistant endpoints: model listing, invoke assistant, history."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_current_verified_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.database import SessionLocal, get_db
from app.models import (
    ProjectDiscussionAssistantExchange,
    User,
)
from app.schemas.project_discussion import (
    DiscussionAssistantRequest,
    DiscussionAssistantResponse,
    DiscussionAssistantExchangeResponse,
    OpenRouterModelInfo,
    OpenRouterModelListResponse,
)
from app.services.ai_service import AIService
from app.services.discussion_ai.openrouter_orchestrator import (
    OpenRouterOrchestrator,
    get_available_models_with_meta,
)
from app.api.utils.openrouter_access import resolve_openrouter_key_for_project
from app.api.utils.request_dedup import check_and_set_request
from app.services.subscription_service import SubscriptionService
from app.api.v1.discussion_helpers import (
    build_ai_response as _build_ai_response,
    get_channel_or_404 as _get_channel_or_404,
    display_name_for_user as _display_name_for_user,
    build_assistant_author_payload as _build_assistant_author_payload,
    broadcast_discussion_event as _broadcast_discussion_event,
    persist_assistant_exchange as _persist_assistant_exchange,
)

router = APIRouter()

logger = logging.getLogger(__name__)

_discussion_ai_core = AIService()


@router.get("/projects/{project_id}/discussion/models")
def list_openrouter_models(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_meta: bool = Query(False),
) -> Union[List[OpenRouterModelInfo], OpenRouterModelListResponse]:
    """List available OpenRouter models."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    discussion_settings = project.discussion_settings or {"enabled": True, "model": "openai/gpt-5.2-20251211"}
    use_owner_key_for_team = bool(discussion_settings.get("use_owner_key_for_team", False))
    resolution = resolve_openrouter_key_for_project(
        db,
        current_user,
        project,
        use_owner_key_for_team=use_owner_key_for_team,
    )

    meta = get_available_models_with_meta(
        include_reasoning=True,
        require_tools=True,
        api_key=resolution.get("api_key"),
        use_env_key=False,
    )
    models = [OpenRouterModelInfo(**m) for m in meta["models"]]
    warning = resolution.get("warning") or meta.get("warning")

    if include_meta:
        return OpenRouterModelListResponse(
            models=models,
            source=meta.get("source") or "fallback",
            warning=warning,
            key_source=resolution.get("source") or "none",
        )

    return models


@router.post(
    "/projects/{project_id}/discussion/channels/{channel_id}/assistant",
    response_model=DiscussionAssistantResponse,
)
async def invoke_discussion_assistant(
    project_id: str,
    channel_id: UUID,
    payload: DiscussionAssistantRequest,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
):
    """
    Invoke the AI assistant using OpenRouter.

    Model and API key are determined by project settings:
    - Model: from project.discussion_settings.model
    - API Key: project owner's key (fallback to current user's key)
    """
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    # Get discussion settings from project
    discussion_settings = project.discussion_settings or {"enabled": True, "model": "openai/gpt-5.2-20251211"}

    # Check if discussion AI is enabled for this project
    if not discussion_settings.get("enabled", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Discussion AI is disabled for this project",
        )

    # Use model from project settings
    model = discussion_settings.get("model", "openai/gpt-5.2-20251211")

    # Determine API key based on user tier + project settings
    use_owner_key_for_team = bool(discussion_settings.get("use_owner_key_for_team", False))
    resolution = resolve_openrouter_key_for_project(
        db,
        current_user,
        project,
        use_owner_key_for_team=use_owner_key_for_team,
    )
    api_key_to_use = resolution.get("api_key")
    key_source = resolution.get("source") or "none"

    if resolution.get("error_status"):
        raise HTTPException(
            status_code=int(resolution["error_status"]),
            detail={
                "error": "no_api_key" if resolution["error_status"] == 402 else "invalid_api_key",
                "message": resolution.get("error_detail") or "OpenRouter API key issue.",
            },
        )

    if not api_key_to_use:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "no_api_key",
                "message": "No API key available. Add your OpenRouter key or ask the project owner to enable key sharing.",
            },
        )

    logger.info(f"Using {key_source} OpenRouter API key for Discussion AI")

    # Check discussion AI credit limit (premium models cost 5, standard cost 1)
    from app.services.subscription_service import get_model_credit_cost
    credit_cost = get_model_credit_cost(model)
    allowed, current_usage, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "discussion_ai_calls"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "discussion_ai_calls",
                "current": current_usage,
                "limit": limit,
                "message": f"You have reached your discussion AI credit limit ({current_usage}/{limit} credits this month). Upgrade to Pro for more credits.",
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
    logger.info(f"AI Assistant - User: {current_user.email}, model: {model} (from project settings)")

    # M2 Security Fix: Fetch search results from server cache instead of trusting client data
    from app.services.discussion_ai.search_cache import get_search_results

    search_results_list = None
    if payload.recent_search_id:
        search_results_list = get_search_results(payload.recent_search_id)
        if search_results_list:
            logger.info(f"AI Assistant - Loaded {len(search_results_list)} papers from server cache (search_id={payload.recent_search_id})")
        else:
            # Redis cache expired — fall back to DB exchange records (server-generated, trusted)
            try:
                past_exchange = (
                    db.query(ProjectDiscussionAssistantExchange)
                    .filter(
                        ProjectDiscussionAssistantExchange.project_id == project.id,
                        ProjectDiscussionAssistantExchange.channel_id == channel.id,
                    )
                    .order_by(ProjectDiscussionAssistantExchange.created_at.desc())
                    .limit(10)
                    .all()
                )
                for ex in past_exchange:
                    resp = ex.response or {}
                    for action in resp.get("suggested_actions", []):
                        if action.get("action_type") == "search_results":
                            p = action.get("payload", {})
                            if p.get("search_id") == payload.recent_search_id and p.get("papers"):
                                search_results_list = p["papers"]
                                logger.info(f"AI Assistant - Recovered {len(search_results_list)} papers from DB exchange (search_id={payload.recent_search_id})")
                                break
                    if search_results_list:
                        break
            except Exception as e:
                logger.warning(f"AI Assistant - DB fallback for search results failed: {e}")

            if not search_results_list:
                logger.warning(f"AI Assistant - No cached results for search_id={payload.recent_search_id}")

    if payload.recent_search_results and not search_results_list:
        logger.info(f"AI Assistant - Ignoring {len(payload.recent_search_results)} client-provided search results (not in server cache)")

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

    # Create OpenRouter orchestrator with the determined API key
    orchestrator = OpenRouterOrchestrator(
        _discussion_ai_core,
        db,
        model=model,
        user_api_key=api_key_to_use,
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

        # Check for duplicate request using idempotency key
        if payload.idempotency_key:
            is_new, existing_exchange_id = check_and_set_request(
                payload.idempotency_key,
                exchange_id,
            )
            if not is_new and existing_exchange_id:
                logger.info(f"Duplicate request detected, returning existing exchange: {existing_exchange_id}")
                async def duplicate_response():
                    yield f"data: {json.dumps({'type': 'duplicate', 'exchange_id': existing_exchange_id})}\n\n"
                return StreamingResponse(
                    duplicate_response(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Duplicate-Request": "true",
                        "X-Existing-Exchange-Id": existing_exchange_id,
                    },
                )

        # Save exchange immediately with status="processing"
        initial_response = DiscussionAssistantResponse(
            message="",
            citations=[],
            reasoning_used=False,
            model=model,
            usage=None,
            suggested_actions=[],
        )
        await asyncio.to_thread(
            _persist_assistant_exchange,
            project.id,
            channel.id,
            current_user.id,
            exchange_id,
            payload.question,
            initial_response.model_dump(mode="json"),
            exchange_created_at,
            {},
            "processing",
            "Thinking",
        )
        await _broadcast_discussion_event(
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
        )

        # Capture values for the async generator closure
        proj_id = project.id
        chan_id = channel.id
        user_id = current_user.id
        question_text = payload.question
        reasoning_enabled = payload.reasoning or False
        selected_model = model

        async def stream_sse():
            """Async generator that streams SSE events from the orchestrator."""
            try:
                final_result = None
                async for event in orchestrator.handle_message_streaming(
                    project,
                    channel,
                    question_text,
                    recent_search_results=search_results_list,
                    recent_search_id=payload.recent_search_id,
                    previous_state_dict=previous_state_dict,
                    conversation_history=conversation_history,
                    reasoning_mode=reasoning_enabled,
                    current_user=current_user,
                ):
                    if event.get("type") == "token":
                        yield "data: " + json.dumps({"type": "token", "content": event.get("content", "")}) + "\n\n"
                    elif event.get("type") in ("status", "tool_start"):
                        status_msg = event.get("message", "Processing...")
                        # Update status in DB and broadcast
                        try:
                            def _update_status():
                                sdb = SessionLocal()
                                try:
                                    rec = sdb.query(ProjectDiscussionAssistantExchange).filter_by(
                                        id=UUID(exchange_id)
                                    ).first()
                                    if rec:
                                        rec.status_message = status_msg
                                        sdb.commit()
                                finally:
                                    sdb.close()
                            await asyncio.to_thread(_update_status)
                            await _broadcast_discussion_event(
                                proj_id, chan_id, "assistant_status",
                                {"exchange_id": exchange_id, "status_message": status_msg},
                            )
                        except Exception as e:
                            logger.warning(f"Failed to update status message: {e}")
                        if event.get("type") == "tool_start":
                            yield "data: " + json.dumps({"type": "tool_start", "tool": event.get("tool", ""), "message": status_msg, "round": event.get("round", 0)}) + "\n\n"
                        # Always emit status for backward compatibility
                        yield "data: " + json.dumps({"type": "status", "tool": event.get("tool", ""), "message": status_msg}) + "\n\n"
                    elif event.get("type") == "tool_end":
                        yield "data: " + json.dumps({"type": "tool_end", "tool": event.get("tool", ""), "round": event.get("round", 0)}) + "\n\n"
                    elif event.get("type") == "round_separator":
                        yield "data: " + json.dumps({"type": "round_separator", "round": event.get("round", 0)}) + "\n\n"
                    elif event.get("type") == "result":
                        final_result = event.get("data", {})
                        response_model = _build_ai_response(final_result, selected_model)
                        # Persist as "completed" BEFORE yielding to client
                        # so the DB is correct even if the client disconnects
                        try:
                            pdict = response_model.model_dump(mode="json")
                            cstate = final_result.get("conversation_state", {})
                            await asyncio.to_thread(
                                _persist_assistant_exchange,
                                proj_id, chan_id, user_id, exchange_id,
                                question_text, pdict, exchange_created_at,
                                cstate, "completed",
                            )
                        except Exception as e:
                            logger.error(f"Failed to persist completed exchange {exchange_id}: {e}")
                        yield "data: " + json.dumps({"type": "result", "payload": response_model.model_dump(mode="json")}) + "\n\n"
                    elif event.get("type") == "error":
                        yield "data: " + json.dumps({"type": "error", "message": event.get("message", "Error")}) + "\n\n"

                # Fire-and-forget: persist + broadcast in background so the stream closes immediately
                if final_result:
                    _final = final_result

                    async def _post_stream_work():
                        # Persist already done before yield — just broadcast + usage here
                        try:
                            resp = _build_ai_response(_final, selected_model)
                            pdict = resp.model_dump(mode="json")
                            await _broadcast_discussion_event(
                                proj_id, chan_id, "assistant_reply",
                                {"exchange": {
                                    "id": exchange_id,
                                    "question": question_text,
                                    "response": pdict,
                                    "created_at": exchange_created_at,
                                    "author": author_info,
                                    "status": "completed",
                                }},
                            )
                            await asyncio.to_thread(SubscriptionService.increment_usage, db, user_id, "discussion_ai_calls", credit_cost)
                        except Exception as e:
                            logger.error(f"Post-stream work failed for exchange {exchange_id}: {e}")

                    asyncio.create_task(_post_stream_work())

            except GeneratorExit:
                logger.info(f"Client disconnected during streaming for exchange {exchange_id}")
                # Mark exchange as failed so it doesn't stay stuck in "processing" forever.
                # _persist_assistant_exchange is sync (uses its own SessionLocal), so no await needed.
                try:
                    _persist_assistant_exchange(
                        proj_id, chan_id, user_id, exchange_id,
                        question_text,
                        {"message": "Response interrupted — you navigated away before it completed. Please try again.",
                         "citations": [], "suggested_actions": []},
                        exchange_created_at, {}, "failed",
                        "Client disconnected",
                    )
                except Exception:
                    logger.warning(f"Failed to mark exchange {exchange_id} as failed after client disconnect")
            except Exception as exc:
                logger.exception("Streaming error", exc_info=exc)
                await asyncio.to_thread(
                    _persist_assistant_exchange,
                    proj_id, chan_id, user_id, exchange_id,
                    question_text,
                    {"message": "An error occurred while processing your request.", "citations": [], "suggested_actions": []},
                    exchange_created_at, {}, "failed",
                    "Processing failed. Please try again.",
                )
                await _broadcast_discussion_event(
                    proj_id, chan_id, "assistant_failed",
                    {"exchange_id": exchange_id, "error": "Processing failed"},
                )
                yield "data: " + json.dumps({"type": "error", "message": "Processing failed"}) + "\n\n"

        return StreamingResponse(
            stream_sse(),
            media_type="text/event-stream",
            headers={"X-Exchange-Id": exchange_id},
        )

    # Non-streaming mode
    result = orchestrator.handle_message(
        project,
        channel,
        payload.question,
        recent_search_results=search_results_list,
        recent_search_id=payload.recent_search_id,
        previous_state_dict=previous_state_dict,
        conversation_history=conversation_history,
        reasoning_mode=payload.reasoning or False,
        current_user=current_user,
    )

    response = _build_ai_response(result, model)

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

    # Increment discussion AI credits
    try:
        SubscriptionService.increment_usage(db, current_user.id, "discussion_ai_calls", amount=credit_cost)
    except Exception as e:
        logger.error(f"Failed to increment discussion AI usage for user {current_user.id}: {e}")

    return response


@router.get(
    "/projects/{project_id}/discussion/channels/{channel_id}/assistant-history",
    response_model=List[DiscussionAssistantExchangeResponse],
)
def list_discussion_assistant_history(
    project_id: str,
    channel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    exchanges = (
        db.query(ProjectDiscussionAssistantExchange)
        .options(joinedload(ProjectDiscussionAssistantExchange.author))
        .filter(
            ProjectDiscussionAssistantExchange.project_id == project.id,
            ProjectDiscussionAssistantExchange.channel_id == channel.id,
        )
        .order_by(ProjectDiscussionAssistantExchange.created_at.asc())
        .all()
    )

    # Auto-expire exchanges stuck in "processing" for over 2 minutes
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    for exchange in exchanges:
        if (
            getattr(exchange, "status", None) == "processing"
            and exchange.created_at
            and exchange.created_at < stale_cutoff
        ):
            exchange.status = "failed"
            exchange.status_message = "Request timed out"
            exchange.response = {
                "message": "This request timed out or was interrupted. Please try again.",
                "citations": [],
                "suggested_actions": [],
                "model": exchange.response.get("model", "") if isinstance(exchange.response, dict) else "",
            }
            db.commit()

    results: List[DiscussionAssistantExchangeResponse] = []
    for exchange in exchanges:
        try:
            response_payload = DiscussionAssistantResponse(**exchange.response)
        except Exception:
            # Fallback to basic structure if stored payload is malformed
            response_payload = _build_ai_response(
                exchange.response, str(exchange.response.get("model", ""))
            )

        author_payload = _build_assistant_author_payload(exchange.author)

        results.append(
            DiscussionAssistantExchangeResponse(
                id=exchange.id,
                question=exchange.question,
                response=response_payload,
                created_at=exchange.created_at or datetime.utcnow(),
                author=author_payload,
                status=getattr(exchange, 'status', 'completed') or 'completed',
                status_message=getattr(exchange, 'status_message', None),
            )
        )

    return results
