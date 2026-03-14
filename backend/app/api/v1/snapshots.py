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
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import httpx

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.models import DocumentSnapshot, ResearchPaper, User, PaperMember
from app.schemas.collab import CollabStateResponse

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
from app.services.paper_service import compute_snapshot_content_hash

router = APIRouter()
logger = logging.getLogger(__name__)
SNAPSHOT_SEQUENCE_RETRY_COUNT = 3


def _resolve_collab_secret(provided: str | None) -> None:
    """Validate collab server secret for internal endpoints."""
    expected = settings.COLLAB_BOOTSTRAP_SECRET or settings.COLLAB_JWT_SECRET
    if not expected or not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid collaboration secret",
        )


def _check_paper_access(db: Session, paper_id: UUID | str, user: User) -> ResearchPaper:
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


def _is_snapshot_sequence_conflict(exc: IntegrityError) -> bool:
    """Return True when the paper+sequence unique constraint was hit."""
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == "uq_document_snapshots_paper_sequence":
        return True

    message = str(exc.orig)
    return "uq_document_snapshots_paper_sequence" in message or (
        "document_snapshots" in message and "sequence_number" in message
    )


def _create_snapshot_with_retry(
    db: Session,
    *,
    paper_id: UUID,
    yjs_state: bytes,
    materialized_text: Optional[str],
    materialized_files: Optional[dict[str, str]],
    snapshot_type: str,
    label: Optional[str],
    created_by: Optional[UUID],
) -> DocumentSnapshot:
    """Create a snapshot, retrying sequence allocation on concurrent inserts."""
    text_length = len(materialized_text) if materialized_text is not None else 0
    content_hash = compute_snapshot_content_hash(materialized_text, materialized_files)

    last_error: Optional[IntegrityError] = None
    for attempt in range(SNAPSHOT_SEQUENCE_RETRY_COUNT):
        snapshot = DocumentSnapshot(
            paper_id=paper_id,
            yjs_state=yjs_state,
            materialized_text=materialized_text,
            materialized_files=materialized_files,
            snapshot_type=snapshot_type,
            label=label,
            created_by=created_by,
            sequence_number=_get_next_sequence_number(db, paper_id),
            text_length=text_length,
            content_hash=content_hash,
        )

        try:
            with db.begin_nested():
                db.add(snapshot)
                db.flush()
            return snapshot
        except IntegrityError as exc:
            last_error = exc
            if not _is_snapshot_sequence_conflict(exc) or attempt == SNAPSHOT_SEQUENCE_RETRY_COUNT - 1:
                raise
            logger.info(
                "Retrying snapshot creation for paper %s after sequence conflict (attempt %s/%s)",
                paper_id,
                attempt + 1,
                SNAPSHOT_SEQUENCE_RETRY_COUNT,
            )

    if last_error:
        raise last_error

    raise RuntimeError("Snapshot creation failed without a captured error")


def _collab_state_headers() -> Optional[dict[str, str]]:
    """Build the shared-secret headers for internal collab service calls."""
    secret = settings.COLLAB_BOOTSTRAP_SECRET or settings.COLLAB_JWT_SECRET
    if not secret:
        return None
    return {"X-Collab-Secret": secret}


def _fetch_live_collab_state(paper_id: str) -> tuple[str, bytes] | None:
    """Fetch the current live document state from the collab service if available."""
    headers = _collab_state_headers()
    if not headers:
        logger.debug("Skipping collab live state fetch for paper %s because no collab secret is configured", paper_id)
        return None

    endpoint = f"{settings.COLLAB_SERVER_URL.rstrip('/')}/documents/{paper_id}/state"

    try:
        with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
            response = client.get(endpoint, headers=headers)

        if response.status_code == status.HTTP_404_NOT_FOUND:
            logger.debug("No live collab state available for paper %s", paper_id)
            return None

        response.raise_for_status()
        payload = CollabStateResponse.model_validate(response.json())

        encoded_yjs_state = payload.yjs_state_base64
        if encoded_yjs_state is None:
            encoded_yjs_state = payload.yjs_state
        if encoded_yjs_state is None:
            raise ValueError("Collab live state response is missing yjs_state")

        return payload.materialized_text, base64.b64decode(encoded_yjs_state, validate=True)
    except httpx.RequestError as exc:
        logger.warning("Failed to fetch live collab state for paper %s: %s", paper_id, exc)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Collab live state lookup failed for paper %s with status %s",
            paper_id,
            exc.response.status_code,
        )
    except ValueError as exc:
        logger.warning("Invalid collab live state payload for paper %s: %s", paper_id, exc)

    return None


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


def _compute_full_diff(text1: str, text2: str) -> tuple[List[DiffLine], DiffStats]:
    """Compute a full-document line diff between two texts."""
    lines1 = (text1 or "").splitlines()
    lines2 = (text2 or "").splitlines()

    diff_lines: List[DiffLine] = []
    additions = 0
    deletions = 0
    unchanged = 0

    matcher = difflib.SequenceMatcher(a=lines1, b=lines2)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset, line in enumerate(lines2[j1:j2], start=j1 + 1):
                diff_lines.append(DiffLine(
                    type="unchanged",
                    content=line,
                    line_number=offset,
                ))
                unchanged += 1
        elif tag == "delete":
            for offset, line in enumerate(lines1[i1:i2], start=i1 + 1):
                diff_lines.append(DiffLine(
                    type="deleted",
                    content=line,
                    line_number=offset,
                ))
                deletions += 1
        elif tag == "insert":
            for offset, line in enumerate(lines2[j1:j2], start=j1 + 1):
                diff_lines.append(DiffLine(
                    type="added",
                    content=line,
                    line_number=offset,
                ))
                additions += 1
        elif tag == "replace":
            for offset, line in enumerate(lines1[i1:i2], start=i1 + 1):
                diff_lines.append(DiffLine(
                    type="deleted",
                    content=line,
                    line_number=offset,
                ))
                deletions += 1
            for offset, line in enumerate(lines2[j1:j2], start=j1 + 1):
                diff_lines.append(DiffLine(
                    type="added",
                    content=line,
                    line_number=offset,
                ))
                additions += 1

    stats = DiffStats(additions=additions, deletions=deletions, unchanged=unchanged)
    return diff_lines, stats


def _get_snapshot_materialized_content(snapshot: DocumentSnapshot, file: Optional[str] = None) -> str:
    """Return snapshot content for the requested file."""
    if file is None:
        return snapshot.materialized_text or ""

    if not isinstance(snapshot.materialized_files, dict):
        return ""

    file_content = snapshot.materialized_files.get(file)
    return file_content if isinstance(file_content, str) else ""


def _snapshot_to_response(
    snapshot: DocumentSnapshot,
    *,
    include_content: bool = False,
) -> SnapshotResponse | SnapshotDetailResponse:
    """Convert a snapshot model to response schema."""
    response_data = {
        "id": snapshot.id,
        "paper_id": snapshot.paper_id,
        "snapshot_type": snapshot.snapshot_type,
        "label": snapshot.label,
        "created_by": snapshot.created_by,
        "created_at": snapshot.created_at,
        "sequence_number": snapshot.sequence_number,
        "text_length": snapshot.text_length,
    }

    if include_content:
        return SnapshotDetailResponse(
            **response_data,
            materialized_text=snapshot.materialized_text,
            materialized_files=snapshot.materialized_files,
        )

    return SnapshotResponse(
        **response_data,
    )


# ─────────────────────────────────────────────────────────────────────────────
# User-facing endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/papers/{paper_id}/snapshots", response_model=SnapshotResponse)
def create_manual_snapshot(
    paper_id: str,
    data: SnapshotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a manual snapshot of the current document state."""
    paper = _check_paper_access(db, paper_id, current_user)

    live_state = _fetch_live_collab_state(paper_id)
    materialized_files = paper.latex_files if isinstance(paper.latex_files, dict) else None
    if live_state is not None:
        latex_source, yjs_state = live_state
    else:
        latex_source = ""
        if isinstance(paper.content_json, dict):
            latex_source = paper.content_json.get("latex_source", "")
        if not latex_source and paper.content:
            latex_source = paper.content
        yjs_state = b""

    snapshot = _create_snapshot_with_retry(
        db,
        paper_id=paper.id,
        yjs_state=yjs_state,
        materialized_text=latex_source,
        materialized_files=materialized_files,
        snapshot_type="manual",
        label=data.label,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(snapshot)

    return _snapshot_to_response(snapshot)


@router.get("/papers/{paper_id}/snapshots", response_model=SnapshotListResponse)
def list_snapshots(
    paper_id: str,
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
    paper_id: str,
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

    return _snapshot_to_response(snapshot, include_content=True)


@router.put("/papers/{paper_id}/snapshots/{snapshot_id}", response_model=SnapshotResponse)
def update_snapshot_label(
    paper_id: str,
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
    paper_id: str,
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
    paper_id: str,
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


@router.get(
    "/papers/{paper_id}/snapshots/{from_id}/full-diff/{to_id}",
    response_model=SnapshotDiffResponse,
)
def get_snapshot_full_diff(
    paper_id: str,
    from_id: UUID,
    to_id: UUID,
    file: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute a full-document diff between two snapshots."""
    _check_paper_access(db, paper_id, current_user)

    snapshot1 = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == from_id,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    snapshot2 = db.query(DocumentSnapshot).filter(
        DocumentSnapshot.id == to_id,
        DocumentSnapshot.paper_id == paper_id,
    ).first()

    if not snapshot1 or not snapshot2:
        raise HTTPException(status_code=404, detail="One or both snapshots not found")

    diff_lines, stats = _compute_full_diff(
        _get_snapshot_materialized_content(snapshot1, file),
        _get_snapshot_materialized_content(snapshot2, file),
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
    paper_id: str,
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
    restore_snapshot = _create_snapshot_with_retry(
        db,
        paper_id=paper.id,
        yjs_state=snapshot.yjs_state,
        materialized_text=snapshot.materialized_text,
        materialized_files=snapshot.materialized_files,
        snapshot_type="restore",
        label=f"Restored from snapshot #{snapshot.sequence_number}",
        created_by=current_user.id,
    )

    # Update paper content
    if isinstance(paper.content_json, dict):
        paper.content_json = {
            **paper.content_json,
            "latex_source": snapshot.materialized_text or "",
        }
    else:
        paper.content = snapshot.materialized_text or ""
    if snapshot.materialized_files is not None:
        paper.latex_files = snapshot.materialized_files

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
    paper_id: str,
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

    snapshot = _create_snapshot_with_retry(
        db,
        paper_id=paper.id,
        yjs_state=yjs_state,
        materialized_text=data.materialized_text,
        materialized_files=data.materialized_files,
        snapshot_type=data.snapshot_type,
        label=None,
        created_by=None,  # Auto snapshots have no specific creator
    )
    db.commit()
    db.refresh(snapshot)

    return _snapshot_to_response(snapshot)
