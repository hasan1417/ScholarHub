"""Discussion API — composed from submodules."""
from fastapi import APIRouter

from .messages import router as messages_router
from .channels import router as channels_router
from .assistant import router as assistant_router
from .tasks import router as tasks_router
from .deep_research import router as deep_research_router

router = APIRouter()
router.include_router(messages_router)
router.include_router(channels_router)
router.include_router(assistant_router)
router.include_router(tasks_router)
router.include_router(deep_research_router)
