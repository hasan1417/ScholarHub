import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db
from app.models.research_paper import ResearchPaper
from app.schemas.collab import (
    CollabPersistRequest,
    CollabPersistResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _resolve_secret(provided: str | None) -> None:
    expected = settings.COLLAB_BOOTSTRAP_SECRET or settings.COLLAB_JWT_SECRET
    if not expected or not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid collaboration bootstrap secret",
        )


def _load_paper(db: Session, paper_id: UUID | str) -> ResearchPaper:
    paper = (
        db.query(ResearchPaper)
        .filter(ResearchPaper.id == paper_id)
        .first()
    )
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return paper


def _extract_latex_payload(paper: ResearchPaper) -> Dict[str, Any]:
    latex_source = ""
    content_json: Dict[str, Any] | None = None

    if isinstance(paper.content_json, dict):
        content_json = dict(paper.content_json)
        if content_json.get("authoring_mode") == "latex":
            candidate = content_json.get("latex_source")
            if isinstance(candidate, str):
                latex_source = candidate
    if not latex_source:
        if isinstance(paper.content, str):
            latex_source = paper.content
        elif isinstance(paper.content_json, dict):
            candidate = paper.content_json.get("content")
            if isinstance(candidate, str):
                latex_source = candidate

    # Include extra .tex files if present
    latex_files: Dict[str, str] = {}
    if isinstance(paper.latex_files, dict):
        latex_files = {k: v for k, v in paper.latex_files.items() if isinstance(v, str)}

    return {
        "paper_id": str(paper.id),
        "latex_source": latex_source,
        "latex_files": latex_files,
        "content_json": content_json,
        "updated_at": paper.updated_at.isoformat() if getattr(paper, "updated_at", None) else None,
    }


@router.get("/collab/bootstrap/{paper_id}")
def get_collab_bootstrap_payload(
    paper_id: str,
    collab_secret: str | None = Header(default=None, alias="X-Collab-Secret"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Internal endpoint used by the collaboration service to hydrate realtime documents.
    Requires a shared secret delivered via X-Collab-Secret header.
    """
    _resolve_secret(collab_secret)
    paper = _load_paper(db, paper_id)
    payload = _extract_latex_payload(paper)
    return payload


@router.post("/collab/persist/{paper_id}", response_model=CollabPersistResponse)
def persist_collab_document_state(
    paper_id: str,
    data: CollabPersistRequest,
    collab_secret: str | None = Header(default=None, alias="X-Collab-Secret"),
    db: Session = Depends(get_db),
) -> CollabPersistResponse:
    """
    Internal endpoint used by the collaboration service to persist live LaTeX state.

    This updates only content_json.latex_source and paper.updated_at.
    """
    _resolve_secret(collab_secret)
    paper = _load_paper(db, paper_id)

    content_json = dict(paper.content_json) if isinstance(paper.content_json, dict) else {}
    content_json["latex_source"] = data.latex_source
    paper.content_json = content_json
    paper.updated_at = datetime.now(timezone.utc)

    # Persist extra files if provided
    if data.latex_files:
        paper.latex_files = data.latex_files

    db.commit()

    file_count = len(data.latex_files) if data.latex_files else 0
    logger.info(
        "Persisted collab state for paper %s (main=%s chars, files=%s)",
        paper_id,
        len(data.latex_source),
        file_count,
    )

    return CollabPersistResponse(ok=True)


@router.get("/collab/state/{paper_id}")
def get_collab_document_state(
    paper_id: str,
    collab_secret: str | None = Header(default=None, alias="X-Collab-Secret"),
) -> Dict[str, str]:
    """Placeholder endpoint until the collaboration service exposes live document state."""
    _resolve_secret(collab_secret)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Live collab state is not available for paper {paper_id}",
    )
