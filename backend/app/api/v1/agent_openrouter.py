"""
OpenRouter Agent API - Multi-model LaTeX Editor AI (Beta)

Provides the same capabilities as the standard agent API, but allows
model selection from various providers via OpenRouter.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import logging

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR
from app.services.subscription_service import SubscriptionService
from app.services.discussion_ai.openrouter_orchestrator import get_available_models
from app.api.utils.openrouter_keys import decrypt_openrouter_key_or_400

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


@router.get("/models", response_model=List[ModelInfo])
def list_available_models():
    """
    List available OpenRouter models for the LaTeX editor.

    Returns all models that can be used with the multi-model chat.
    """
    models = get_available_models(include_reasoning=True)
    return [
        ModelInfo(
            id=model["id"],
            name=model.get("name", model["id"]),
            provider=model.get("provider", "Unknown"),
            supports_reasoning=model.get("supports_reasoning", False),
        )
        for model in models
    ]


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
    user_api_key = decrypt_openrouter_key_or_400(
        getattr(current_user, "openrouter_api_key", None),
        error_detail="Your OpenRouter API key is invalid. Please re-enter it in Settings.",
        log_context=f"user {current_user.id}",
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
                query=request.query,
                paper_id=request.paper_id,
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
