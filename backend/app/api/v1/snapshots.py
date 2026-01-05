"""
Snapshots API - Overleaf-style document history feature.

Provides endpoints for:
- Creating manual snapshots
- Listing snapshots for a paper
- Getting snapshot details
- Computing diffs between snapshots
- Restoring to a snapshot
- Internal auto-snapshot endpoint for collab server
"""

import base64
import difflib
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.models import DocumentSnapshot, ResearchPaper, User, PaperMember

from app.schemas.snapshot import (
    SnapshotCreate,
    SnapshotAutoCreate,
    SnapshotUpdate,
    SnapshotResponse,
    SnapshotDetailResponse,
    SnapshotListResponse,
    SnapshotDiffResponse,
    SnapshotRestoreResponse,
    DiffLine,
    DiffStats,
)

router = APIRouter()


def _resolve_collab_secret(provided: str | None) -> None:
    """Validate collab server secret for internal endpoints."""
    expected = settings.COLLAB_BOOTSTRAP_SECRET or settings.COLLAB_JWT_SECRET
    if not expected or not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid collaboration secret",
        )


def _check_paper_access(db: Session, paper_id: UUID, user: User) -> ResearchPaper:
    """Check if user has access to the paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Check if user is owner or member
    if paper.owner_id != user.id:
        membership = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == user.id
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Not authorized to access this paper")

    return paper


def _get_next_sequence_number(db: Session, paper_id: UUID) -> int:
    """Get the next sequence number for a paper's snapshots."""
    max_seq = db.query(func.max(DocumentSnapshot.sequence_number)).filter(
        DocumentSnapshot.paper_id == paper_id
    ).scalar()
    return (max_seq or 0) + 1


def _compute_diff(text1: str, text2: str) -> tuple[List[DiffLine], DiffStats]:
    """Compute a line-by-line diff between two texts."""
    lines1 = (text1 or "").splitlines(keepends=True)
    lines2 = (text2 or "").splitlines(keepends=True)

    diff_lines: List[DiffLine] = []
    additions = 0
    deletions = 0
    unchanged = 0

    differ = difflib.unified_diff(lines1, lines2, lineterm="")

    # Skip the header lines (---, +++, @@)
    line_num_old = 0
    line_num_new = 0

    for line in differ:
        if line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("@@"):
            # Parse line numbers from @@ -start,count +start,count @@
            import re
            match = re.match(r"@@ -(\d+)", line)
            if match:
                line_num_old = int(match.group(1))
                line_num_new = line_num_old
            continue
        elif line.startswith("-"):
            diff_lines.append(DiffLine(
                type="deleted",
                content=line[1:].rstrip("\n"),
                line_number=line_num_old
            ))
            deletions += 1
            line_num_old += 1
        elif line.startswith("+"):
            diff_lines.append(DiffLine(
                type="added",
                content=line[1:].rstrip("\n"),
                line_number=line_num_new
            ))
            additions += 1
            line_num_new += 1
        else:
            # Context line (starts with space)
            diff_lines.append(DiffLine(
                type="unchanged",
                content=line[1:].rstrip("\n") if line.startswith(" ") else line.rstrip("\n"),
                line_number=line_num_new
            ))
            unchanged += 1
            line_num_old += 1
            line_num_new += 1

    stats = DiffStats(additions=additions, deletions=deletions, unchanged=unchanged)
    return diff_lines, stats


def _snapshot_to_response(snapshot: DocumentSnapshot) -> SnapshotResponse:
    """Convert a snapshot model to response schema."""
    return SnapshotResponse(
        id=snapshot.id,
        paper_id=snapshot.paper_id,
        snapshot_type=snapshot.snapshot_type,
        label=snapshot.label,
        created_by=snapshot.created_by,
        created_at=snapshot.created_at,
        sequence_number=snapshot.sequence_number,
        text_length=snapshot.text_length,
    )


# ─────────────────────────────────────────────────────────────────────────────
# User-facing endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/papers/{paper_id}/snapshots", response_model=SnapshotResponse)
def create_manual_snapshot(
    paper_id: UUID,
    data: SnapshotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a manual snapshot of the current document state."""
    paper = _check_paper_access(db, paper_id, current_user)

    # Get current document content from paper
    latex_source = ""
    if isinstance(paper.content_json, dict):
        latex_source = paper.content_json.get("latex_source", "")
    if not latex_source and paper.content:
        latex_source = paper.content

    # For manual snapshots, we need to get the current Yjs state
    # This would typically come from the collab server
    # For now, we'll store an empty Yjs state and rely on materialized_text
    yjs_state = b""  # Placeholder - collab server will provide real state

    snapshot = DocumentSnapshot(
        paper_id=paper_id,
        yjs_state=yjs_state,
        materialized_text=latex_source,
        snapshot_type="manual",
        label=data.label,
        created_by=current_user.id,
        sequence_number=_get_next_sequence_number(db, paper_id),
        text_length=len(latex_source) if latex_source else 0,
    )

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return _snapshot_to_response(snapshot)


@router.get("/papers/{paper_id}/snapshots", response_model=SnapshotListResponse)
def list_snapshots(
    paper_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    snapshot_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all snapshots for a paper, newest first."""
    _check_paper_access(db, paper_id, current_user)

    query = db.query(DocumentSnapshot).filter(DocumentSnapshot.paper_id == paper_id)

    if snapshot_type:
        query = query.filter(DocumentSnapshot.snapshot_type == snapshot_type)

    total = query.count()

    snapshots = query.order_by(desc(DocumentSnapshot.created_at)).offset(skip).limit(limit).all()

    return SnapshotListResponse(
        snapshots=[_snapshot_to_response(s) for s in snapshots],
        total=total,
        has_more=(skip + len(snapshots)) < total,
    )


@router.get("/papers/{paper_id}/snapshots/{snapshot_id}", response_model=SnapshotDetailResponse)
def get_snapshot(
    paper_id: UUID,
    snapshot_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific snapshot with its content."""
    _check_paper_access(db, paper_id, current_user)

    snapshot = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == snapshot_id,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return SnapshotDetailResponse(
        id=snapshot.id,
        paper_id=snapshot.paper_id,
        snapshot_type=snapshot.snapshot_type,
        label=snapshot.label,
        created_by=snapshot.created_by,
        created_at=snapshot.created_at,
        sequence_number=snapshot.sequence_number,
        text_length=snapshot.text_length,
        materialized_text=snapshot.materialized_text,
    )


@router.put("/papers/{paper_id}/snapshots/{snapshot_id}", response_model=SnapshotResponse)
def update_snapshot_label(
    paper_id: UUID,
    snapshot_id: UUID,
    data: SnapshotUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a snapshot's label."""
    _check_paper_access(db, paper_id, current_user)

    snapshot = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == snapshot_id,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    if data.label is not None:
        snapshot.label = data.label

    db.commit()
    db.refresh(snapshot)

    return _snapshot_to_response(snapshot)


@router.delete("/papers/{paper_id}/snapshots/{snapshot_id}")
def delete_snapshot(
    paper_id: UUID,
    snapshot_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a snapshot."""
    _check_paper_access(db, paper_id, current_user)

    snapshot = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == snapshot_id,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    db.delete(snapshot)
    db.commit()

    return {"message": "Snapshot deleted"}


@router.get(
    "/papers/{paper_id}/snapshots/{snapshot_id1}/diff/{snapshot_id2}",
    response_model=SnapshotDiffResponse,
)
def get_snapshot_diff(
    paper_id: UUID,
    snapshot_id1: UUID,
    snapshot_id2: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute diff between two snapshots."""
    _check_paper_access(db, paper_id, current_user)

    snapshot1 = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == snapshot_id1,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    snapshot2 = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == snapshot_id2,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    if not snapshot1 or not snapshot2:
        raise HTTPException(status_code=404, detail="One or both snapshots not found")

    diff_lines, stats = _compute_diff(
        snapshot1.materialized_text or "",
        snapshot2.materialized_text or "",
    )

    return SnapshotDiffResponse(
        from_snapshot=_snapshot_to_response(snapshot1),
        to_snapshot=_snapshot_to_response(snapshot2),
        diff_lines=diff_lines,
        stats=stats,
    )


@router.post(
    "/papers/{paper_id}/snapshots/{snapshot_id}/restore",
    response_model=SnapshotRestoreResponse,
)
def restore_snapshot(
    paper_id: UUID,
    snapshot_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Restore the document to a snapshot's state.

    This creates a new 'restore' snapshot and updates the paper content.
    The frontend is responsible for updating the Yjs document.
    """
    paper = _check_paper_access(db, paper_id, current_user)

    snapshot = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == snapshot_id,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Create a restore snapshot to mark this point in history
    restore_snapshot = DocumentSnapshot(
        paper_id=paper_id,
        yjs_state=snapshot.yjs_state,
        materialized_text=snapshot.materialized_text,
        snapshot_type="restore",
        label=f"Restored from snapshot #{snapshot.sequence_number}",
        created_by=current_user.id,
        sequence_number=_get_next_sequence_number(db, paper_id),
        text_length=snapshot.text_length,
    )

    db.add(restore_snapshot)

    # Update paper content
    if isinstance(paper.content_json, dict):
        paper.content_json = {
            **paper.content_json,
            "latex_source": snapshot.materialized_text or "",
        }
    else:
        paper.content = snapshot.materialized_text or ""

    db.commit()
    db.refresh(restore_snapshot)

    return SnapshotRestoreResponse(
        message="Document restored successfully",
        snapshot_id=restore_snapshot.id,
        restored_at=restore_snapshot.created_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal endpoint for collab server
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/papers/{paper_id}/snapshots/auto", response_model=SnapshotResponse)
def create_auto_snapshot(
    paper_id: UUID,
    data: SnapshotAutoCreate,
    collab_secret: str | None = Header(default=None, alias="X-Collab-Secret"),
    db: Session = Depends(get_db),
):
    """
    Internal endpoint for collab server to create auto-snapshots.

    Requires X-Collab-Secret header for authentication.
    """
    _resolve_collab_secret(collab_secret)

    # Verify paper exists
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Decode Yjs state from base64
    try:
        yjs_state = base64.b64decode(data.yjs_state_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 Yjs state")

    snapshot = DocumentSnapshot(
        paper_id=paper_id,
        yjs_state=yjs_state,
        materialized_text=data.materialized_text,
        snapshot_type=data.snapshot_type,
        label=None,
        created_by=None,  # Auto snapshots have no specific creator
        sequence_number=_get_next_sequence_number(db, paper_id),
        text_length=len(data.materialized_text) if data.materialized_text else 0,
    )

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return _snapshot_to_response(snapshot)
