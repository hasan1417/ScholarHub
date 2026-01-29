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


# Available models through OpenRouter
# Must match frontend's OPENROUTER_MODELS in ModelSelector.tsx
AVAILABLE_MODELS: List[ModelInfo] = [
    # OpenAI
    ModelInfo(id="openai/gpt-5.2-20251211", name="GPT-5.2", provider="OpenAI", supports_reasoning=True),
    ModelInfo(id="openai/gpt-5.2-codex-20260114", name="GPT-5.2 Codex", provider="OpenAI", supports_reasoning=True),
    ModelInfo(id="openai/gpt-5.1-20251113", name="GPT-5.1", provider="OpenAI", supports_reasoning=True),
    ModelInfo(id="openai/gpt-4o", name="GPT-4o", provider="OpenAI"),
    ModelInfo(id="openai/gpt-4o-mini", name="GPT-4o Mini", provider="OpenAI"),
    # Anthropic
    ModelInfo(id="anthropic/claude-4.5-opus-20251124", name="Claude 4.5 Opus", provider="Anthropic", supports_reasoning=True),
    ModelInfo(id="anthropic/claude-4.5-sonnet-20250929", name="Claude 4.5 Sonnet", provider="Anthropic", supports_reasoning=True),
    ModelInfo(id="anthropic/claude-4.5-haiku-20251001", name="Claude 4.5 Haiku", provider="Anthropic", supports_reasoning=True),
    ModelInfo(id="anthropic/claude-3.5-sonnet", name="Claude 3.5 Sonnet", provider="Anthropic"),
    # Google
    ModelInfo(id="google/gemini-3-pro-preview-20251117", name="Gemini 3 Pro", provider="Google", supports_reasoning=True),
    ModelInfo(id="google/gemini-3-flash-preview-20251217", name="Gemini 3 Flash", provider="Google", supports_reasoning=True),
    ModelInfo(id="google/gemini-2.5-pro", name="Gemini 2.5 Pro", provider="Google", supports_reasoning=True),
    ModelInfo(id="google/gemini-2.5-flash", name="Gemini 2.5 Flash", provider="Google", supports_reasoning=True),
    # DeepSeek
    ModelInfo(id="deepseek/deepseek-v3.2-20251201", name="DeepSeek V3.2", provider="DeepSeek", supports_reasoning=True),
    ModelInfo(id="deepseek/deepseek-chat-v3.1", name="DeepSeek V3.1", provider="DeepSeek", supports_reasoning=True),
    ModelInfo(id="deepseek/deepseek-r1", name="DeepSeek R1", provider="DeepSeek", supports_reasoning=True),
    ModelInfo(id="deepseek/deepseek-r1:free", name="DeepSeek R1 (Free)", provider="DeepSeek", supports_reasoning=True),
    # Meta
    ModelInfo(id="meta-llama/llama-3.3-70b-instruct", name="Llama 3.3 70B", provider="Meta"),
    # Qwen
    ModelInfo(id="qwen/qwen-2.5-72b-instruct", name="Qwen 2.5 72B", provider="Qwen"),
]


@router.get("/models", response_model=List[ModelInfo])
def list_available_models():
    """
    List available OpenRouter models for the LaTeX editor.

    Returns all models that can be used with the multi-model chat.
    """
    return AVAILABLE_MODELS


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
    user_api_key = getattr(current_user, 'openrouter_api_key', None)

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
        "available_models": len(AVAILABLE_MODELS),
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
