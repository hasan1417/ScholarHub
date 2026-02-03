"""
Smart Agent API - Tiered routing for fast + quality responses
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import time

from app.database import get_db
from app.api.deps import get_current_user, get_current_verified_user
from app.models.user import User
from app.services.smart_agent_service import SmartAgentService
from app.services.smart_agent_service_v2 import SmartAgentServiceV2
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter()

# Toggle between old keyword-based and new tool-based service
USE_TOOL_BASED_AGENT = True  # Set to True to use tool-based orchestration

agent_service = SmartAgentService()
agent_service_v2 = SmartAgentServiceV2()


class AgentChatRequest(BaseModel):
    query: str
    paper_id: Optional[str] = None
    project_id: Optional[str] = None
    document_excerpt: Optional[str] = None  # Current paper content
    reasoning_mode: bool = False  # Use o3-mini for chain-of-thought reasoning
    edit_mode: bool = False  # Allow AI to suggest document edits (requires approval)


class AgentChatResponse(BaseModel):
    response: str
    route_used: str  # "simple", "paper", "research"
    model_used: str
    processing_time_ms: int
    tools_called: List[str] = []


@router.post("/chat")
async def agent_chat(
    request: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user)
):
    """
    Smart agent chat with tiered routing:
    - Simple queries → gpt-4o-mini, no context (~300ms)
    - Paper queries → gpt-4o-mini + doc excerpt (~800ms)
    - Research queries → gpt-4o/gpt-5-mini + RAG (~2-3s)
    """
    # Check subscription limit (shares limit with Discussion AI)
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

    start_time = time.time()

    try:
        result = agent_service.process_query(
            db=db,
            user_id=str(current_user.id),
            query=request.query,
            paper_id=request.paper_id,
            project_id=request.project_id,
            document_excerpt=request.document_excerpt,
            reasoning_mode=request.reasoning_mode
        )

        processing_time = int((time.time() - start_time) * 1000)

        # Increment usage after successful call
        SubscriptionService.increment_usage(db, current_user.id, "discussion_ai_calls")

        return AgentChatResponse(
            response=result["response"],
            route_used=result["route"],
            model_used=result["model"],
            processing_time_ms=processing_time,
            tools_called=result.get("tools_called", [])
        )
    except Exception as e:
        logger.error(f"Agent chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def agent_chat_stream(
    request: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user)
):
    """
    Streaming version of smart agent chat.
    Uses tool-based orchestration (V2) when enabled.
    """
    # Check subscription limit (shares limit with Discussion AI)
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

    try:
        def generate():
            try:
                if USE_TOOL_BASED_AGENT:
                    # V2: Tool-based orchestration - AI decides what action to take
                    for chunk in agent_service_v2.stream_query(
                        db=db,
                        user_id=str(current_user.id),
                        query=request.query,
                        paper_id=request.paper_id,
                        project_id=request.project_id,
                        document_excerpt=request.document_excerpt,
                        reasoning_mode=request.reasoning_mode,
                    ):
                        yield chunk
                else:
                    # V1: Keyword-based routing
                    for chunk in agent_service.stream_query(
                        db=db,
                        user_id=str(current_user.id),
                        query=request.query,
                        paper_id=request.paper_id,
                        project_id=request.project_id,
                        document_excerpt=request.document_excerpt,
                        reasoning_mode=request.reasoning_mode,
                        edit_mode=request.edit_mode
                    ):
                        yield chunk
            finally:
                # Increment usage after streaming
                try:
                    SubscriptionService.increment_usage(db, current_user.id, "discussion_ai_calls")
                except Exception as e:
                    logger.warning(f"Failed to increment usage for user {current_user.id}: {e}")

        return StreamingResponse(
            generate(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "Transfer-Encoding": "chunked",
            }
        )
    except Exception as e:
        logger.error(f"Agent stream error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routes")
async def get_available_routes():
    """Get info about available agent architecture."""
    return {
        "architecture": "tool-based" if USE_TOOL_BASED_AGENT else "keyword-based",
        "model": "gpt-5.2",
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
                "description": "Convert document to a conference format (ACL, IEEE, NeurIPS, AAAI, ICML)",
                "when": "User asks to convert, reformat, or change to a specific conference style"
            }
        ],
        "capabilities": [
            "AI decides which action to take (no keyword matching)",
            "Answer questions about current paper",
            "Use attached references for context",
            "Propose edits with <<<EDIT>>> format",
            "Review and provide structured feedback",
            "Convert between conference formats (ACL, IEEE, NeurIPS, AAAI, ICML, generic)",
            "Reasoning mode for complex analysis"
        ],
        "limitations": [
            "Cannot search for new papers online",
            "Cannot access project library (only paper-attached refs)",
            "For paper discovery, use Discussion AI or Discovery page in project"
        ]
    }
