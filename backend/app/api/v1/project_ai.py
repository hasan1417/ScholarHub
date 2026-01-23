from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.config import settings
from app.database import get_db
from app.models import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    ProjectRole,
    ResearchPaper,
    User,
)
from app.services.ai_service import AIService
from app.services.project_ai_service import ProjectAIOrchestrator


router = APIRouter()
_ai_service = AIService()
_ai_orchestrator = ProjectAIOrchestrator(_ai_service)


def _guard_feature() -> None:
    if not settings.PROJECT_AI_ORCHESTRATION_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI orchestration disabled")


class ArtifactCreatePayload(BaseModel):
    type: AIArtifactType
    payload: dict = Field(default_factory=dict)
    paper_id: Optional[UUID] = None


class ArtifactStatusUpdate(BaseModel):
    status: AIArtifactStatus
    payload: Optional[dict] = None


class ArtifactGeneratePayload(BaseModel):
    type: AIArtifactType
    paper_id: Optional[UUID] = None
    focus: Optional[str] = Field(default=None, description="Optional focus or custom instruction")


def _serialize_artifact(artifact: AIArtifact) -> dict:
    return {
        "id": str(artifact.id),
        "type": artifact.type.value,
        "status": artifact.status.value,
        "project_id": str(artifact.project_id) if artifact.project_id else None,
        "paper_id": str(artifact.paper_id) if artifact.paper_id else None,
        "payload": artifact.payload,
        "created_by": str(artifact.created_by) if artifact.created_by else None,
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else None,
    }


@router.post("/projects/{project_id}/ai/artifacts", status_code=status.HTTP_201_CREATED)
def create_ai_artifact(
    project_id: str,
    body: ArtifactCreatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    paper_id = body.paper_id
    if paper_id:
        paper = (
            db.query(ResearchPaper)
            .filter(
                ResearchPaper.id == paper_id,
                ResearchPaper.project_id == project.id,
            )
            .first()
        )
        if not paper:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found in project")

    artifact = AIArtifact(
        project_id=project.id,
        paper_id=paper_id,
        type=body.type,
        payload=body.payload,
        status=AIArtifactStatus.QUEUED,
        created_by=current_user.id,
    )
    db.add(artifact)
    db.flush()

    db.commit()
    db.refresh(artifact)
    return _serialize_artifact(artifact)


@router.post("/projects/{project_id}/ai/artifacts/generate", status_code=status.HTTP_201_CREATED)
def generate_ai_artifact(
    project_id: str,
    body: ArtifactGeneratePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    paper = None
    if body.paper_id:
        paper = (
            db.query(ResearchPaper)
            .filter(
                ResearchPaper.id == body.paper_id,
                ResearchPaper.project_id == project.id,
            )
            .first()
        )
        if not paper:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found in project")

    artifact = _ai_orchestrator.generate_artifact(
        db,
        project,
        current_user,
        body.type,
        paper=paper,
        focus=body.focus,
    )

    return _serialize_artifact(artifact)


@router.get("/projects/{project_id}/ai/artifacts")
def list_ai_artifacts(
    project_id: str,
    status_filter: Optional[AIArtifactStatus] = None,
    paper_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    query = db.query(AIArtifact).filter(AIArtifact.project_id == project.id)
    if paper_id:
        query = query.filter(AIArtifact.paper_id == paper_id)
    if status_filter:
        query = query.filter(AIArtifact.status == status_filter)

    artifacts = query.order_by(AIArtifact.created_at.desc()).all()
    return {
        "project_id": str(project.id),
        "artifacts": [_serialize_artifact(artifact) for artifact in artifacts],
    }


@router.post("/projects/{project_id}/ai/artifacts/{artifact_id}/status")
def update_artifact_status(
    project_id: str,
    artifact_id: UUID,
    body: ArtifactStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    artifact = (
        db.query(AIArtifact)
        .filter(
            AIArtifact.id == artifact_id,
            AIArtifact.project_id == project.id,
        )
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    artifact.status = body.status
    if body.payload is not None:
        artifact.payload = body.payload
    db.commit()
    db.refresh(artifact)
    return _serialize_artifact(artifact)
