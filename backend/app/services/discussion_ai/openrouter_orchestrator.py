"""
OpenRouter-Based Discussion AI Orchestrator

Uses OpenRouter API to support multiple AI models (GPT, Claude, Gemini, etc.)
Inherits from ToolOrchestrator and only overrides the AI calling methods.

Key difference from base ToolOrchestrator:
- Streams ONLY the final response (hides intermediate "thinking" during tool calls)
- Shows status messages during tool execution
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

import openai
from openai import APIStatusError, RateLimitError, APIConnectionError, APITimeoutError
import httpx

from app.core.config import settings
from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator, DISCUSSION_TOOLS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# =============================================================================
# REASONING CONTENT FILTERING (two layers)
# =============================================================================
# Layer 1 (primary): All API calls include `reasoning: {exclude: true}` so
#   OpenRouter strips reasoning tokens server-side for any model.
#
# Layer 2 (safety net): ThinkTagFilter + _THINK_TAG_RE catch any tags that
#   leak through despite the API flag (e.g. new/unsupported models).
# =============================================================================
_REASONING_TAGS = ("think", "thought", "reasoning", "reflection")

_THINK_TAG_RE = re.compile(
    r"<(?:" + "|".join(_REASONING_TAGS) + r")>.*?</(?:" + "|".join(_REASONING_TAGS) + r")>",
    re.DOTALL,
)


class ThinkTagFilter:
    """Streaming safety-net filter that strips reasoning tag blocks.

    Primary defence is the API-level ``reasoning.exclude`` flag.  This filter
    catches anything that still leaks through (new models, API bugs, etc.).
    Handles: <think>, <thought>, <reasoning>, <reflection>.
    """

    _OPEN_TAGS = tuple(f"<{t}>" for t in _REASONING_TAGS)
    _CLOSE_TAGS = tuple(f"</{t}>" for t in _REASONING_TAGS)
    _MAX_OPEN_LEN = max(len(t) for t in _OPEN_TAGS)
    _MAX_CLOSE_LEN = max(len(t) for t in _CLOSE_TAGS)

    def __init__(self) -> None:
        self._inside_block = False
        self._buffer = ""

    def _find_open_tag(self, text: str) -> tuple[int, int]:
        best_pos, best_len = -1, 0
        for tag in self._OPEN_TAGS:
            idx = text.find(tag)
            if idx != -1 and (best_pos == -1 or idx < best_pos):
                best_pos, best_len = idx, len(tag)
        return best_pos, best_len

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
                if start_idx == -1:
                    safe_end = len(self._buffer) - self._MAX_OPEN_LEN
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
        with httpx.Client(timeout=3.0) as client:
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

        self.openrouter_client = openai.OpenAI(
            api_key=api_key or "missing-key",
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            }
        ) if api_key else None

        self.async_openrouter_client = openai.AsyncOpenAI(
            api_key=api_key or "missing-key",
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            }
        ) if api_key else None

        if user_api_key:
            logger.info("Using user-provided OpenRouter API key")

    def _model_supports_reasoning(self) -> bool:
        """Check if the current model supports OpenRouter reasoning parameter."""
        return model_supports_reasoning(self._model)

    def _get_reasoning_params(self) -> dict:
        """Get reasoning parameters for the API call.

        When reasoning is enabled and the model supports it, returns
        effort: "high". Otherwise, explicitly excludes reasoning tokens
        so models like DeepSeek don't leak <think> tags into content.
        """
        if self._reasoning_mode and self._model_supports_reasoning():
            return {
                "extra_body": {
                    "reasoning": {
                        "effort": "high"
                    }
                }
            }

        # Explicitly disable reasoning for models that think by default
        # (e.g. DeepSeek V3.2). This prevents chain-of-thought from
        # appearing in the content stream. ThinkTagFilter remains as safety net.
        return {
            "extra_body": {
                "reasoning": {
                    "enabled": False
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

    def _call_ai_with_tools(self, messages: List[Dict], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Call OpenRouter with tool definitions (non-streaming) with retry on transient errors."""
        if not self.openrouter_client:
            return {
                "content": "OpenRouter API not configured. Please check your OPENROUTER_API_KEY.",
                "tool_calls": []
            }

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
        }

        # Add reasoning params (always includes exclude or effort)
        reasoning_params = self._get_reasoning_params()
        if reasoning_params.get("extra_body"):
            call_params["extra_body"] = reasoning_params["extra_body"]

        # Retry loop for transient errors
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.openrouter_client.chat.completions.create(**call_params)

                choice = response.choices[0]
                message = choice.message

                result = {
                    "content": _THINK_TAG_RE.sub("", message.content or "").strip(),
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
                last_error = e
                if not self._is_retryable_error(e):
                    # Non-retryable error (auth, invalid request, etc.) - fail immediately
                    logger.error(f"Non-retryable error calling OpenRouter: {e}")
                    return {"content": f"Error: {str(e)}", "tool_calls": []}

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
        error_msg = f"{self.model} is temporarily unavailable. Please try again or switch models."
        return {"content": error_msg, "tool_calls": []}

    async def _call_ai_with_tools_streaming(self, messages: List[Dict], ctx: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Call OpenRouter with tool definitions (async streaming) with retry on transient errors.

        Yields:
        - {"type": "token", "content": str} for content tokens
        - {"type": "tool_call_detected"} when first tool call is detected (stop streaming tokens)
        - {"type": "result", "content": str, "tool_calls": list} at the end
        """
        if not self.async_openrouter_client:
            yield {"type": "result", "content": "OpenRouter API not configured.", "tool_calls": []}
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
        }

        reasoning_params = self._get_reasoning_params()
        if reasoning_params.get("extra_body"):
            call_params["extra_body"] = reasoning_params["extra_body"]

        stream = None
        for attempt in range(MAX_RETRIES):
            try:
                stream = await self.async_openrouter_client.chat.completions.create(**call_params)
                break
            except Exception as e:
                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error starting async OpenRouter stream: {e}")
                    yield {"type": "result", "content": f"Error: {str(e)}", "tool_calls": []}
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
            error_msg = f"{self.model} is temporarily unavailable. Please try again or switch models."
            yield {"type": "result", "content": error_msg, "tool_calls": []}
            return

        try:
            content_chunks = []
            tool_calls_data = {}
            tool_call_signaled = False
            think_filter = ThinkTagFilter()

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                if delta.content:
                    content_chunks.append(delta.content)
                    if not tool_call_signaled:
                        visible = think_filter.feed(delta.content)
                        if visible:
                            yield {"type": "token", "content": visible}

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

            # Flush any remaining buffered content from the think filter
            if not tool_call_signaled:
                remaining = think_filter.flush()
                if remaining:
                    yield {"type": "token", "content": remaining}

            tool_calls = []
            for idx in sorted(tool_calls_data.keys()):
                tc = tool_calls_data[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({"id": tc["id"], "name": tc["name"], "arguments": args})

            # Strip any think tags from the accumulated content for the result
            full_content = _THINK_TAG_RE.sub("", "".join(content_chunks)).strip()
            yield {"type": "result", "content": full_content, "tool_calls": tool_calls}

        except Exception as e:
            logger.exception(f"Error processing async OpenRouter stream with model {self.model}")
            yield {"type": "result", "content": f"Error: {str(e)}", "tool_calls": []}

    def _execute_lite(self, messages: List[Dict], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Execute lite route: single LLM call, no tools, minimal overhead."""
        if not self.openrouter_client:
            return self._error_response("OpenRouter API not configured.")

        try:
            response = self.openrouter_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=256,
                extra_body={"reasoning": {"enabled": False}},
            )
            raw = response.choices[0].message.content or ""
            final_message = _THINK_TAG_RE.sub("", raw).strip()
        except Exception as e:
            logger.error(f"Lite execution error: {e}")
            final_message = ""

        if not final_message:
            final_message = self._build_lite_fallback(ctx)

        # Lightweight memory update (regex only, skip LLM fact extraction)
        self._lite_memory_update(ctx)

        return {
            "message": final_message,
            "actions": [],
            "citations": [],
            "model_used": self.model,
            "reasoning_used": False,
            "tools_called": [],
            "conversation_state": {},
        }

    async def _execute_lite_streaming(self, messages: List[Dict], ctx: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute lite route with streaming: single LLM call, no tools."""
        if not self.async_openrouter_client:
            yield {"type": "result", "data": self._error_response("OpenRouter API not configured.")}
            return

        content_chunks: List[str] = []
        think_filter = ThinkTagFilter()
        try:
            stream = await self.async_openrouter_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=256,
                stream=True,
                extra_body={"reasoning": {"enabled": False}},
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    content_chunks.append(delta.content)
                    visible = think_filter.feed(delta.content)
                    if visible:
                        yield {"type": "token", "content": visible}
            remaining = think_filter.flush()
            if remaining:
                yield {"type": "token", "content": remaining}
        except Exception as e:
            logger.error(f"Lite streaming error: {e}")

        final_message = _THINK_TAG_RE.sub("", "".join(content_chunks)).strip()
        if not final_message:
            final_message = self._build_lite_fallback(ctx)
            yield {"type": "token", "content": final_message}

        # Lightweight memory update (regex only, skip LLM fact extraction)
        self._lite_memory_update(ctx)

        yield {
            "type": "result",
            "data": {
                "message": final_message,
                "actions": [],
                "citations": [],
                "model_used": self.model,
                "reasoning_used": False,
                "tools_called": [],
                "conversation_state": {},
            },
        }

    @staticmethod
    def _build_lite_fallback(ctx: Dict[str, Any]) -> str:
        """Friendly fallback for lite route when the LLM call fails (e.g. rate limit)."""
        reason = ctx.get("route_reason", "")
        project_title = getattr(ctx.get("project"), "title", "your project")
        if reason in ("greeting_or_acknowledgment", "standalone_confirmation", "empty_message"):
            return f"Hello! I'm here to help with {project_title}. What would you like to work on?"
        return f"Got it! Let me know how I can help with {project_title}."

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

    async def _execute_with_tools_streaming(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute with tool calling and async streaming.

        OVERRIDE: Only streams the FINAL response, not intermediate thinking.
        Tool execution runs in threads via asyncio.to_thread since tools use sync DB.
        """
        self._reasoning_mode = ctx.get("reasoning_mode", False)
        policy_decision = self._build_policy_decision(ctx)
        ctx["policy_decision"] = policy_decision

        max_iterations = 8
        iteration = 0
        all_tool_results = []
        final_content_chunks = []
        clarification_first_detected = False
        direct_search_intent = (
            policy_decision.should_force_tool("search_papers")
            and policy_decision.search is not None
        )
        search_tool_executed = False

        recent_results = ctx.get("recent_search_results", [])
        logger.info(f"[OpenRouter Async Streaming] Starting with model: {self.model}, recent_search_results: {len(recent_results)} papers")

        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"[OpenRouter Async Streaming] Iteration {iteration}, messages count: {len(messages)}")

            response_content = ""
            tool_calls = []
            iteration_content = []
            has_tool_call = False
            hold_direct_search_tokens = direct_search_intent and not search_tool_executed

            async for event in self._call_ai_with_tools_streaming(messages, ctx):
                if event["type"] == "token":
                    iteration_content.append(event["content"])
                    # For direct-search intent, hold tokens until a search action has executed.
                    if not has_tool_call and not hold_direct_search_tokens:
                        yield {"type": "token", "content": event["content"]}
                elif event["type"] == "tool_call_detected":
                    has_tool_call = True
                    logger.info("[OpenRouter Async Streaming] Tool call detected, stopping token stream")
                elif event["type"] == "result":
                    response_content = event["content"]
                    tool_calls = event.get("tool_calls", [])

            logger.debug(f"[OpenRouter Async Streaming] Got {len(tool_calls)} tool calls: {[tc.get('name') for tc in tool_calls]}")

            if not tool_calls:
                if direct_search_intent and not search_tool_executed and policy_decision.search is not None:
                    clarification_first_detected = clarification_first_detected or bool((response_content or "").strip() or iteration_content)
                    forced_query = policy_decision.search.query or self._build_fallback_search_query(ctx)
                    forced_tool_call = {
                        "id": "forced-search-1",
                        "name": "search_papers",
                        "arguments": {
                            "query": forced_query,
                            "count": policy_decision.search.count,
                            "limit": policy_decision.search.count,
                            "open_access_only": policy_decision.search.open_access_only,
                            "year_from": policy_decision.search.year_from,
                            "year_to": policy_decision.search.year_to,
                        },
                    }
                    logger.info(f"[OpenRouter Async] Applying direct-search fallback with query: {forced_query[:120]}")
                    yield {
                        "type": "status",
                        "tool": "search_papers",
                        "message": self._get_tool_status_message("search_papers"),
                    }
                    tool_results = await asyncio.to_thread(self._execute_tool_calls, [forced_tool_call], ctx)
                    all_tool_results.extend(tool_results)
                    search_tool_executed = True
                    final_content_chunks.append("Searching for papers now. Results will appear in the UI shortly.")
                    break

                logger.info("[OpenRouter Async Streaming] Final response - no more tool calls")
                if iteration_content:
                    final_content_chunks.extend(iteration_content)
                elif response_content:
                    final_content_chunks.append(response_content)
                    yield {"type": "token", "content": response_content}
                break

            for tc in tool_calls:
                tool_name = tc.get("name", "")
                status_message = self._get_tool_status_message(tool_name)
                yield {"type": "status", "tool": tool_name, "message": status_message}

            # Execute tool calls in thread (tools use sync DB)
            tool_results = await asyncio.to_thread(self._execute_tool_calls, tool_calls, ctx)
            all_tool_results.extend(tool_results)
            if any(tr.get("name") in ("search_papers", "batch_search_papers") for tr in tool_results):
                search_tool_executed = True

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
                    "content": json.dumps(result, default=str),
                })

        final_message = _THINK_TAG_RE.sub("", "".join(final_content_chunks)).strip()
        final_message = self._apply_response_budget(final_message, ctx, all_tool_results)
        logger.debug(f"[OpenRouter Async] Complete. Tools called: {[t['name'] for t in all_tool_results]}")

        if not final_message.strip() and all_tool_results:
            final_message = await asyncio.to_thread(self._generate_tool_summary_message, all_tool_results)
            logger.info(f"[OpenRouter Async] Generated summary for empty response: {final_message[:100]}...")
        if not final_message.strip():
            generated_fallback = await asyncio.to_thread(
                self._generate_content_fallback,
                ctx,
                all_tool_results,
            )
            if generated_fallback and generated_fallback.strip():
                final_message = generated_fallback.strip()
        if not final_message.strip():
            final_message = self._build_empty_response_fallback(ctx)

        actions = self._extract_actions(final_message, all_tool_results)

        contradiction_warning = None
        try:
            contradiction_warning = await asyncio.to_thread(
                self.update_memory_after_exchange,
                ctx["channel"],
                ctx["user_message"],
                final_message,
                ctx.get("conversation_history", []),
                getattr(ctx.get("current_user"), "id", None),
            )
            if contradiction_warning:
                logger.info(f"Contradiction detected: {contradiction_warning}")
        except Exception as mem_err:
            logger.error(f"Failed to update AI memory: {mem_err}")

        # Deterministic stage transition after successful search tools.
        stage_transition_success = await asyncio.to_thread(
            self._enforce_finding_papers_stage_after_search,
            ctx,
            all_tool_results,
        )
        await asyncio.to_thread(
            self._record_quality_metrics,
            ctx,
            policy_decision,
            all_tool_results,
            clarification_first_detected,
            stage_transition_success,
        )

        yield {
            "type": "result",
            "data": {
                "message": final_message,
                "actions": actions,
                "citations": [],
                "model_used": self.model,
                "reasoning_used": ctx.get("reasoning_mode", False),
                "tools_called": [t["name"] for t in all_tool_results] if all_tool_results else [],
                "conversation_state": {},
                "memory_warning": contradiction_warning,
            }
        }

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
                if papers_found > 0:
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
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise research assistant. "
                            "Answer directly in 2-4 sentences with one concrete next step."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ],
                max_tokens=min(self._get_model_output_token_cap(ctx), 280),
            )
            text = _THINK_TAG_RE.sub("", response.choices[0].message.content or "").strip()
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
