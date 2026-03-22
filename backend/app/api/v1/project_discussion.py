"""Discussion API — split into submodules under discussion/"""
from app.api.v1.discussion import router  # noqa: F401

__all__ = ["router"]
