"""
Smart Agent API - Tiered routing for fast + quality responses
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import time

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services.smart_agent_service import SmartAgentService

logger = logging.getLogger(__name__)

router = APIRouter()
agent_service = SmartAgentService()


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
    current_user: User = Depends(get_current_user)
):
    """
    Smart agent chat with tiered routing:
    - Simple queries → gpt-4o-mini, no context (~300ms)
    - Paper queries → gpt-4o-mini + doc excerpt (~800ms)
    - Research queries → gpt-4o/gpt-5-mini + RAG (~2-3s)
    """
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
    current_user: User = Depends(get_current_user)
):
    """
    Streaming version of smart agent chat.
    First yields route info, then streams response.
    """
    try:
        def generate():
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
    """Get info about available agent routes for debugging."""
    return {
        "routes": [
            {
                "name": "simple",
                "description": "Greetings, help, simple questions",
                "model": "gpt-4o-mini",
                "context": "none",
                "expected_latency": "~300ms"
            },
            {
                "name": "paper",
                "description": "Questions about user's draft/paper",
                "model": "gpt-4o-mini",
                "context": "document_excerpt",
                "expected_latency": "~800ms"
            },
            {
                "name": "research",
                "description": "Reference questions, literature queries",
                "model": "gpt-4o",
                "context": "RAG + references",
                "expected_latency": "~2-3s"
            }
        ],
        "tools": [
            "search_references",
            "get_reference_summary",
            "expand_text",
            "rephrase_text"
        ]
    }
