from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID


class SnapshotCreate(BaseModel):
    """Request to create a manual snapshot."""
    label: Optional[str] = Field(None, max_length=255, description="Optional label for this snapshot")


class SnapshotAutoCreate(BaseModel):
    """Request to create an auto-snapshot from collab server."""
    yjs_state_base64: str = Field(..., description="Base64-encoded Yjs state")
    materialized_text: str = Field(..., description="Materialized LaTeX text")
    snapshot_type: Literal["auto", "manual", "restore"] = Field("auto")


class SnapshotUpdate(BaseModel):
    """Request to update snapshot label."""
    label: Optional[str] = Field(None, max_length=255, description="New label for snapshot")


class SnapshotResponse(BaseModel):
    """Single snapshot response."""
    id: UUID
    paper_id: UUID
    snapshot_type: str
    label: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    sequence_number: int
    text_length: Optional[int] = None

    class Config:
        from_attributes = True


class SnapshotDetailResponse(SnapshotResponse):
    """Snapshot with content included."""
    materialized_text: Optional[str] = None


class SnapshotListResponse(BaseModel):
    """Paginated list of snapshots."""
    snapshots: List[SnapshotResponse]
    total: int
    has_more: bool


class DiffLine(BaseModel):
    """Single line in a diff."""
    type: Literal["added", "deleted", "unchanged"]
    content: str
    line_number: Optional[int] = None


class DiffStats(BaseModel):
    """Statistics about a diff."""
    additions: int
    deletions: int
    unchanged: int


class SnapshotDiffResponse(BaseModel):
    """Diff between two snapshots."""
    from_snapshot: SnapshotResponse
    to_snapshot: SnapshotResponse
    diff_lines: List[DiffLine]
    stats: DiffStats


class SnapshotRestoreResponse(BaseModel):
    """Response after restoring a snapshot."""
    message: str
    snapshot_id: UUID
    restored_at: datetime
