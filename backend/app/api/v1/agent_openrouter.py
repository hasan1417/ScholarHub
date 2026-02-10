"""
OpenRouter Agent API - Multi-model LaTeX Editor AI (Beta)

Provides the same capabilities as the standard agent API, but allows
model selection from various providers via OpenRouter.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Union
import logging
import uuid as uuid_mod

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.research_paper import ResearchPaper
from app.models.paper_member import PaperMember, PaperRole
from app.models.editor_chat_message import EditorChatMessage
from app.schemas.editor_chat_message import EditorChatMessageResponse
from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR
from app.services.subscription_service import SubscriptionService
from app.services.discussion_ai.openrouter_orchestrator import get_available_models, get_available_models_with_meta
from app.api.utils.openrouter_access import resolve_openrouter_key_for_user

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentChatRequest(BaseModel):
    """Request model for agent chat."""
    query: str
    paper_id: Optional[str] = None
    project_id: Optional[str] = None
    document_excerpt: Optional[str] = None
    reasoning_mode: bool = False
    edit_mode: bool = False  # Kept for API compatibility, auto-detected by backend


class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str
    name: str
    provider: str
    supports_reasoning: bool = False


class ModelListResponse(BaseModel):
    models: List[ModelInfo]
    source: str
    warning: Optional[str] = None
    key_source: Optional[str] = None


@router.get("/models")
def list_available_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_meta: bool = Query(False),
) -> Union[List[ModelInfo], ModelListResponse]:
    """
    List available OpenRouter models for the LaTeX editor.

    Returns all models that can be used with the multi-model chat.
    """
    resolution = resolve_openrouter_key_for_user(db, current_user)
    api_key = resolution.get("api_key")
    key_source = resolution.get("source") or "none"

    meta = get_available_models_with_meta(include_reasoning=True, require_tools=True, api_key=api_key, use_env_key=False)
    models = [
        ModelInfo(
            id=model["id"],
            name=model.get("name", model["id"]),
            provider=model.get("provider", "Unknown"),
            supports_reasoning=model.get("supports_reasoning", False),
        )
        for model in meta["models"]
    ]
    warning = resolution.get("warning") or meta.get("warning")

    if include_meta:
        return ModelListResponse(
            models=models,
            source=meta.get("source") or "fallback",
            warning=warning,
            key_source=key_source,
        )

    return models


@router.post("/chat/stream")
async def agent_chat_stream_or(
    request: AgentChatRequest,
    model: str = Query("openai/gpt-5.2-20251211", description="OpenRouter model to use"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    OpenRouter-powered LaTeX Editor AI chat with streaming.

    Same capabilities as /agent/chat/stream but supports model selection
    via the `model` query parameter. Uses tool-based orchestration to
    automatically detect when to propose edits vs. answer questions.

    Query Parameters:
        model: OpenRouter model ID (e.g., "openai/gpt-5.2", "anthropic/claude-sonnet-4")

    Request Body:
        query: The user's question or request
        paper_id: Optional paper ID for reference context
        project_id: Optional project ID
        document_excerpt: The current LaTeX document content
        reasoning_mode: Enable reasoning mode for supported models
    """
    # Get user's OpenRouter API key if configured
    resolution = resolve_openrouter_key_for_user(db, current_user)
    user_api_key = resolution.get("api_key")
    if resolution.get("error_status"):
        raise HTTPException(
            status_code=int(resolution["error_status"]),
            detail={
                "error": "no_api_key" if resolution["error_status"] == 402 else "invalid_api_key",
                "message": resolution.get("error_detail") or "OpenRouter API key issue.",
            },
        )
    if not user_api_key:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "no_api_key",
                "message": "No API key available. Add your OpenRouter key or upgrade to Pro.",
            },
        )

    # Check subscription limit (shares limit with Discussion AI)
    # BYOK users have unlimited (-1), others have tier limits
    allowed, current, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "discussion_ai_calls"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "AI usage limit reached",
                "current": current,
                "limit": limit,
                "message": f"You've used {current}/{limit} AI calls this month. "
                           "Add your OpenRouter API key in Settings for unlimited usage, "
                           "or upgrade to Pro for more calls."
            }
        )

    logger.info(f"[agent-or] User {current_user.id} using model {model}")

    agent_service = SmartAgentServiceV2OR(
        model=model,
        user_api_key=user_api_key,
    )

    def generate():
        try:
            for chunk in agent_service.stream_query(
                db=db,
                user_id=str(current_user.id),
                user_name=current_user.first_name or "User",
                query=request.query,
                paper_id=request.paper_id,
                project_id=request.project_id,
                document_excerpt=request.document_excerpt,
                reasoning_mode=request.reasoning_mode,
            ):
                yield chunk
        finally:
            # Increment usage after streaming (counts even if interrupted)
            try:
                SubscriptionService.increment_usage(db, current_user.id, "discussion_ai_calls")
            except Exception as e:
                logger.warning(f"Failed to increment usage for user {current_user.id}: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
        }
    )


def _get_paper_for_member(db: Session, paper_id: str, user_id) -> ResearchPaper:
    """Return paper if user is owner or member, else raise 403."""
    try:
        pid = uuid_mod.UUID(str(paper_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper_id")
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == pid).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.owner_id == user_id:
        return paper
    member = db.query(PaperMember).filter(
        PaperMember.paper_id == pid,
        PaperMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this paper")
    return paper


@router.get("/chat/history")
def get_chat_history(
    paper_id: str = Query(..., description="Paper ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[EditorChatMessageResponse]:
    """Get shared editor AI chat history for a paper (all collaborators)."""
    _get_paper_for_member(db, paper_id, current_user.id)

    rows = (
        db.query(EditorChatMessage, User.first_name)
        .outerjoin(User, EditorChatMessage.user_id == User.id)
        .filter(EditorChatMessage.paper_id == str(paper_id))
        .order_by(EditorChatMessage.created_at.asc(), EditorChatMessage.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for msg, first_name in rows:
        if msg.role == "assistant":
            author_name = "AI"
            author_id = None
        else:
            author_name = first_name or "User"
            author_id = msg.user_id
        result.append(EditorChatMessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            author_name=author_name,
            author_id=author_id,
            created_at=msg.created_at,
        ))
    return result


@router.delete("/chat/history")
def clear_chat_history(
    paper_id: str = Query(..., description="Paper ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear editor AI chat history for a paper. Owner or admin only."""
    paper = _get_paper_for_member(db, paper_id, current_user.id)
    if paper.owner_id != current_user.id:
        # Check if user is an admin on this paper
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper.id,
            PaperMember.user_id == current_user.id,
            PaperMember.role == PaperRole.ADMIN,
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Only the paper owner or admin can clear chat history")

    count = db.query(EditorChatMessage).filter(
        EditorChatMessage.paper_id == str(paper_id)
    ).delete(synchronize_session=False)

    paper.editor_ai_context = {}
    db.commit()
    return {"deleted": count, "context_version": 0}


@router.get("/info")
async def get_agent_info():
    """
    Get information about the OpenRouter agent capabilities.
    """
    return {
        "name": "LaTeX Editor AI (Beta)",
        "description": "Multi-model LaTeX editor assistant powered by OpenRouter",
        "default_model": "openai/gpt-5.2-20251211",
        "available_models": len(get_available_models(include_reasoning=False)),
        "tools": [
            {
                "name": "answer_question",
                "description": "Answer questions about the paper, content, or structure",
                "when": "General questions that don't require editing"
            },
            {
                "name": "propose_edit",
                "description": "Propose edits to the document",
                "when": "User asks to change, modify, extend, shorten, rewrite, fix, improve, add, remove anything"
            },
            {
                "name": "review_document",
                "description": "Review and provide feedback",
                "when": "User asks for review, feedback, evaluation, or suggestions"
            },
            {
                "name": "explain_references",
                "description": "Discuss attached references",
                "when": "User asks about citations or wants to find papers"
            },
            {
                "name": "list_available_templates",
                "description": "List available conference/journal templates",
                "when": "User asks what formats or templates are available"
            },
            {
                "name": "apply_template",
                "description": "Convert document to a conference format",
                "when": "User asks to convert, reformat, or change to a specific conference style"
            }
        ],
        "capabilities": [
            "Multiple model selection (GPT-5.2, Claude 4.5, Gemini, DeepSeek)",
            "AI decides which action to take (no keyword matching)",
            "Answer questions about current paper",
            "Use attached references for context",
            "Propose edits with <<<EDIT>>> format",
            "Review and provide structured feedback",
            "Convert between conference formats",
            "Reasoning mode for supported models"
        ]
    }
