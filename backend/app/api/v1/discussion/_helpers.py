"""Shared imports, helpers, and singletons used across discussion submodules."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

import asyncio
import json
import logging
import time

import httpx
import openai
from pydantic import BaseModel, Field

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    Response,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_current_verified_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.security import verify_token
from app.database import SessionLocal, get_db
from app.models import (
    Meeting,
    ProjectDiscussionChannel,
    ProjectDiscussionChannelResource,
    ProjectDiscussionMessage,
    ProjectDiscussionResourceType,
    ProjectDiscussionTask,
    ProjectDiscussionTaskStatus,
    ProjectDiscussionAssistantExchange,
    ProjectReference,
    Reference,
    ProjectRole,
    ResearchPaper,
    User,
)
from app.schemas.project_discussion import (
    DiscussionAssistantRequest,
    DiscussionAssistantResponse,
    DiscussionAssistantExchangeResponse,
    DiscussionChannelCreate,
    DiscussionChannelResourceCreate,
    DiscussionChannelResourceResponse,
    DiscussionChannelSummary,
    DiscussionChannelUpdate,
    DiscussionMessageCreate,
    DiscussionMessageResponse,
    DiscussionMessageUpdate,
    DiscussionStats,
    DiscussionTaskCreate,
    DiscussionTaskResponse,
    DiscussionTaskUpdate,
    DiscussionThreadResponse,
    OpenRouterModelInfo,
    OpenRouterModelListResponse,
)
from app.core.config import settings
from app.services.ai_service import AIService
from app.services.discussion_ai.openrouter_orchestrator import (
    OpenRouterOrchestrator,
    get_available_models_with_meta,
)
from app.api.utils.openrouter_access import resolve_openrouter_key_for_project
from app.api.utils.request_dedup import check_and_set_request
from app.services.websocket_manager import connection_manager
from app.services.subscription_service import SubscriptionService
from app.api.v1.discussion_helpers import (
    slugify as _slugify,
    build_ai_response as _build_ai_response,
    generate_unique_slug as _generate_unique_slug,
    ensure_default_channel as _ensure_default_channel,
    get_channel_or_404 as _get_channel_or_404,
    serialize_message as _serialize_message,
    serialize_channel as _serialize_channel,
    serialize_resource as _serialize_resource,
    serialize_task as _serialize_task,
    parse_task_status as _parse_task_status,
    discussion_session_id as _discussion_session_id,
    display_name_for_user as _display_name_for_user,
    build_assistant_author_payload as _build_assistant_author_payload,
    broadcast_discussion_event as _broadcast_discussion_event,
    persist_assistant_exchange as _persist_assistant_exchange,
)

logger = logging.getLogger(__name__)

_discussion_ai_core = AIService()
