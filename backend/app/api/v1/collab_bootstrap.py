from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db
from app.models.research_paper import ResearchPaper

router = APIRouter()


def _resolve_secret(provided: str | None) -> None:
    expected = settings.COLLAB_BOOTSTRAP_SECRET or settings.COLLAB_JWT_SECRET
    if not expected or not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid collaboration bootstrap secret",
        )


def _load_paper(db: Session, paper_id: UUID) -> ResearchPaper:
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

    return {
        "paper_id": str(paper.id),
        "latex_source": latex_source,
        "content_json": content_json,
        "updated_at": paper.updated_at.isoformat() if getattr(paper, "updated_at", None) else None,
    }


@router.get("/collab/bootstrap/{paper_id}")
def get_collab_bootstrap_payload(
    paper_id: UUID,
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
