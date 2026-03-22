"""Deep research endpoint and supporting helpers."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import httpx
import openai
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_verified_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.api.utils.openrouter_access import resolve_openrouter_key_for_project
from app.core.config import settings
from app.database import get_db
from app.models import (
    ProjectReference,
    Reference,
    User,
)
from app.services.subscription_service import SubscriptionService
from app.api.v1.discussion_helpers import (
    get_channel_or_404 as _get_channel_or_404,
    display_name_for_user as _display_name_for_user,
    broadcast_discussion_event as _broadcast_discussion_event,
    persist_assistant_exchange as _persist_assistant_exchange,
)

router = APIRouter()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deep Research
# ---------------------------------------------------------------------------

_ALLOWED_DEEP_RESEARCH_MODELS = {
    "openai/o4-mini-deep-research",
    "openai/o3-deep-research",
    "perplexity/sonar-deep-research",
    "alibaba/tongyi-deepresearch-30b-a3b",
}

# Models that need external tool execution (agentic models)
_AGENTIC_DEEP_RESEARCH_MODELS = {
    "alibaba/tongyi-deepresearch-30b-a3b",
}

_DEEP_RESEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search academic papers and web sources",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": "Search query or list of queries",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse",
            "description": "Read content from a URL or list of URLs (academic papers, web pages)",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": "URL or list of URLs to read",
                    },
                    "goal": {
                        "type": "string",
                        "description": "What information to extract",
                    },
                },
                "required": ["url"],
            },
        },
    },
]

_MAX_TOOL_ROUNDS = 8
_SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_SS_FIELDS = "title,authors,year,abstract,url,externalIds"


async def _execute_search_tool(queries: list[str]) -> str:
    """Execute academic paper search via Semantic Scholar API."""
    all_results: list[str] = []
    headers: dict[str, str] = {}
    if settings.SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY

    async with httpx.AsyncClient(timeout=15) as client:
        for q in queries[:5]:  # Max 5 queries per tool call
            try:
                resp = await client.get(
                    _SEMANTIC_SCHOLAR_SEARCH_URL,
                    params={"query": q, "limit": "5", "fields": _SS_FIELDS},
                    headers=headers,
                )
                if resp.status_code != 200:
                    all_results.append(f"Search '{q}': no results (status {resp.status_code})")
                    continue
                data = resp.json()
                papers = data.get("data", [])
                if not papers:
                    all_results.append(f"Search '{q}': no results")
                    continue
                for p in papers:
                    title = p.get("title", "Unknown")
                    authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])
                    year = p.get("year", "")
                    abstract = (p.get("abstract") or "")[:300]
                    doi = (p.get("externalIds") or {}).get("DOI", "")
                    all_results.append(
                        f"- {title} ({authors}, {year})"
                        + (f" DOI:{doi}" if doi else "")
                        + (f"\n  {abstract}" if abstract else "")
                    )
                await asyncio.sleep(1)  # Rate limit: 1 req/sec
            except Exception as e:
                all_results.append(f"Search '{q}': error ({e})")
                logger.warning("Deep research search tool error for query '%s': %s", q, e)

    return "\n".join(all_results) if all_results else "No results found."


async def _execute_browse_tool(urls: list[str], goal: str = "") -> str:
    """Fetch content from URLs for the agentic model. Uses Semantic Scholar paper API for DOIs."""
    results: list[str] = []
    headers: dict[str, str] = {}
    if settings.SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for url in urls[:5]:  # Max 5 URLs per tool call
            try:
                # If it's a DOI URL, fetch from Semantic Scholar instead
                doi = None
                if "doi.org/" in url:
                    doi = url.split("doi.org/", 1)[-1].strip()
                if doi:
                    resp = await client.get(
                        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
                        params={"fields": "title,authors,year,abstract,tldr"},
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        p = resp.json()
                        title = p.get("title", "Unknown")
                        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:5])
                        year = p.get("year", "")
                        abstract = p.get("abstract") or ""
                        tldr = (p.get("tldr") or {}).get("text", "")
                        results.append(
                            f"## {title} ({authors}, {year})\n"
                            + (f"Abstract: {abstract}\n" if abstract else "")
                            + (f"TLDR: {tldr}\n" if tldr else "")
                        )
                    else:
                        results.append(f"Could not fetch DOI {doi} (status {resp.status_code})")
                else:
                    # Non-DOI URL — skip (SSRF risk, not worth fetching arbitrary URLs)
                    results.append(f"URL {url}: skipped (only DOI URLs are fetched for safety)")
                await asyncio.sleep(1)  # Rate limit
            except Exception as e:
                results.append(f"Error fetching {url}: {e}")
                logger.warning("Deep research browse tool error for '%s': %s", url, e)

    return "\n\n".join(results) if results else "No content could be fetched."


def _parse_text_tool_calls(text: str) -> list[dict]:
    """Parse tool calls from text — handles both <tool_call> XML and raw JSON."""
    import re as _re
    calls = []
    # Try <tool_call> XML format first
    for match in _re.finditer(r'<tool_call>\s*(.*?)\s*</tool_call>', text, _re.DOTALL):
        try:
            parsed = json.loads(match.group(1))
            if "name" in parsed:
                calls.append(parsed)
        except json.JSONDecodeError:
            pass
    if calls:
        return calls
    # Try to find any JSON with "name" or "arguments" containing tool-like data
    stripped = text.strip()
    # Try the whole text as JSON
    for candidate_text in [stripped, '{' + stripped if stripped.startswith('"') else stripped]:
        try:
            parsed = json.loads(candidate_text)
            if isinstance(parsed, dict):
                if "name" in parsed:
                    calls.append(parsed)
                    return calls
                # No "name" but has "arguments" with "url" or "query" — infer tool name
                args = parsed.get("arguments", {})
                if isinstance(args, dict):
                    if "query" in args:
                        calls.append({"name": "search", "arguments": args})
                        return calls
                    if "url" in args or "urls" in args:
                        calls.append({"name": "browse", "arguments": args})
                        return calls
        except (json.JSONDecodeError, TypeError):
            pass
    # Try to find JSON objects with "name" key anywhere in text
    for match in _re.finditer(r'\{["\']name["\']\s*:', text):
        try:
            start = match.start()
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{': depth += 1
                elif text[i] == '}': depth -= 1
                if depth == 0:
                    parsed = json.loads(text[start:i+1])
                    if "name" in parsed:
                        calls.append(parsed)
                    break
        except (json.JSONDecodeError, IndexError):
            pass
    # Last resort: find "arguments" with url/query patterns
    if not calls:
        for match in _re.finditer(r'"arguments"\s*:\s*\{', text):
            try:
                start = match.start() - 1
                if text[start] != '{':
                    start = text.rfind('{', 0, match.start())
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == '{': depth += 1
                    elif text[i] == '}': depth -= 1
                    if depth == 0:
                        parsed = json.loads(text[start:i+1])
                        args = parsed.get("arguments", {})
                        if "query" in args:
                            calls.append({"name": "search", "arguments": args})
                        elif "url" in args:
                            calls.append({"name": "browse", "arguments": args})
                        break
            except (json.JSONDecodeError, IndexError):
                pass
    return calls


def _strip_tool_call_text(text: str) -> str:
    """Remove tool call artifacts from text."""
    import re as _re
    # Remove <tool_call>...</tool_call>
    cleaned = _re.sub(r'<tool_call>\s*.*?\s*</tool_call>', '', text, flags=_re.DOTALL)
    # Remove raw JSON tool calls with "name"
    cleaned = _re.sub(r'\{"name"\s*:\s*"(?:search|browse|read|fetch|visit)".*?\}\s*\}', '', cleaned, flags=_re.DOTALL)
    # Remove "arguments": {...} patterns (tool calls without "name" wrapper)
    cleaned = _re.sub(r'"arguments"\s*:\s*\{.*?\}\s*\}', '', cleaned, flags=_re.DOTALL)
    # Remove standalone JSON objects with "url" arrays and "goal" strings
    cleaned = _re.sub(r'\{?\s*"url"\s*:\s*\[.*?\]\s*,\s*"goal"\s*:\s*".*?"\s*\}?\s*\}?', '', cleaned, flags=_re.DOTALL)
    return cleaned.strip()


def _is_tool_call_text(text: str) -> bool:
    """Check if text is primarily a tool call (not a real report)."""
    stripped = text.strip()
    if not stripped:
        return False
    # If it starts with "arguments" or {"name" or <tool_call>, it's a tool call
    if stripped.startswith('"arguments"') or stripped.startswith('{"name"') or stripped.startswith('<tool_call>'):
        return True
    # If most of the text is JSON-like with urls/queries, it's a tool call
    clean = _strip_tool_call_text(stripped)
    return len(clean) < len(stripped) * 0.3  # More than 70% was tool call content


async def _run_agentic_deep_research(
    client: "openai.AsyncOpenAI",
    model: str,
    messages: list[dict],
) -> str:
    """Run multi-turn tool execution loop for agentic models. Returns final text."""
    for round_num in range(1, _MAX_TOOL_ROUNDS + 1):
        logger.info("[deep-research] Agentic round %d/%d, model=%s", round_num, _MAX_TOOL_ROUNDS, model)

        # After round 6, nudge the model to stop searching and write the report
        if round_num >= 6:
            messages.append({
                "role": "user",
                "content": "You have gathered enough information. Please stop searching and write your final comprehensive report now. Synthesize all findings into a structured academic report.",
            })

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=_DEEP_RESEARCH_TOOLS if round_num < 7 else [],
        )
        choice = response.choices[0]

        # Check for text-based tool calls (Tongyi outputs these as XML or raw JSON)
        text_content = choice.message.content or ""
        text_tool_calls = _parse_text_tool_calls(text_content) if (
            "<tool_call>" in text_content or
            '"name"' in text_content and '"arguments"' in text_content
        ) else []

        if text_tool_calls:
            # Handle XML-format tool calls
            messages.append({"role": "assistant", "content": text_content})
            for tc_data in text_tool_calls:
                fn_name = tc_data.get("name", "")
                args = tc_data.get("arguments", {})
                logger.info("[deep-research] XML tool call: %s(%s)", fn_name, str(args)[:100])

                if fn_name == "search":
                    raw_query = args.get("query", [])
                    queries = raw_query if isinstance(raw_query, list) else [raw_query]
                    result = await _execute_search_tool(queries)
                elif fn_name in ("browse", "read", "fetch", "visit"):
                    raw_urls = args.get("url", args.get("urls", []))
                    urls = raw_urls if isinstance(raw_urls, list) else [raw_urls]
                    goal = args.get("goal", "")
                    result = await _execute_browse_tool(urls, goal)
                else:
                    result = f"Tool result for {fn_name}: not supported"

                messages.append({"role": "user", "content": f"Tool result:\n{result}"})
            continue

        # Check for structured tool calls (OpenAI format)
        if choice.message.tool_calls:
            # Add assistant message with tool calls
            messages.append(choice.message.model_dump())

            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                logger.info("[deep-research] Tool call: %s(%s)", fn_name, str(args)[:100])

                if fn_name == "search":
                    raw_query = args.get("query", [])
                    queries = raw_query if isinstance(raw_query, list) else [raw_query]
                    result = await _execute_search_tool(queries)
                elif fn_name in ("browse", "read", "fetch", "visit"):
                    raw_urls = args.get("url", args.get("urls", []))
                    urls = raw_urls if isinstance(raw_urls, list) else [raw_urls]
                    goal = args.get("goal", "")
                    result = await _execute_browse_tool(urls, goal)
                else:
                    result = f"Unknown tool: {fn_name}. Available tools: search, browse."

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            continue

        # No structured or text tool calls — check if final text is a real report or leaked tool call
        if _is_tool_call_text(text_content):
            # Model is still trying to call tools via text — redirect to synthesis
            logger.info("[deep-research] Round %d: text is tool call, redirecting to synthesis", round_num)
            messages.append({"role": "assistant", "content": text_content})
            messages.append({"role": "user", "content": "I cannot execute that tool call. Please write your final comprehensive report NOW based on all the papers and information you have gathered so far. Write it as a structured academic report with sections, findings, and comparisons."})
            continue

        # Clean text output — return it
        final = _strip_tool_call_text(text_content)
        if final and len(final) > 50:
            return final
        return text_content or ""

    # Exhausted rounds — force a final synthesis call without tools
    logger.warning("[deep-research] Exhausted %d tool rounds, forcing final synthesis", _MAX_TOOL_ROUNDS)
    messages.append({
        "role": "user",
        "content": "Write your final report now based on all the information you have gathered. Do not make any more tool calls.",
    })
    try:
        final_resp = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
        return final_resp.choices[0].message.content or "Research could not be completed."
    except Exception as e:
        logger.error("[deep-research] Final synthesis failed: %s", e)
        return "Research could not be completed after exhausting search rounds."

class DeepResearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    context_summary: str = Field("", max_length=2000)
    reference_ids: list[str] = Field(default_factory=list)
    model: str = Field("openai/o4-mini-deep-research", description="Deep research model to use")


@router.post("/projects/{project_id}/discussion-or/channels/{channel_id}/deep-research")
async def run_deep_research(
    project_id: str,
    channel_id: UUID,
    payload: DeepResearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
):
    """Launch a deep research job that streams SSE progress and a final report."""

    # --- Validate project / channel / permissions ---
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    discussion_settings = project.discussion_settings or {"enabled": True}
    if not discussion_settings.get("enabled", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Discussion AI is disabled for this project",
        )

    # --- Resolve OpenRouter API key ---
    use_owner_key_for_team = bool(discussion_settings.get("use_owner_key_for_team", False))
    resolution = resolve_openrouter_key_for_project(
        db, current_user, project, use_owner_key_for_team=use_owner_key_for_team,
    )
    api_key_to_use = resolution.get("api_key")

    if resolution.get("error_status"):
        raise HTTPException(
            status_code=int(resolution["error_status"]),
            detail={
                "error": "no_api_key" if resolution["error_status"] == 402 else "invalid_api_key",
                "message": resolution.get("error_detail") or "OpenRouter API key issue.",
            },
        )
    if not api_key_to_use:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "no_api_key",
                "message": "No API key available. Add your OpenRouter key or ask the project owner to enable key sharing.",
            },
        )

    # --- Credit limit check ---
    from app.services.subscription_service import get_model_credit_cost
    # Validate model
    if payload.model not in _ALLOWED_DEEP_RESEARCH_MODELS:
        raise HTTPException(status_code=400, detail=f"Model {payload.model} is not supported for deep research")
    deep_research_model = payload.model
    credit_cost = get_model_credit_cost(deep_research_model)
    allowed, current_usage, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "discussion_ai_calls"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "discussion_ai_calls",
                "current": current_usage,
                "limit": limit,
                "message": f"You have reached your discussion AI credit limit ({current_usage}/{limit} credits this month). Upgrade to Pro for more credits.",
            },
        )

    # --- Create exchange with status="processing" ---
    exchange_id = str(uuid4())
    exchange_created_at = datetime.utcnow().isoformat() + "Z"
    display_name = _display_name_for_user(current_user)
    author_info = {
        "id": str(current_user.id),
        "name": {
            "first": current_user.first_name or "",
            "last": current_user.last_name or "",
            "display": display_name,
        },
    }
    initial_response = {
        "message": "",
        "citations": [],
        "reasoning_used": False,
        "model": deep_research_model,
        "usage": None,
        "suggested_actions": [],
    }
    await asyncio.to_thread(
        _persist_assistant_exchange,
        project.id, channel.id, current_user.id, exchange_id,
        f"[Deep Research] {payload.question}",
        initial_response, exchange_created_at, {}, "processing",
        "Starting deep research...",
    )
    await _broadcast_discussion_event(
        project.id, channel.id, "assistant_processing",
        {"exchange": {
            "id": exchange_id,
            "question": f"[Deep Research] {payload.question}",
            "status": "processing",
            "status_message": "Starting deep research...",
            "created_at": exchange_created_at,
            "author": author_info,
        }},
    )

    # --- Load library context (only user-selected references, not the whole library) ---
    def _load_library_context():
        if not payload.reference_ids:
            return ""  # No context selected — let the model search freely
        q = (
            db.query(Reference)
            .join(ProjectReference, ProjectReference.reference_id == Reference.id)
            .filter(ProjectReference.project_id == project.id)
            .filter(ProjectReference.reference_id.in_(payload.reference_ids))
        )
        refs = q.all()
        parts: list[str] = []
        for ref in refs:
            lines = [f"- {ref.title}"]
            if ref.authors:
                lines.append(f"  Authors: {', '.join(ref.authors[:5])}")
            if ref.year:
                lines.append(f"  Year: {ref.year}")
            if ref.abstract:
                lines.append(f"  Abstract: {ref.abstract[:300]}")
            if ref.key_findings:
                lines.append(f"  Key findings: {'; '.join(ref.key_findings[:3])}")
            parts.append("\n".join(lines))
        return "\n".join(parts)

    library_context = await asyncio.to_thread(_load_library_context)

    # --- Build prompt ---
    system_content = (
        "You are a deep research assistant for an academic project. "
        "The researcher has these papers in their library:\n"
        f"{library_context}\n\n"
        "Use this to understand what they already know. Search the web for additional sources. "
        "Provide a comprehensive report with: "
        "1) Key findings by theme "
        "2) Inline citations with URLs "
        "3) Areas of consensus and debate "
        "4) Gaps and future directions "
        "5) Relevance to existing library"
    )
    user_content = payload.question
    if payload.context_summary:
        user_content += f"\n\nAdditional context: {payload.context_summary}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    # --- Capture closure values ---
    proj_id = project.id
    chan_id = channel.id
    user_id = current_user.id
    question_text = f"[Deep Research] {payload.question}"

    async def stream_sse():
        accumulated = ""
        first_token = True
        last_keepalive = time.monotonic()

        try:
            client = openai.AsyncOpenAI(
                api_key=api_key_to_use,
                base_url="https://openrouter.ai/api/v1",
                timeout=httpx.Timeout(1800.0, connect=30.0),
                default_headers={
                    "HTTP-Referer": "https://scholarhub.space",
                    "X-Title": "ScholarHub",
                },
            )

            use_agentic = deep_research_model in _AGENTIC_DEEP_RESEARCH_MODELS

            if use_agentic:
                # Agentic model: multi-turn tool execution loop
                yield "data: " + json.dumps({"type": "status", "message": "Searching academic sources..."}) + "\n\n"
                final_text = await _run_agentic_deep_research(client, deep_research_model, messages)
                # Stream the final text word-by-word for smooth display
                for word in final_text.split(" "):
                    token = word + " "
                    accumulated += token
                    yield "data: " + json.dumps({"type": "token", "content": token}) + "\n\n"
            else:
                # Standard model: direct streaming (OpenAI/Perplexity handle search internally)
                stream = await client.chat.completions.create(
                    model=deep_research_model,
                    messages=messages,
                    stream=True,
                )

                async for chunk in stream:
                    # Keepalive every 15s
                    now = time.monotonic()
                    if now - last_keepalive >= 15:
                        yield "data: " + json.dumps({"type": "keepalive"}) + "\n\n"
                        last_keepalive = now

                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta or not delta.content:
                        continue

                    token = delta.content
                    if first_token:
                        yield "data: " + json.dumps({"type": "status", "message": "Generating report..."}) + "\n\n"
                        first_token = False

                    accumulated += token
                    yield "data: " + json.dumps({"type": "token", "content": token}) + "\n\n"

            # --- Stream finished: build result ---
            response_dict = {
                "message": accumulated,
                "citations": [],
                "reasoning_used": False,
                "model": deep_research_model,
                "usage": None,
                "suggested_actions": [],
            }
            yield "data: " + json.dumps({"type": "result", "payload": response_dict}) + "\n\n"

            # Fire-and-forget persist + broadcast
            async def _post_stream_work():
                try:
                    await asyncio.to_thread(
                        _persist_assistant_exchange,
                        proj_id, chan_id, user_id, exchange_id,
                        question_text, response_dict, exchange_created_at,
                        {}, "completed",
                    )
                    await _broadcast_discussion_event(
                        proj_id, chan_id, "assistant_reply",
                        {"exchange": {
                            "id": exchange_id,
                            "question": question_text,
                            "response": response_dict,
                            "created_at": exchange_created_at,
                            "author": author_info,
                            "status": "completed",
                        }},
                    )
                    await asyncio.to_thread(
                        SubscriptionService.increment_usage,
                        db, user_id, "discussion_ai_calls", credit_cost,
                    )
                except Exception as e:
                    logger.error(f"Deep research post-stream work failed for exchange {exchange_id}: {e}")

            asyncio.create_task(_post_stream_work())

        except GeneratorExit:
            logger.info(f"Client disconnected during deep research for exchange {exchange_id}")
            try:
                if accumulated:
                    # Partial results are still valuable
                    partial_response = {
                        "message": accumulated,
                        "citations": [],
                        "reasoning_used": False,
                        "model": deep_research_model,
                        "usage": None,
                        "suggested_actions": [],
                    }
                    _persist_assistant_exchange(
                        proj_id, chan_id, user_id, exchange_id,
                        question_text, partial_response, exchange_created_at,
                        {}, "completed", "Partial results (client disconnected)",
                    )
                else:
                    _persist_assistant_exchange(
                        proj_id, chan_id, user_id, exchange_id,
                        question_text,
                        {"message": "Deep research interrupted before results were available. Please try again.",
                         "citations": [], "suggested_actions": []},
                        exchange_created_at, {}, "failed",
                        "Client disconnected",
                    )
            except Exception:
                logger.warning(f"Failed to persist exchange {exchange_id} after client disconnect")

        except Exception as exc:
            logger.exception("Deep research streaming error", exc_info=exc)
            error_response = {
                "message": "An error occurred during deep research.",
                "citations": [],
                "suggested_actions": [],
            }
            await asyncio.to_thread(
                _persist_assistant_exchange,
                proj_id, chan_id, user_id, exchange_id,
                question_text, error_response, exchange_created_at,
                {}, "failed", "Deep research failed. Please try again.",
            )
            await _broadcast_discussion_event(
                proj_id, chan_id, "assistant_failed",
                {"exchange_id": exchange_id, "error": "Deep research failed"},
            )
            yield "data: " + json.dumps({"type": "error", "message": "Deep research failed"}) + "\n\n"

    return StreamingResponse(
        stream_sse(),
        media_type="text/event-stream",
        headers={"X-Exchange-Id": exchange_id},
    )
