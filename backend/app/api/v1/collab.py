from datetime import datetime, timedelta
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.database import get_db
from app.models.paper_member import PaperMember
from app.models.research_paper import ResearchPaper
from app.models.user import User
from app.services.paper_membership_service import ensure_paper_membership_for_project_member

router = APIRouter()


def _ensure_realtime_enabled() -> None:
    if not settings.PROJECT_COLLAB_REALTIME_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Realtime collaboration is disabled",
        )


def _get_research_paper(db: Session, paper_id: UUID) -> ResearchPaper:
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return paper


def _assert_membership(db: Session, paper: ResearchPaper, user: User) -> None:
    if paper.owner_id == user.id:
        return

    membership = (
        db.query(PaperMember)
        .filter(
            PaperMember.paper_id == paper.id,
            PaperMember.user_id == user.id,
            PaperMember.status == "accepted",
        )
        .first()
    )
    if membership:
        return

    ensured = ensure_paper_membership_for_project_member(db, paper, user)
    if ensured:
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Paper access denied")


def _ensure_latex_authoring(paper: ResearchPaper) -> None:
    json_mode = None
    if isinstance(paper.content_json, dict):
        json_mode = paper.content_json.get("authoring_mode")

    is_latex_format = (paper.format or "").lower() == "latex"

    if not (is_latex_format or json_mode == "latex"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Realtime collaboration is available only for LaTeX papers",
        )


@router.post("/token")
def mint_collab_token(
    paper_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_realtime_enabled()

    paper = _get_research_paper(db, paper_id)
    _ensure_latex_authoring(paper)
    _assert_membership(db, paper, current_user)

    secret = settings.COLLAB_JWT_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Collaboration secret not configured",
        )

    now = datetime.utcnow()
    expiry_seconds = settings.COLLAB_JWT_EXPIRE_SECONDS
    full_name = ' '.join(filter(None, [getattr(current_user, 'first_name', None), getattr(current_user, 'last_name', None)])).strip()
    display_name = full_name or getattr(current_user, 'email', 'Collaborator')

    payload = {
        "paperId": str(paper.id),
        "userId": str(current_user.id),
        "displayName": display_name,
        "color": None,
        "roles": settings.COLLAB_DEFAULT_ROLES,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expiry_seconds)).timestamp()),
        "iss": settings.PROJECT_NAME,
    }

    token = jwt.encode(payload, secret, algorithm=settings.COLLAB_JWT_ALGORITHM)

    return {
        "token": token,
        "expires_in": expiry_seconds,
        "ws_url": settings.COLLAB_WS_URL,
    }
