from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.database import get_db
from app.models import (
    ProjectDiscussionChannel,
    ProjectRole,
    User,
    DiscussionArtifact,
)
from app.schemas.project_discussion import (
    DiscussionArtifactDownloadResponse,
    DiscussionArtifactResponse,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/discussion/channels/{channel_id}/artifacts",
    response_model=List[DiscussionArtifactResponse],
)
async def list_channel_artifacts(
    project_id: str,
    channel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all artifacts for a channel."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    # Verify channel belongs to project
    channel = db.query(ProjectDiscussionChannel).filter(
        ProjectDiscussionChannel.id == channel_id,
        ProjectDiscussionChannel.project_id == project_id,
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    artifacts = db.query(DiscussionArtifact).filter(
        DiscussionArtifact.channel_id == channel_id
    ).order_by(DiscussionArtifact.created_at.desc()).all()

    return [
        DiscussionArtifactResponse(
            id=str(a.id),
            title=a.title,
            filename=a.filename,
            format=a.format.value if hasattr(a.format, 'value') else str(a.format),
            artifact_type=a.artifact_type,
            mime_type=a.mime_type,
            file_size=a.file_size,
            created_at=a.created_at,
            created_by=str(a.created_by) if a.created_by else None,
        )
        for a in artifacts
    ]


@router.get(
    "/projects/{project_id}/discussion/channels/{channel_id}/artifacts/{artifact_id}",
    response_model=DiscussionArtifactDownloadResponse,
)
async def get_artifact(
    project_id: str,
    channel_id: UUID,
    artifact_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get artifact content for download."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    artifact = db.query(DiscussionArtifact).filter(
        DiscussionArtifact.id == artifact_id,
        DiscussionArtifact.channel_id == channel_id,
    ).first()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return DiscussionArtifactDownloadResponse(
        id=str(artifact.id),
        title=artifact.title,
        filename=artifact.filename,
        content_base64=artifact.content_base64,
        mime_type=artifact.mime_type,
    )


@router.delete(
    "/projects/{project_id}/discussion/channels/{channel_id}/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_artifact(
    project_id: str,
    channel_id: UUID,
    artifact_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an artifact."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    artifact = db.query(DiscussionArtifact).filter(
        DiscussionArtifact.id == artifact_id,
        DiscussionArtifact.channel_id == channel_id,
    ).first()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    db.delete(artifact)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
