"""
OpenRouter-Based Discussion AI Orchestrator

Uses OpenRouter API to support multiple AI models (GPT, Claude, Gemini, etc.)
Inherits from ToolOrchestrator and only overrides the AI calling methods.

Key difference from base ToolOrchestrator:
- Streams ONLY the final response (hides intermediate "thinking" during tool calls)
- Shows status messages during tool execution
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Generator, List, Optional, TYPE_CHECKING

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

        if user_api_key:
            logger.info("Using user-provided OpenRouter API key")

    def _model_supports_reasoning(self) -> bool:
        """Check if the current model supports OpenRouter reasoning parameter."""
        return model_supports_reasoning(self._model)

    def _get_reasoning_params(self) -> dict:
        """Get reasoning parameters for the API call if enabled and supported."""
        if not self._reasoning_mode or not self._model_supports_reasoning():
            return {}

        # OpenRouter unified reasoning parameter
        # effort: "high" provides good balance of reasoning depth vs cost
        return {
            "extra_body": {
                "reasoning": {
                    "effort": "high"
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

        # Add reasoning params if enabled
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
                    "content": message.content or "",
                    "tool_calls": [],
                }

                if message.tool_calls:
                    for tc in message.tool_calls:
                        result["tool_calls"].append({
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments),
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

    def _call_ai_with_tools_streaming(self, messages: List[Dict], ctx: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """Call OpenRouter with tool definitions (streaming) with retry on transient errors.

        Yields:
        - {"type": "token", "content": str} for content tokens
        - {"type": "tool_call_detected"} when first tool call is detected (stop streaming tokens)
        - {"type": "result", "content": str, "tool_calls": list} at the end
        """
        if not self.openrouter_client:
            yield {"type": "result", "content": "OpenRouter API not configured.", "tool_calls": []}
            return

        reasoning_info = f" (reasoning: {self._reasoning_mode})" if self._reasoning_mode else ""
        logger.info(f"Streaming from OpenRouter with model: {self.model}{reasoning_info}")

        # Filter tools based on user's role
        tools = self._get_tools_for_user(ctx)

        # Build API call params
        call_params = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
        }

        # Add reasoning params if enabled
        reasoning_params = self._get_reasoning_params()
        if reasoning_params.get("extra_body"):
            call_params["extra_body"] = reasoning_params["extra_body"]

        # Retry loop for transient errors (only retries stream initialization, not mid-stream)
        last_error: Optional[Exception] = None
        stream = None

        for attempt in range(MAX_RETRIES):
            try:
                stream = self.openrouter_client.chat.completions.create(**call_params)
                break  # Successfully got stream
            except Exception as e:
                last_error = e
                if not self._is_retryable_error(e):
                    # Non-retryable error - fail immediately
                    logger.error(f"Non-retryable error starting OpenRouter stream: {e}")
                    yield {"type": "result", "content": f"Error: {str(e)}", "tool_calls": []}
                    return

                if attempt < MAX_RETRIES - 1:
                    backoff = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(
                        f"Model {self.model} stream attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. "
                        f"Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        f"Model {self.model} stream failed after {MAX_RETRIES} attempts. Last error: {e}"
                    )

        if stream is None:
            error_msg = f"{self.model} is temporarily unavailable. Please try again or switch models."
            yield {"type": "result", "content": error_msg, "tool_calls": []}
            return

        # Process the stream
        try:
            content_chunks = []
            tool_calls_data = {}  # {index: {"id": ..., "name": ..., "arguments": ...}}
            tool_call_signaled = False

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Handle content tokens
                if delta.content:
                    content_chunks.append(delta.content)
                    # Only yield tokens if we haven't detected a tool call yet
                    if not tool_call_signaled:
                        yield {"type": "token", "content": delta.content}

                # Handle tool calls (accumulated across chunks)
                if delta.tool_calls:
                    # Signal tool call detection ONCE so caller knows to stop streaming
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

            # Parse accumulated tool calls
            tool_calls = []
            for idx in sorted(tool_calls_data.keys()):
                tc = tool_calls_data[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": args,
                })

            yield {
                "type": "result",
                "content": "".join(content_chunks),
                "tool_calls": tool_calls,
            }

        except Exception as e:
            logger.exception(f"Error processing OpenRouter stream with model {self.model}")
            yield {"type": "result", "content": f"Error: {str(e)}", "tool_calls": []}

    def _execute_with_tools_streaming(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Execute with tool calling and streaming.

        OVERRIDE: Only streams the FINAL response, not intermediate thinking.
        - Tokens are streamed immediately until a tool call is detected
        - When tool call is detected mid-stream, remaining content is hidden
        - Status messages are shown during tool execution
        - Final response (no tool calls) is fully streamed
        """
        # Set reasoning mode from context for use in API calls
        self._reasoning_mode = ctx.get("reasoning_mode", False)

        max_iterations = 8
        iteration = 0
        all_tool_results = []
        final_content_chunks = []

        recent_results = ctx.get("recent_search_results", [])
        logger.info(f"[OpenRouter Streaming] Starting with model: {self.model}, recent_search_results: {len(recent_results)} papers")

        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"[OpenRouter Streaming] Iteration {iteration}, messages count: {len(messages)}")

            response_content = ""
            tool_calls = []
            iteration_content = []
            has_tool_call = False

            for event in self._call_ai_with_tools_streaming(messages, ctx):
                if event["type"] == "token":
                    iteration_content.append(event["content"])
                    # Stream tokens to client unless tool call detected
                    if not has_tool_call:
                        yield {"type": "token", "content": event["content"]}
                elif event["type"] == "tool_call_detected":
                    # Tool call detected mid-stream - stop streaming, buffer the rest
                    has_tool_call = True
                    logger.info("[OpenRouter Streaming] Tool call detected, stopping token stream")
                elif event["type"] == "result":
                    response_content = event["content"]
                    tool_calls = event.get("tool_calls", [])

            logger.debug(f"[OpenRouter Streaming] Got {len(tool_calls)} tool calls: {[tc.get('name') for tc in tool_calls]}")
            logger.debug(f"[OpenRouter Streaming] Content length: {len(response_content)} chars")

            if not tool_calls:
                # No tool calls - this was the final response
                logger.info("[OpenRouter Streaming] Final response - no more tool calls")
                # Use streamed tokens if available, otherwise fall back to response_content
                # (some models don't stream tokens, they return content only in the final result)
                if iteration_content:
                    final_content_chunks.extend(iteration_content)
                elif response_content:
                    final_content_chunks.append(response_content)
                    # Stream the content now since it wasn't streamed earlier
                    yield {"type": "token", "content": response_content}
                break

            # Tool calls present - send status messages
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                status_message = self._get_tool_status_message(tool_name)
                yield {"type": "status", "tool": tool_name, "message": status_message}

            # Execute tool calls
            tool_results = self._execute_tool_calls(tool_calls, ctx)
            all_tool_results.extend(tool_results)

            # Add assistant message with tool calls to conversation
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

            # Add tool results to conversation
            for tool_call, result in zip(tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, default=str),
                })

        # Build final result
        final_message = "".join(final_content_chunks)
        logger.debug(f"[OpenRouter] Complete. Tools called: {[t['name'] for t in all_tool_results]}")

        # Generate message when model returns empty content after tool execution
        # Some models (e.g., DeepSeek) don't provide a summary message after executing tools
        if not final_message.strip() and all_tool_results:
            final_message = self._generate_tool_summary_message(all_tool_results)
            logger.info(f"[OpenRouter] Generated summary for empty response: {final_message[:100]}...")

        actions = self._extract_actions(final_message, all_tool_results)
        logger.debug(f"[OpenRouter] Extracted {len(actions)} actions: {[a.get('type') for a in actions]}")

        # Update AI memory after successful response
        contradiction_warning = None
        try:
            contradiction_warning = self.update_memory_after_exchange(
                ctx["channel"],
                ctx["user_message"],
                final_message,
                ctx.get("conversation_history", []),
            )
            if contradiction_warning:
                logger.info(f"Contradiction detected: {contradiction_warning}")
        except Exception as mem_err:
            logger.error(f"Failed to update AI memory: {mem_err}")

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
