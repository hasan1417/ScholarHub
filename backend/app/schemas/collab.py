from typing import Dict, Optional

from pydantic import BaseModel, Field


class CollabPersistRequest(BaseModel):
    """Internal request to persist the current LaTeX source and extra files."""
    latex_source: str = Field(..., description="Current materialized LaTeX source (main.tex)")
    latex_files: Optional[Dict[str, str]] = Field(None, description="Extra .tex files: filename -> content")


class CollabPersistResponse(BaseModel):
    """Simple acknowledgement for internal collab persistence."""
    ok: bool = Field(..., description="Whether the persist operation succeeded")


class CollabStateResponse(BaseModel):
    """Current live state returned by the collaboration service."""
    materialized_text: str = Field(..., description="Current materialized LaTeX text")
    yjs_state_base64: Optional[str] = Field(
        None,
        description="Base64-encoded Yjs state update",
    )
    yjs_state: Optional[str] = Field(
        None,
        description="Legacy base64-encoded Yjs state key",
    )
