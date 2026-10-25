"""
OpenRouter-Based Discussion AI Orchestrator

Uses OpenRouter API to support multiple AI models (GPT, Claude, Gemini, etc.)
Inherits from ToolOrchestrator and only overrides the AI calling methods.

Key difference from base ToolOrchestrator:
- Streams prose promptly and validates citation-bearing tails before emission
- Shows status messages during tool execution
"""

from __future__ import annotations

import asyncio
from copy import copy, deepcopy
import json
import logging
import os
import queue as stdlib_queue
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

import openai
from openai import APIStatusError, RateLimitError, APIConnectionError, APITimeoutError
import httpx

from app.core.config import settings
from app.services.discussion_ai.tool_orchestrator import MUTATING_TOOLS, ToolOrchestrator
from app.services.discussion_ai.token_utils import count_messages_tokens
from app.services.discussion_ai.utils import filter_duplicate_mutations

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# =============================================================================
# REASONING CONTENT FILTERING (two layers)
# =============================================================================
# Layer 1 (reasoning-capable models): API calls include `reasoning.effort`
#   param so OpenRouter separates reasoning into a dedicated field that we
#   don't read — only applied to models that support it.
#
# Layer 2 (universal safety net): ThinkTagFilter + _THINK_TAG_RE catch any
#   <think>/<thought>/<reasoning>/<reflection> tags that leak into content
#   from any model, whether reasoning-capable or not.
# =============================================================================
_REASONING_TAGS = ("think", "thought", "reasoning", "reflection")

# Some models (DeepSeek, Llama, Qwen) emit tool calls as XML in content
# rather than (or in addition to) using the structured tool_calls API.
_TOOL_CALL_XML_TAGS = ("function_calls", "function_call", "invoke", "tool_call")

_STRIP_TAGS = _REASONING_TAGS + _TOOL_CALL_XML_TAGS

_THINK_TAG_RE = re.compile(
    r"<(?:" + "|".join(_STRIP_TAGS) + r")[\s>].*?</(?:" + "|".join(_STRIP_TAGS) + r")>",
    re.DOTALL,
)
# Catch orphaned closing tags left after nested stripping (e.g. </function_calls>)
_ORPHAN_CLOSE_RE = re.compile(
    r"</(?:" + "|".join(_STRIP_TAGS) + r")>",
)


def _strip_internal_tags(text: str) -> str:
    """Strip reasoning and XML tool-call tags, including orphaned closing tags."""
    text = _THINK_TAG_RE.sub("", text)
    text = _ORPHAN_CLOSE_RE.sub("", text)
    return text.strip()


class _StreamingCitationPrefix:
    """Strip internal tags and emit prose until a citation needs final filtering."""

    def __init__(self) -> None:
        self.text = ""
        self.buffering = False
        self._tags = ThinkTagFilter()

    def feed(self, text: str) -> str:
        if self.buffering:
            return ""
        text = self._tags.feed(text)
        opener = re.search(r"[\\]", text)
        if opener:
            self.buffering = True
            text = text[:opener.start()]
        if not self.text:
            text = text.lstrip()
        self.text += text
        return text


class ThinkTagFilter:
    """Streaming safety-net filter that strips reasoning and XML tool-call blocks.

    Primary defence is the API-level ``reasoning.exclude`` flag.  This filter
    catches anything that still leaks through (new models, API bugs, etc.).
    Handles: <think>, <thought>, <reasoning>, <reflection>,
             <function_calls>, <function_call>, <invoke>, <tool_call>.
    """

    _OPEN_TAGS = tuple(f"<{t}>" for t in _STRIP_TAGS) + tuple(f"<{t} " for t in _STRIP_TAGS)
    _CLOSE_TAGS = tuple(f"</{t}>" for t in _STRIP_TAGS)
    _MAX_CLOSE_LEN = max(len(t) for t in _CLOSE_TAGS)
    _OPEN_RE = re.compile(r"<(?:" + "|".join(_STRIP_TAGS) + r")[\s>]")

    def __init__(self) -> None:
        self._inside_block = False
        self._buffer = ""

    def _find_open_tag(self, text: str) -> tuple[int, int]:
        match = self._OPEN_RE.search(text)
        return (match.start(), match.end() - match.start()) if match else (-1, 0)

    def _find_close_tag(self, text: str) -> tuple[int, int]:
        best_pos, best_len = -1, 0
        for tag in self._CLOSE_TAGS:
            idx = text.find(tag)
            if idx != -1 and (best_pos == -1 or idx < best_pos):
                best_pos, best_len = idx, len(tag)
        return best_pos, best_len

    def feed(self, text: str) -> str:
        """Feed a streaming chunk and return only the visible portion."""
        self._buffer += text
        output_parts: list[str] = []

        while self._buffer:
            if self._inside_block:
                end_idx, end_len = self._find_close_tag(self._buffer)
                if end_idx == -1:
                    if len(self._buffer) > self._MAX_CLOSE_LEN:
                        self._buffer = self._buffer[-self._MAX_CLOSE_LEN:]
                    break
                else:
                    self._buffer = self._buffer[end_idx + end_len:]
                    self._inside_block = False
            else:
                start_idx, start_len = self._find_open_tag(self._buffer)
                close_idx, close_len = self._find_close_tag(self._buffer)
                if close_idx >= 0 and (start_idx == -1 or close_idx < start_idx):
                    output_parts.append(self._buffer[:close_idx])
                    self._buffer = self._buffer[close_idx + close_len:]
                    continue
                if start_idx == -1:
                    # Retain only a suffix that could begin an internal tag;
                    # ordinary prose can be emitted without a fixed delay.
                    possible_tag = self._buffer.rfind("<")
                    safe_end = len(self._buffer)
                    if possible_tag >= 0 and any(
                        tag.startswith(self._buffer[possible_tag:]) for tag in self._OPEN_TAGS + self._CLOSE_TAGS
                    ):
                        safe_end = possible_tag
                    if safe_end > 0:
                        output_parts.append(self._buffer[:safe_end])
                        self._buffer = self._buffer[safe_end:]
                    break
                else:
                    if start_idx > 0:
                        output_parts.append(self._buffer[:start_idx])
                    self._buffer = self._buffer[start_idx + start_len:]
                    self._inside_block = True

        return "".join(output_parts)

    def flush(self) -> str:
        """Flush remaining buffer at end of stream."""
        if self._inside_block:
            self._buffer = ""
            return ""
        remaining = self._buffer
        self._buffer = ""
        return remaining


# =============================================================================
# MODEL CATALOG FALLBACK STRATEGY
# =============================================================================
# When fetching available models, we use a three-tier fallback:
#
# 1. REMOTE: Fetch from OpenRouter API (cached for 24 hours)
#    - Best source: real-time model availability and capabilities
#    - Merged with fallback to ensure known models are always available
#
# 2. FALLBACK FILE: JSON file with curated model list
#    - Path: openrouter_models_fallback.json (or OPENROUTER_FALLBACK_MODELS_PATH env)
#    - Updated periodically with known working models
#    - Used when API is unavailable or no API key configured
#
# 3. BUILTIN: Hardcoded minimal list (last resort)
#    - Only GPT-5.2 and Claude 4.5 Sonnet
#    - Used if fallback file is missing or corrupted
#
# This ensures the model selector always has options, even offline.
# =============================================================================
DEFAULT_FALLBACK_MODELS_PATH = os.path.join(os.path.dirname(__file__), "openrouter_models_fallback.json")
BUILTIN_FALLBACK_MODELS = [
    {"id": "openai/gpt-5.2-20251211", "name": "GPT-5.2", "provider": "OpenAI"},
    {"id": "anthropic/claude-4.5-sonnet-20250929", "name": "Claude 4.5 Sonnet", "provider": "Anthropic"},
]


# Models that support OpenRouter's reasoning parameter
# Based on OpenRouter docs: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
REASONING_SUPPORTED_MODELS = {
    # OpenAI GPT-5+ supports reasoning.effort
    "openai/gpt-5.2-20251211",
    "openai/gpt-5.2-codex-20260114",
    "openai/gpt-5.1-20251113",
    # Anthropic Claude 4.5+ supports extended thinking
    "anthropic/claude-4.5-opus-20251124",
    "anthropic/claude-4.5-sonnet-20250929",
    "anthropic/claude-4.5-haiku-20251001",
    # Google Gemini 2.5+/3.x supports reasoning via thinkingLevel
    "google/gemini-3-pro-preview-20251117",
    "google/gemini-3-flash-preview-20251217",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    # DeepSeek V3+ and R1 support reasoning
    "deepseek/deepseek-v3.2-20251201",
    "deepseek/deepseek-chat-v3.1",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-r1:free",
}

MODEL_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours
REDIS_CACHE_KEY = "openrouter_available_models:v3"
_model_cache: Dict[str, Any] = {"timestamp": 0.0, "models": None}
_redis_client = None
_redis_initialized = False
_fallback_models_cache: Dict[str, Any] = {"path": None, "mtime": None, "models": None}
REASONING_PARAM_KEYS = {
    "reasoning",
    "include_reasoning",
    "reasoning_effort",
    "reasoning_mode",
    "thinking",
    "thinking_level",
}
TOOLS_PARAM_KEYS = {"tools", "tool_choice"}

# Retry configuration for transient API errors
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0

# Recovery retry: action verbs that suggest the user wanted a tool call
_ACTION_SIGNAL = re.compile(
    r"\b(add|find|search|create|write|compare|export|show|focus|tag|update|generate)\b",
    re.IGNORECASE,
)


def _get_redis_client():
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True
    try:
        import redis as redis_lib
        client = redis_lib.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        _redis_client = client
    except Exception:
        _redis_client = None
    return _redis_client


def _provider_display_name(raw_provider: str) -> str:
    if not raw_provider:
        return "Unknown"
    normalized = raw_provider.strip().lower()
    mapping = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
        "deepseek": "DeepSeek",
        "meta": "Meta",
        "meta-llama": "Meta",
        "qwen": "Qwen",
    }
    return mapping.get(normalized, normalized.replace("-", " ").title())


def _normalize_fallback_models(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, dict):
        items = [{"id": model_id, **(info if isinstance(info, dict) else {})} for model_id, info in raw.items()]
    elif isinstance(raw, list):
        items = [item for item in raw if isinstance(item, dict)]
    else:
        return []

    models: List[Dict[str, Any]] = []
    for item in items:
        model_id = item.get("id")
        if not model_id:
            continue
        name = item.get("name") or item.get("display_name") or model_id
        provider = item.get("provider") or item.get("owned_by") or model_id.split("/", 1)[0]
        normalized = {
            "id": model_id,
            "name": name,
            "provider": _provider_display_name(provider),
        }
        if "supports_reasoning" in item:
            normalized["supports_reasoning"] = item.get("supports_reasoning")
        if "supports_tools" in item:
            normalized["supports_tools"] = item.get("supports_tools")
        if "context_length" in item:
            normalized["context_length"] = item.get("context_length")
        models.append(normalized)
    return models


def _load_fallback_models_from_file(path: str) -> Optional[List[Dict[str, Any]]]:
    if not path:
        return None

    try:
        stat = os.stat(path)
    except OSError:
        return None

    cache = _fallback_models_cache
    if cache.get("path") == path and cache.get("mtime") == stat.st_mtime and cache.get("models"):
        return cache["models"]

    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load OpenRouter fallback models from %s: %s", path, exc)
        return None

    models = _normalize_fallback_models(raw)
    if not models:
        return None

    cache["path"] = path
    cache["mtime"] = stat.st_mtime
    cache["models"] = models
    return models


def _fallback_models_with_source(include_reasoning: bool = False) -> tuple[List[Dict[str, Any]], str]:
    fallback_path = settings.OPENROUTER_FALLBACK_MODELS_PATH or DEFAULT_FALLBACK_MODELS_PATH
    models = _load_fallback_models_from_file(fallback_path)
    source = "fallback" if models else "builtin"
    if not models:
        models = _normalize_fallback_models(BUILTIN_FALLBACK_MODELS)
    if include_reasoning:
        for model in models:
            if model.get("supports_reasoning") is None:
                model["supports_reasoning"] = model["id"] in REASONING_SUPPORTED_MODELS
    for model in models:
        model.setdefault("supports_tools", True)
    return models, source


def _fallback_models(include_reasoning: bool = False) -> List[Dict[str, Any]]:
    models, _source = _fallback_models_with_source(include_reasoning=include_reasoning)
    return models


def _get_cached_models() -> Optional[List[Dict[str, Any]]]:
    now = time.time()
    cached_models = _model_cache.get("models")
    cached_at = _model_cache.get("timestamp", 0.0)
    if cached_models and (now - cached_at) < MODEL_CACHE_TTL_SECONDS:
        return cached_models

    client = _get_redis_client()
    if not client:
        return None

    try:
        raw = client.get(REDIS_CACHE_KEY)
        if not raw:
            return None
        models = json.loads(raw)
        if isinstance(models, list) and models:
            _model_cache["models"] = models
            _model_cache["timestamp"] = now
            _sync_context_limits(models)
            return models
    except Exception:
        return None
    return None


def _cache_models(models: List[Dict[str, Any]]) -> None:
    _model_cache["models"] = models
    _model_cache["timestamp"] = time.time()

    client = _get_redis_client()
    if not client:
        return
    try:
        client.setex(REDIS_CACHE_KEY, MODEL_CACHE_TTL_SECONDS, json.dumps(models))
    except Exception:
        pass


def _sync_context_limits(models: List[Dict[str, Any]]) -> None:
    """Push context_length data from model list into token_utils dynamic limits."""
    from app.services.discussion_ai.token_utils import update_context_limits

    limits: Dict[str, int] = {}
    for model in models:
        model_id = model.get("id")
        ctx_len = model.get("context_length")
        if model_id and ctx_len and isinstance(ctx_len, int):
            limits[model_id] = ctx_len
    if limits:
        update_context_limits(limits)
        logger.info("Updated dynamic context limits for %d models", len(limits))


def _fetch_openrouter_models(api_key: Optional[str]) -> List[Dict[str, Any]]:
    headers = {
        "HTTP-Referer": "https://scholarhub.space",
        "X-Title": "ScholarHub",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        return []

    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get("https://openrouter.ai/api/v1/models", headers=headers)
        if resp.status_code != 200:
            logger.warning("OpenRouter models API returned %s", resp.status_code)
            return []
        payload = resp.json() or {}
        items = payload.get("data", [])
        models: List[Dict[str, Any]] = []
        for item in items:
            model_id = item.get("id")
            if not model_id:
                continue
            model_type = item.get("type")
            if model_type and model_type != "chat":
                continue
            name = item.get("name") or item.get("display_name") or model_id
            provider_raw = item.get("provider") or item.get("owned_by") or model_id.split("/", 1)[0]
            provider = _provider_display_name(provider_raw)
            supported_params = item.get("supported_parameters") or []
            supports_reasoning = None
            supports_tools = None
            if isinstance(supported_params, list):
                if any(param in supported_params for param in REASONING_PARAM_KEYS):
                    supports_reasoning = True
                if any(param in supported_params for param in TOOLS_PARAM_KEYS):
                    supports_tools = True
            entry: Dict[str, Any] = {
                "id": model_id,
                "name": name,
                "provider": provider,
                "supports_reasoning": supports_reasoning,
                "supports_tools": supports_tools,
            }
            context_length = item.get("context_length")
            if context_length and isinstance(context_length, (int, float)):
                entry["context_length"] = int(context_length)
            models.append(entry)

        # Push context limits to token_utils for dynamic model awareness
        _sync_context_limits(models)
        return models
    except Exception as exc:
        logger.warning("Failed to fetch OpenRouter models: %s", exc)
        return []


def model_supports_reasoning(model_id: str) -> bool:
    """Check whether a model supports OpenRouter reasoning parameters."""
    cached = _get_cached_models()
    if cached:
        for model in cached:
            if model.get("id") == model_id:
                supports = model.get("supports_reasoning")
                if supports is not None:
                    return bool(supports)
                break
    return model_id in REASONING_SUPPORTED_MODELS


class OpenRouterOrchestrator(ToolOrchestrator):
    """
    AI orchestrator that uses OpenRouter for multi-model support.

    Inherits all tool implementations from ToolOrchestrator,
    only overrides the AI calling methods to use OpenRouter.
    """

    def __init__(
        self,
        ai_service: "AIService",
        db: "Session",
        model: str = "openai/gpt-5.2-20251211",
        user_api_key: Optional[str] = None,
    ):
        super().__init__(ai_service, db)
        self._model = model
        self._reasoning_mode = False  # Set by invoke methods from ctx

        # Initialize OpenRouter client (OpenAI-compatible API)
        # User's API key takes priority over system key
        api_key = user_api_key or settings.OPENROUTER_API_KEY
        self._using_user_key = bool(user_api_key)

        if not api_key:
            logger.warning("OPENROUTER_API_KEY not configured (no user key or system key)")

        # Cap LLM round-trip at 60s. Default SDK timeout is ~10min, which would
        # stall tool-call iterations well past the frontend's 180s axios limit and
        # surface as an opaque network error instead of a retryable backend timeout.
        openrouter_timeout = 60.0

        self.openrouter_client = openai.OpenAI(
            api_key=api_key or "missing-key",
            base_url="https://openrouter.ai/api/v1",
            timeout=openrouter_timeout,
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            }
        ) if api_key else None

        self.async_openrouter_client = openai.AsyncOpenAI(
            api_key=api_key or "missing-key",
            base_url="https://openrouter.ai/api/v1",
            timeout=openrouter_timeout,
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            }
        ) if api_key else None

        if user_api_key:
            logger.info("Using user-provided OpenRouter API key")

    def _get_classifier_client(self):
        """Return sync client for the intent classifier."""
        return self.openrouter_client

    def _model_supports_reasoning(self) -> bool:
        """Check if the current model supports OpenRouter reasoning parameter."""
        return model_supports_reasoning(self._model)

    def _get_reasoning_params(self) -> dict:
        """Get reasoning parameters for the API call.

        Only sends reasoning params to models that support them.
        For models without reasoning support, returns empty dict and
        relies on ThinkTagFilter as safety net for any leaked tags.
        """
        if not self._model_supports_reasoning():
            return {}

        if self._reasoning_mode:
            return {
                "extra_body": {
                    "reasoning": {
                        "effort": "high"
                    }
                }
            }

        # Model supports reasoning but user hasn't enabled reasoning mode.
        # Use effort: "medium" to separate reasoning into the `reasoning`
        # field (which we don't read) instead of mixing into `content`.
        # This keeps reasoning active for quality but hides it from the user.
        # ThinkTagFilter remains as safety net for any tags that leak.
        return {
            "extra_body": {
                "reasoning": {
                    "effort": "medium"
                }
            }
        }

    @property
    def model(self) -> str:
        """Get the current model being used."""
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        """Set the model to use."""
        self._model = value

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable (transient)."""
        if isinstance(error, RateLimitError):
            return True
        if isinstance(error, (APIConnectionError, APITimeoutError)):
            return True
        if isinstance(error, APIStatusError):
            return error.status_code in RETRYABLE_STATUS_CODES
        return False

    @staticmethod
    def _provider_failure_result(
        *,
        retryable: bool,
        status_code: int,
    ) -> Dict[str, Any]:
        """Return an explicit provider failure for the orchestration layer."""
        return {
            "ok": False,
            "error": {
                "code": "provider_unavailable",
                "message": "The AI provider is temporarily unavailable. Please try again.",
                "retryable": retryable,
                "status_code": status_code,
            },
            "content": "",
            "tool_calls": [],
        }

    @staticmethod
    def _is_no_tools_error(error: Exception) -> bool:
        """Check if the error is a 'model doesn't support tools' error from OpenRouter."""
        if isinstance(error, APIStatusError) and error.status_code == 404:
            msg = str(error).lower()
            return "tool use" in msg or "tool_use" in msg or "tools" in msg
        return False

    def _call_ai_with_tools(self, messages: List[Dict], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Call OpenRouter with tool definitions (non-streaming) with retry on transient errors."""
        if not self.openrouter_client:
            return self._provider_failure_result(retryable=False, status_code=502)

        reasoning_info = f" (reasoning: {self._reasoning_mode})" if self._reasoning_mode else ""
        logger.info(f"Calling OpenRouter with model: {self.model}{reasoning_info}")

        # Filter tools based on user's role
        tools = self._get_tools_for_user(ctx)

        # Build API call params
        call_params = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            # Explicit cap so non-streaming tool-chain responses don't get
            # silently clipped at provider defaults.
            "max_tokens": self._get_model_output_token_cap(ctx),
        }

        if not tools:
            call_params.pop("tools")
            call_params.pop("tool_choice")

        # Add reasoning params (always includes exclude or effort)
        reasoning_params = self._get_reasoning_params()
        if reasoning_params.get("extra_body"):
            call_params["extra_body"] = reasoning_params["extra_body"]

        # Retry loop for transient errors
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                messages = self._fit_provider_messages(messages, ctx, tools=call_params.get("tools", []))
                call_params["messages"] = messages
                response = self.openrouter_client.chat.completions.create(**call_params)

                choice = response.choices[0]
                message = choice.message

                result = {
                    "ok": True,
                    "content": _strip_internal_tags(message.content or ""),
                    "tool_calls": [],
                }

                if message.tool_calls:
                    for tc in message.tool_calls:
                        raw_args = tc.function.arguments or "{}"
                        try:
                            parsed_args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            logger.warning(
                                "Malformed tool arguments from model (%s). Using empty args. Raw: %s",
                                tc.function.name,
                                raw_args[:200],
                            )
                            parsed_args = {}
                        result["tool_calls"].append({
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": parsed_args,
                        })

                return result

            except Exception as e:
                # Model doesn't support tools → retry without tools
                if self._is_no_tools_error(e):
                    logger.warning(f"Model {self.model} does not support tools. Retrying without tools.")
                    call_params.pop("tools", None)
                    call_params.pop("tool_choice", None)
                    try:
                        messages = self._fit_provider_messages(messages, ctx, tools=call_params.get("tools", []))
                        call_params["messages"] = messages
                        response = self.openrouter_client.chat.completions.create(**call_params)
                        raw = response.choices[0].message.content or ""
                        return {"ok": True, "content": _strip_internal_tags(raw), "tool_calls": []}
                    except Exception as inner_e:
                        logger.error(f"No-tools fallback also failed: {inner_e}")
                        return self._provider_failure_result(
                            retryable=self._is_retryable_error(inner_e),
                            status_code=503 if self._is_retryable_error(inner_e) else 502,
                        )

                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error calling OpenRouter: {e}")
                    return self._provider_failure_result(retryable=False, status_code=502)

                if attempt < MAX_RETRIES - 1:
                    backoff = INITIAL_BACKOFF_SECONDS * (2 ** attempt)  # 1s, 2s, 4s
                    logger.warning(
                        f"Model {self.model} attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. "
                        f"Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        f"Model {self.model} failed after {MAX_RETRIES} attempts. Last error: {e}"
                    )

        # All retries exhausted
        return self._provider_failure_result(retryable=True, status_code=503)

    async def _call_ai_with_tools_streaming(self, messages: List[Dict], ctx: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Call OpenRouter with tool definitions (async streaming) with retry on transient errors.

        Yields:
        - {"type": "token", "content": str} for prose before the first backslash
        Citation-bearing tails stay buffered for final validation.
        - {"type": "tool_call_detected"} when first tool call is detected
        - {"type": "result", "content": str, "tool_calls": list} at the end
        """
        if not self.async_openrouter_client:
            yield {
                "type": "result",
                **self._provider_failure_result(retryable=False, status_code=502),
            }
            return

        reasoning_info = f" (reasoning: {self._reasoning_mode})" if self._reasoning_mode else ""
        logger.info(f"Async streaming from OpenRouter with model: {self.model}{reasoning_info}")

        tools = self._get_tools_for_user(ctx)

        call_params = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
            # Hard cap so composite tool-chain turns don't get truncated
            # mid-word by provider defaults. 4096 is roomy for chat-style
            # responses; tune per-model in _get_model_output_token_cap.
            "max_tokens": self._get_model_output_token_cap(ctx),
        }

        if not tools:
            call_params.pop("tools")
            call_params.pop("tool_choice")

        reasoning_params = self._get_reasoning_params()
        if reasoning_params.get("extra_body"):
            call_params["extra_body"] = reasoning_params["extra_body"]

        stream = None
        no_tools_fallback = False
        for attempt in range(MAX_RETRIES):
            try:
                messages = self._fit_provider_messages(messages, ctx, tools=call_params.get("tools", []))
                call_params["messages"] = messages
                stream = await self.async_openrouter_client.chat.completions.create(**call_params)
                break
            except Exception as e:
                # Model doesn't support tools → retry without tools
                if self._is_no_tools_error(e):
                    logger.warning(f"Model {self.model} does not support tools. Retrying without tools.")
                    call_params.pop("tools", None)
                    call_params.pop("tool_choice", None)
                    no_tools_fallback = True
                    try:
                        messages = self._fit_provider_messages(messages, ctx, tools=call_params.get("tools", []))
                        call_params["messages"] = messages
                        stream = await self.async_openrouter_client.chat.completions.create(**call_params)
                        break
                    except Exception as inner_e:
                        logger.error(f"No-tools streaming fallback also failed: {inner_e}")
                        yield {
                            "type": "result",
                            **self._provider_failure_result(
                                retryable=self._is_retryable_error(inner_e),
                                status_code=503 if self._is_retryable_error(inner_e) else 502,
                            ),
                        }
                        return

                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error starting async OpenRouter stream: {e}")
                    yield {
                        "type": "result",
                        **self._provider_failure_result(retryable=False, status_code=502),
                    }
                    return
                if attempt < MAX_RETRIES - 1:
                    backoff = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(
                        f"Model {self.model} async stream attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. "
                        f"Retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Model {self.model} async stream failed after {MAX_RETRIES} attempts. Last error: {e}")

        if stream is None:
            yield {
                "type": "result",
                **self._provider_failure_result(retryable=True, status_code=503),
            }
            return

        try:
            content_chunks = []
            prefix = _StreamingCitationPrefix()
            tool_calls_data = {}
            tool_call_signaled = False

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                if delta.content:
                    content_chunks.append(delta.content)
                    safe_text = prefix.feed(delta.content)
                    if safe_text and not tool_call_signaled:
                        yield {"type": "token", "content": safe_text}

                if delta.tool_calls:
                    if not tool_call_signaled:
                        tool_call_signaled = True
                        yield {"type": "tool_call_detected"}

                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_chunk.id:
                            tool_calls_data[idx]["id"] = tc_chunk.id
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                tool_calls_data[idx]["name"] = tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc_chunk.function.arguments

            tool_calls = []
            for idx in sorted(tool_calls_data.keys()):
                tc = tool_calls_data[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({"id": tc["id"], "name": tc["name"], "arguments": args})

            # Strip any think tags from the accumulated content for the result
            full_content = _THINK_TAG_RE.sub("", "".join(content_chunks))
            full_content = _ORPHAN_CLOSE_RE.sub("", full_content).lstrip()
            yield {"type": "result", "ok": True, "content": full_content, "tool_calls": tool_calls}

        except Exception as e:
            logger.exception(f"Error processing async OpenRouter stream with model {self.model}")
            yield {
                "type": "result",
                **self._provider_failure_result(
                    retryable=self._is_retryable_error(e),
                    status_code=503 if self._is_retryable_error(e) else 502,
                ),
            }

    def _execute_lite(self, messages: List[Dict], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Execute lite route: single LLM call, no tools, minimal overhead."""
        t_start = time.monotonic()
        if not self.openrouter_client:
            return self._error_response("OpenRouter API not configured.")

        try:
            messages = self._fit_provider_messages(messages, ctx, tools=[])
            call_kwargs: Dict[str, Any] = dict(
                model=self.model,
                messages=messages,
                max_tokens=4096,
            )
            response = self.openrouter_client.chat.completions.create(**call_kwargs)
            raw = response.choices[0].message.content or ""
            final_message = _strip_internal_tags(raw)
        except Exception as e:
            logger.error(f"Lite execution error: {e}")
            return self._error_response(
                str(e),
                retryable=self._is_retryable_error(e),
                status_code=503 if self._is_retryable_error(e) else 502,
            )

        if not final_message:
            return self._error_response("Provider returned an empty response", status_code=502)
        final_message, invalid_citations = self._apply_citation_filter_for_context(final_message, ctx)

        # Lightweight memory update (regex only, skip LLM fact extraction)
        self._lite_memory_update(ctx)

        prompt_tokens = count_messages_tokens(messages, self.model)
        total_ms = int((time.monotonic() - t_start) * 1000)
        logger.info(
            "[TurnMetrics] route=lite prompt_tokens=%d tools_count=0 ttfb_ms=0 total_ms=%d model=%s reason=%s",
            prompt_tokens, total_ms, self.model, ctx.get("route_reason", ""),
        )

        return {
            "ok": True,
            "message": final_message,
            "actions": [],
            "citations": [],
            "model_used": self.model,
            "reasoning_used": False,
            "tools_called": [],
            "conversation_state": {},
            "invalid_citations": invalid_citations,
            "citation_validation": ctx.get("citation_validation", {}),
        }

    async def _execute_lite_streaming(self, messages: List[Dict], ctx: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute lite route with streaming: single LLM call, no tools."""
        t_start = time.monotonic()
        ttfb_ms: Optional[int] = None
        if not self.async_openrouter_client:
            yield {"type": "result", "data": self._error_response("OpenRouter API not configured.")}
            return

        content_chunks: List[str] = []
        prefix = _StreamingCitationPrefix()
        try:
            messages = self._fit_provider_messages(messages, ctx, tools=[])
            lite_kwargs: Dict[str, Any] = dict(
                model=self.model,
                messages=messages,
                max_tokens=4096,
                stream=True,
            )
            stream = await self.async_openrouter_client.chat.completions.create(**lite_kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    content_chunks.append(delta.content)
                    safe_text = prefix.feed(delta.content)
                    if safe_text:
                        if ttfb_ms is None:
                            ttfb_ms = int((time.monotonic() - t_start) * 1000)
                        yield {"type": "token", "content": safe_text}
        except Exception as e:
            logger.error(f"Lite streaming error: {e}")
            yield {
                "type": "result",
                "data": self._error_response(
                    str(e),
                    retryable=self._is_retryable_error(e),
                    status_code=503 if self._is_retryable_error(e) else 502,
                ),
            }
            return

        content = _THINK_TAG_RE.sub("", "".join(content_chunks))
        content = _ORPHAN_CLOSE_RE.sub("", content).lstrip()
        tail = content[len(prefix.text):] if content.startswith(prefix.text) else content
        final_message = prefix.text + tail
        if not final_message:
            yield {
                "type": "result",
                "data": self._error_response("Provider returned an empty response", status_code=502),
            }
            return
        tail, invalid_citations = self._apply_citation_filter_for_context(tail, ctx)
        for invalid in invalid_citations:
            invalid["span_start"] += len(prefix.text)
            invalid["span_end"] += len(prefix.text)
        final_message = prefix.text + tail

        if tail:
            if ttfb_ms is None:
                ttfb_ms = int((time.monotonic() - t_start) * 1000)
            yield {"type": "token", "content": tail}

        # Yield result IMMEDIATELY so the frontend can unblock the input.
        yield {
            "type": "result",
            "data": {
                "ok": True,
                "message": final_message,
                "actions": [],
                "citations": [],
                "model_used": self.model,
                "reasoning_used": False,
                "tools_called": [],
                "conversation_state": {},
                "invalid_citations": invalid_citations,
                "citation_validation": ctx.get("citation_validation", {}),
            },
        }

        # Post-result work uses the same session isolation as tool turns.
        try:
            await self._run_streaming_db_work(ctx, lite=True)
        except Exception as mem_err:
            logger.error(f"Failed to update lite AI memory: {mem_err}")

        prompt_tokens = count_messages_tokens(messages, self.model)
        total_ms = int((time.monotonic() - t_start) * 1000)
        logger.info(
            "[TurnMetrics] route=lite prompt_tokens=%d tools_count=0 ttfb_ms=%d total_ms=%d model=%s reason=%s",
            prompt_tokens, ttfb_ms or 0, total_ms, self.model, ctx.get("route_reason", ""),
        )

    def _lite_memory_update(self, ctx: Dict[str, Any]) -> None:
        """Lightweight memory update for lite route: regex-only, no LLM fact extraction."""
        try:
            channel = ctx.get("channel")
            if not channel:
                return
            memory = self._get_ai_memory(channel)
            existing_rq = memory.get("facts", {}).get("research_question")
            direct_rq = self._extract_research_question_direct(
                ctx.get("user_message", ""), existing_rq=existing_rq
            )
            if direct_rq:
                memory.setdefault("facts", {})["research_question"] = direct_rq
            memory["_exchanges_since_fact_update"] = memory.get("_exchanges_since_fact_update", 0) + 1
            self._save_ai_memory(channel, memory)
        except Exception as e:
            logger.debug(f"Lite memory update failed: {e}")

    async def _run_streaming_db_work(
        self,
        ctx: Dict[str, Any],
        *,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        final_message: Optional[str] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        policy_decision: Any = None,
        lite: bool = False,
    ) -> Any:
        """Run blocking tools or memory AI with a session owned by the worker."""
        from sqlalchemy import inspect

        from app.database import SessionLocal
        from app.models import Project, ProjectDiscussionChannel, User

        models = {"project": Project, "channel": ProjectDiscussionChannel, "current_user": User}
        entity_ids = {}
        for key in models:
            entity = ctx.get(key)
            state = inspect(entity, raiseerr=False) if entity is not None else None
            # Reading an expired ORM .id can issue a SELECT on the event loop.
            entity_ids[key] = state.identity[0] if state is not None and state.identity else getattr(entity, "id", None)
        worker_ctx = deepcopy({key: value for key, value in ctx.items() if key not in models})
        # Copy before dispatch: neither the request session nor its ORM objects
        # are handed to the worker. Provider clients can be reused across threads.
        worker = copy(self)
        worker.db = None

        def run() -> tuple[Any, Dict[str, Any]]:
            with SessionLocal() as worker_db:
                worker.db = worker_db
                for key, model in models.items():
                    worker_ctx[key] = worker_db.get(model, entity_ids[key]) if entity_ids[key] else None
                if tool_calls is not None:
                    result = worker._execute_tool_calls(tool_calls, worker_ctx)
                elif lite:
                    result = worker._lite_memory_update(worker_ctx)
                elif tool_results is not None:
                    stage_transition_success = worker._enforce_finding_papers_stage_after_search(
                        worker_ctx, tool_results,
                    )
                    worker._record_quality_metrics(
                        worker_ctx, policy_decision, tool_results, False, stage_transition_success,
                    )
                    channel = worker_ctx.get("channel")
                    if channel:
                        memory = worker._get_ai_memory(channel)
                        memory.setdefault("facts", {})["_last_tools_called"] = [item["name"] for item in tool_results]
                        worker._save_ai_memory(channel, memory)
                    result = None
                else:
                    result = worker.update_memory_after_exchange(
                        worker_ctx["channel"],
                        worker_ctx.get("user_message", ""),
                        final_message,
                        worker_ctx.get("conversation_history", []),
                        entity_ids["current_user"],
                    )
                return result, {key: value for key, value in worker_ctx.items() if key not in models}

        result, updates = await asyncio.to_thread(run)
        ctx.update(updates)
        # Tools and memory may have committed changes in their own sessions.
        for key in models:
            if ctx.get(key) is not None:
                self.db.expire(ctx[key])
        return result

    async def _execute_with_tools_streaming(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute with tool calling and async streaming.

        Stream prose prefixes and retain citation-bearing tails for validation.
        Tool execution runs in threads via asyncio.to_thread since tools use sync DB.
        """
        self._reasoning_mode = ctx.get("reasoning_mode", False)
        t_start = time.monotonic()
        ttfb_ms: Optional[int] = None
        conversation_history = ctx.get("conversation_history")
        policy_decision = self._classify_and_build_policy(ctx, conversation_history)

        # Fill the ~6s silence between "Processing your request" and the
        # first tool status with an intent-aware hint, so the user sees
        # progress while the model decides what to do.
        intent = getattr(policy_decision, "intent", "general")
        _intent_filler = {
            "direct_search": "Planning paper search",
            "project_update": "Preparing project updates",
            "analysis": "Preparing analysis",
            "library": "Checking your library",
            "writing": "Planning writing task",
            "clarify": "Reviewing what you said",
        }.get(intent, "Drafting response")
        yield {"type": "status", "tool": "", "message": _intent_filler}

        mutating_calls_seen: set = set()

        max_iterations = 8
        iteration = 0
        all_tool_results = []
        all_content_chunks = []  # Only the final round's text (what the user sees)
        search_tool_executed = False
        recovery_attempted = False
        streamed_text = ""

        recent_results = self._get_recent_papers(ctx)
        logger.info(f"[OpenRouter Async Streaming] Starting with model: {self.model}, recent_search_results: {len(recent_results)} papers")
        streamed_invalid_citations: List[Dict[str, Any]] = []

        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"[OpenRouter Async Streaming] Iteration {iteration}, messages count: {len(messages)}")

            response_content = ""
            tool_calls = []
            iteration_content = []
            provider_error: Optional[Dict[str, Any]] = None
            prefix = _StreamingCitationPrefix()
            stream_prose = True

            async for event in self._call_ai_with_tools_streaming(messages, ctx):
                if event["type"] == "token":
                    iteration_content.append(event["content"])
                    if stream_prose:
                        safe_text = prefix.feed(event["content"])
                        if safe_text:
                            streamed_text += safe_text
                            if ttfb_ms is None:
                                ttfb_ms = int((time.monotonic() - t_start) * 1000)
                            yield {"type": "token", "content": safe_text}
                elif event["type"] == "tool_call_detected":
                    stream_prose = False
                    logger.info("[OpenRouter Async Streaming] Tool call detected")
                elif event["type"] == "result":
                    if event.get("ok") is False:
                        provider_error = event.get("error") or {}
                        continue
                    response_content = event["content"]
                    tool_calls = event.get("tool_calls", [])

            if provider_error is not None:
                yield {
                    "type": "result",
                    "data": self._error_response(
                        provider_error.get("message", "Provider request failed"),
                        retryable=provider_error.get("retryable", True),
                        status_code=provider_error.get("status_code", 503),
                    ),
                }
                return

            logger.debug(f"[OpenRouter Async Streaming] Got {len(tool_calls)} tool calls: {[tc.get('name') for tc in tool_calls]}")

            if not tool_calls:
                # Recovery retry: if no tool calls but user clearly requested action,
                # retry once with a nudge.
                if (
                    not all_tool_results
                    and not recovery_attempted
                    and _ACTION_SIGNAL.search(ctx.get("user_message", ""))
                ):
                    recovery_attempted = True
                    messages.append({
                        "role": "system",
                        "content": "You MUST use a tool to fulfill this request. Do not just describe what you would do — call the appropriate tool now.",
                    })
                    # Emit a status so the user doesn't stare at a frozen UI
                    # during the silent 1.5-4s while we re-prompt the model.
                    yield {"type": "status", "tool": "", "message": "Reconsidering approach"}
                    logger.info("[ToolRecovery] No tool calls, retrying with nudge")
                    continue

                logger.info("[OpenRouter Async Streaming] Final response - no more tool calls")
                all_content_chunks.append(response_content or "".join(iteration_content))
                break

            # Filter out duplicate mutating tool calls.
            tool_calls = filter_duplicate_mutations(tool_calls, mutating_calls_seen, MUTATING_TOOLS)
            tool_calls = self._limit_turn_tool_calls(tool_calls, ctx)
            if not tool_calls:
                all_content_chunks.append(response_content or "".join(iteration_content))
                break

            # Prose buffered after the first backslash in this round must not be
            # dropped: filter it and emit it before the tool calls, so the stream
            # and the persisted message both keep the full sentence. The inner
            # generator only yields the pre-backslash tokens; the whole round,
            # already tag-stripped, arrives in the result event's content.
            round_text = response_content or ""
            round_tail = round_text[len(prefix.text):] if round_text.startswith(prefix.text) else round_text
            if round_tail.strip():
                round_tail, round_invalid = self._apply_citation_filter_for_context(round_tail, ctx)
                for invalid in round_invalid:
                    invalid["span_start"] += len(streamed_text)
                    invalid["span_end"] += len(streamed_text)
                streamed_invalid_citations.extend(round_invalid)
                streamed_text += round_tail
                if ttfb_ms is None:
                    ttfb_ms = int((time.monotonic() - t_start) * 1000)
                yield {"type": "token", "content": round_tail}

            for tc in tool_calls:
                tool_name = tc.get("name", "")
                status_message = self._get_tool_status_message(tool_name)
                yield {"type": "tool_start", "tool": tool_name, "message": status_message, "round": iteration}
                # Keep backward-compatible status event
                yield {"type": "status", "tool": tool_name, "message": status_message}

            # Execute tool calls in thread with progress polling
            progress_queue: stdlib_queue.Queue[str] = stdlib_queue.Queue()
            ctx["_progress_callback"] = lambda msg: progress_queue.put(msg)
            tool_task = asyncio.create_task(
                self._run_streaming_db_work(ctx, tool_calls=tool_calls)
            )
            while not tool_task.done():
                await asyncio.sleep(0.15)
                while not progress_queue.empty():
                    try:
                        msg = progress_queue.get_nowait()
                        yield {"type": "status", "tool": "", "message": msg}
                    except stdlib_queue.Empty:
                        break
            tool_results = await tool_task
            # Drain any remaining progress messages
            while not progress_queue.empty():
                try:
                    msg = progress_queue.get_nowait()
                    yield {"type": "status", "tool": "", "message": msg}
                except stdlib_queue.Empty:
                    break
            ctx.pop("_progress_callback", None)
            all_tool_results.extend(tool_results)

            # Emit tool_end for each tool that was called
            for tc in tool_calls:
                yield {"type": "tool_end", "tool": tc.get("name", ""), "round": iteration}

            # Only mark "search executed" when a search actually produced results.
            # Blocked/errored searches must loop back to the model so it can
            # explain the situation instead of silently emitting "Results will
            # appear shortly" when nothing ran.
            if any(
                tr.get("name") in ("search_papers", "batch_search_papers")
                and (tr.get("result") or {}).get("status") not in ("error", "blocked")
                for tr in tool_results
            ):
                search_tool_executed = True

            # Skip re-querying only when every tool was a successful search.
            # Any blocked/error result requires another round so the model
            # can produce an honest correction for the user.
            search_only = all(
                tr.get("name") in ("search_papers", "batch_search_papers")
                for tr in tool_results
            )
            search_has_problem = any(
                (tr.get("result") or {}).get("status") in ("error", "blocked", "partial")
                for tr in tool_results
            )
            if search_only and search_tool_executed and not search_has_problem:
                break

            formatted_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    }
                }
                for tc in tool_calls
            ]

            messages.append({
                "role": "assistant",
                "content": response_content or "",
                "tool_calls": formatted_tool_calls,
            })

            for tool_call, result in zip(tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": self._serialize_tool_result(result, ctx),
                })

            messages.append({
                "role": "system",
                "content": "Continue your response naturally from where you left off. Do not repeat or rephrase what you already said before the tool call.",
            })

        final_message = _THINK_TAG_RE.sub("", "".join(all_content_chunks))
        final_message = _ORPHAN_CLOSE_RE.sub("", final_message).lstrip()
        if not streamed_text:
            final_message = self._apply_response_budget(final_message, ctx, all_tool_results)
        logger.debug(f"[OpenRouter Async] Complete. Tools called: {[t['name'] for t in all_tool_results]}")

        if not final_message.strip() and all_tool_results:
            provider_worker = copy(self)
            provider_worker.db = None
            final_message = await asyncio.to_thread(provider_worker._generate_tool_summary_message, all_tool_results)
            logger.info(f"[OpenRouter Async] Generated summary for empty response: {final_message[:100]}...")
        if not final_message.strip():
            provider_worker = copy(self)
            provider_worker.db = None
            generated_fallback = await asyncio.to_thread(
                provider_worker._generate_content_fallback,
                {"user_message": ctx.get("user_message", "")},
                all_tool_results,
            )
            if generated_fallback and generated_fallback.strip():
                final_message = generated_fallback.strip()
        if not final_message.strip():
            final_message = self._build_empty_response_fallback(ctx)
        tail = final_message[len(prefix.text):] if final_message.startswith(prefix.text) else final_message
        tail, invalid_citations = self._apply_citation_filter_for_context(tail, ctx)
        for invalid in invalid_citations:
            invalid["span_start"] += len(streamed_text)
            invalid["span_end"] += len(streamed_text)
        invalid_citations = streamed_invalid_citations + invalid_citations
        final_message = streamed_text + tail

        actions = self._extract_actions(final_message, all_tool_results)
        tools_called_this_turn = [t["name"] for t in all_tool_results] if all_tool_results else []

        if tail:
            if ttfb_ms is None:
                ttfb_ms = int((time.monotonic() - t_start) * 1000)
            yield {"type": "token", "content": tail}

        # Yield result IMMEDIATELY so the frontend can unblock the input.
        # Memory updates, metrics, and stage transitions happen AFTER.
        yield {
            "type": "result",
            "data": {
                "ok": True,
                "message": final_message,
                "actions": actions,
                "citations": [],
                "model_used": self.model,
                "reasoning_used": ctx.get("reasoning_mode", False),
                "tools_called": tools_called_this_turn,
                "conversation_state": {},
                "invalid_citations": invalid_citations,
                "citation_validation": ctx.get("citation_validation", {}),
            }
        }

        # --- Post-result work (user already has the response) ---

        try:
            contradiction_warning = await self._run_streaming_db_work(
                ctx, final_message=final_message,
            )
            if contradiction_warning:
                logger.info(f"Contradiction detected: {contradiction_warning}")
        except Exception as mem_err:
            logger.error(f"Failed to update AI memory: {mem_err}")

        try:
            await self._run_streaming_db_work(
                ctx, tool_results=all_tool_results, policy_decision=policy_decision,
            )
        except Exception as metrics_err:
            logger.error(f"Failed to record metrics: {metrics_err}")

        prompt_tokens = count_messages_tokens(messages[:1], self.model)
        total_ms = int((time.monotonic() - t_start) * 1000)
        logger.info(
            "[TurnMetrics] route=full prompt_tokens=%d tools_count=%d ttfb_ms=%d total_ms=%d model=%s",
            prompt_tokens, len(all_tool_results), ttfb_ms or 0, total_ms, self.model,
        )

    def _generate_tool_summary_message(self, tool_results: List[Dict]) -> str:
        """Generate a summary message when model returns empty content after tool execution."""
        messages = []

        for tr in tool_results:
            tool_name = tr.get("name", "")
            result = tr.get("result", {})

            if tool_name == "add_to_library":
                added = result.get("added_count", 0)
                if added > 0:
                    messages.append(f"Added {added} paper{'s' if added != 1 else ''} to your library.")

            elif tool_name == "search_papers":
                action = result.get("action", {})
                payload = action.get("payload", {})
                papers_found = len(payload.get("papers", []))
                query = payload.get("query", "")
                if result.get("status") == "error":
                    messages.append("Search failed because academic sources were unavailable. Please retry.")
                elif result.get("status") == "empty":
                    messages.append(f"No papers matched '{query}'.")
                elif result.get("status") == "partial":
                    messages.append(
                        f"Found {papers_found} papers for '{query}', but some academic sources were unavailable."
                    )
                elif papers_found > 0:
                    messages.append(f"Found {papers_found} papers for '{query}'.")

            elif tool_name == "get_project_references":
                total = result.get("total_count", 0)
                messages.append(f"Retrieved your library ({total} reference{'s' if total != 1 else ''}).")

            elif tool_name == "create_paper":
                action = result.get("action", {})
                payload = action.get("payload", {})
                title = payload.get("title", "paper")
                messages.append(f"Created paper: **{title}**")

            elif tool_name == "get_recent_search_results":
                count = result.get("count", 0)
                if count > 0:
                    messages.append(f"Retrieved {count} recent search result{'s' if count != 1 else ''}.")

        if messages:
            return " ".join(messages)
        else:
            # Fallback - list what tools were called
            tools_called = [tr.get("name", "unknown") for tr in tool_results]
            return f"Completed: {', '.join(tools_called)}."

    def _generate_content_fallback(
        self,
        ctx: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Generate concise non-empty fallback content when primary response is blank."""
        if not self.openrouter_client:
            return None

        user_message = (ctx.get("user_message") or "").strip()
        if not user_message:
            return None

        try:
            response = self.openrouter_client.chat.completions.create(
                model=self.model,
                messages=self._fit_provider_messages([
                    {
                        "role": "system",
                        "content": (
                            "You are a concise research assistant. "
                            "Answer directly in 2-4 sentences with one concrete next step."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ], ctx, tools=[]),
                max_tokens=min(self._get_model_output_token_cap(ctx), 280),
            )
            text = _strip_internal_tags(response.choices[0].message.content or "")
            return text or None
        except Exception as exc:
            logger.debug("Content fallback generation skipped due to model error: %s", exc)
            return None


def get_available_models_with_meta(
    *,
    include_reasoning: bool = False,
    require_tools: bool = False,
    api_key: Optional[str] = None,
    use_env_key: bool = True,
) -> Dict[str, Any]:
    """Return available models with metadata about the source and warnings."""
    resolved_key = api_key or (settings.OPENROUTER_API_KEY if use_env_key else None)
    use_cache = api_key is None and use_env_key
    source = None
    warning = None

    models: Optional[List[Dict[str, Any]]] = None
    if use_cache:
        cached = _get_cached_models()
        if cached:
            models = cached
            source = "cache"

    if models is None:
        fetched = _fetch_openrouter_models(resolved_key)
        if fetched:
            merged = {model["id"]: model for model in fetched}
            for fallback in _fallback_models(include_reasoning=False):
                if fallback["id"] not in merged:
                    merged[fallback["id"]] = fallback
                elif include_reasoning and merged[fallback["id"]].get("supports_reasoning") is None:
                    merged[fallback["id"]]["supports_reasoning"] = fallback["id"] in REASONING_SUPPORTED_MODELS
            models = list(merged.values())
            source = "remote"
            if use_cache:
                _cache_models(models)
        else:
            models, source = _fallback_models_with_source(include_reasoning=False)
            if resolved_key:
                warning = "OpenRouter models API unavailable; using fallback list."
            else:
                warning = "OpenRouter API key not configured; using fallback list."

    if include_reasoning:
        for model in models:
            if model.get("supports_reasoning") is not True:
                model["supports_reasoning"] = model["id"] in REASONING_SUPPORTED_MODELS

    if require_tools:
        models = [model for model in models if model.get("supports_tools") is True]

    return {"models": models, "source": source, "warning": warning}


def get_available_models(include_reasoning: bool = False, require_tools: bool = False) -> List[Dict[str, Any]]:
    """Return list of available models for the frontend."""
    meta = get_available_models_with_meta(
        include_reasoning=include_reasoning,
        require_tools=require_tools,
        api_key=None,
        use_env_key=True,
    )
    return meta["models"]
