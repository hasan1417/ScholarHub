"""Prose streams promptly while citation-bearing tails remain private."""

from typing import Any, AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator


@pytest.fixture
def orchestrator() -> OpenRouterOrchestrator:
    instance = object.__new__(OpenRouterOrchestrator)
    instance.model = "openai/gpt-4o"
    instance._reasoning_mode = False
    instance.db = MagicMock()
    instance.async_openrouter_client = MagicMock()
    instance._fit_provider_messages = MagicMock(side_effect=lambda messages, ctx, tools: messages)
    instance._get_tools_for_user = MagicMock(return_value=[])
    instance._get_reasoning_params = MagicMock(return_value={})
    instance._lite_memory_update = MagicMock()
    instance._run_streaming_db_work = AsyncMock()
    instance._classify_and_build_policy = MagicMock(return_value=SimpleNamespace(intent="general"))
    instance._apply_response_budget = MagicMock(side_effect=lambda text, ctx, results: text)
    instance._extract_actions = MagicMock(return_value=[])
    instance.update_memory_after_exchange = MagicMock()
    instance._enforce_finding_papers_stage_after_search = MagicMock()
    instance._record_quality_metrics = MagicMock()
    return instance


async def provider_stream(fail: bool = False) -> AsyncGenerator[Any, None]:
    for text in ["Supported ", r"\ci", "te{fabricated}", " conclusion."]:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])
    if fail:
        raise RuntimeError("stream interrupted")


@pytest.mark.asyncio
async def test_provider_stream_keeps_split_citations_internal(orchestrator: OpenRouterOrchestrator) -> None:
    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=provider_stream())
    events = [event async for event in orchestrator._call_ai_with_tools_streaming([], {})]
    assert [event["type"] for event in events] == ["token", "result"]
    assert events[0]["content"] == "Supported "
    assert r"\cite{fabricated}" in events[-1]["content"]
    kwargs = orchestrator.async_openrouter_client.chat.completions.create.call_args.kwargs
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs
    orchestrator._fit_provider_messages.assert_called_once()


@pytest.mark.asyncio
async def test_lite_stream_emits_only_filtered_final_text(orchestrator: OpenRouterOrchestrator) -> None:
    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=provider_stream())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()), patch(
        "app.services.discussion_ai.tool_orchestrator.settings.CITATION_FILTER_MODE", "strict"
    ):
        events = [event async for event in orchestrator._execute_lite_streaming([], {})]
    result = events[-1]["data"]
    tokens = "".join(event["content"] for event in events if event["type"] == "token")
    assert tokens == result["message"]
    assert r"\cite{fabricated}" not in tokens
    assert "?MISSING:fabricated?" in tokens
    assert result["invalid_citations"]
    orchestrator._fit_provider_messages.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
async def test_interrupted_stream_does_not_leak_partial_citations(
    orchestrator: OpenRouterOrchestrator, lite: bool,
) -> None:
    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=provider_stream(fail=True))
    stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
    events = [event async for event in stream]
    assert [event["content"] for event in events if event["type"] == "token"] == ["Supported "]
    assert events[-1]["data"]["ok"] is False


@pytest.mark.asyncio
async def test_tool_stream_buffers_recovery_and_intermediate_rounds(orchestrator: OpenRouterOrchestrator) -> None:
    responses = [
        {"content": r"Retry draft \cite{retry_fake}", "tool_calls": []},
        {"content": r"Tool draft \cite{tool_fake}", "tool_calls": [{"id": "call-1", "name": "get_project_references", "arguments": {}}]},
        {"content": r"Final answer \cite{final_fake}", "tool_calls": []},
    ]

    async def call_stream(messages: list[dict], ctx: dict) -> AsyncGenerator[dict, None]:
        response = responses.pop(0)
        # Mirror the real generator: only the text before the first backslash
        # streams as tokens; the whole round arrives in the result event.
        yield {"type": "token", "content": response["content"].split("\\", 1)[0]}
        if response["tool_calls"]:
            yield {"type": "tool_call_detected"}
        yield {"type": "result", "ok": True, **response}

    orchestrator._call_ai_with_tools_streaming = call_stream
    orchestrator._run_streaming_db_work = AsyncMock(side_effect=[[{"name": "get_project_references", "result": {"references": []}}], None, None])
    orchestrator._serialize_tool_result = MagicMock(return_value='{"truncated": true}')
    ctx = {"user_message": "find papers", "channel": None}
    messages = [{"role": "user", "content": "find papers"}]
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()), patch(
        "app.services.discussion_ai.tool_orchestrator.settings.CITATION_FILTER_MODE", "strict"
    ):
        events = [event async for event in orchestrator._execute_with_tools_streaming(messages, ctx)]
    result = events[-1]["data"]
    tokens = "".join(event["content"] for event in events if event["type"] == "token")
    assert tokens == result["message"]
    assert "Final answer" in tokens
    assert r"\cite{final_fake}" not in tokens
    assert "?MISSING:final_fake?" in tokens
    # The recovery draft's tail is superseded by the retry; an intermediate tool
    # round's prose after the first backslash is filtered and emitted, not dropped.
    assert tokens.startswith("Retry draft Tool draft ")
    assert "retry_fake" not in tokens
    assert r"\cite{tool_fake}" not in tokens
    assert "Tool draft \\cite{?MISSING:tool_fake?}Final answer " in tokens
    assert [item["original_key"] for item in result["invalid_citations"]] == ["tool_fake", "final_fake"]
    assert any(event["type"] == "tool_start" for event in events)
    assert any(event.get("message") == "Reconsidering approach" for event in events)
    assert next(message["content"] for message in messages if message["role"] == "tool") == '{"truncated": true}'
    orchestrator._serialize_tool_result.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
async def test_strict_validation_error_does_not_stream_unvalidated_citations(
    orchestrator: OpenRouterOrchestrator, lite: bool,
) -> None:
    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=provider_stream())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", side_effect=RuntimeError("database unavailable")), patch(
        "app.services.discussion_ai.tool_orchestrator.settings.CITATION_FILTER_MODE", "strict"
    ):
        stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
        events = [event async for event in stream]
    result = events[-1]["data"]
    tokens = "".join(event["content"] for event in events if event["type"] == "token")
    assert tokens == result["message"]
    assert r"\cite{fabricated}" not in tokens
    assert result["citation_validation"]["error"] == "citation_validation_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
@pytest.mark.parametrize("citation", [True, False])
async def test_safe_prose_streams_before_provider_finishes(
    orchestrator: OpenRouterOrchestrator, lite: bool, citation: bool,
) -> None:
    finished = False

    async def chunks() -> AsyncGenerator[Any, None]:
        nonlocal finished
        for text in ["Supported ", "prose ", r"\cite{fake}" if citation else "continues."]:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])
        finished = True

    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=chunks())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()), patch(
        "app.services.discussion_ai.tool_orchestrator.settings.CITATION_FILTER_MODE", "strict"
    ):
        stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
        tokens = []
        async for event in stream:
            if event["type"] == "token":
                if not tokens:
                    assert not finished, "First token was delayed until provider completion"
                tokens.append(event["content"])
    assert tokens[:2] == ["Supported ", "prose "]
    assert tokens[2:] == ([r"\cite{?MISSING:fake?}"] if citation else ["continues."])


@pytest.mark.asyncio
async def test_post_stream_metrics_are_dispatched_to_worker(orchestrator: OpenRouterOrchestrator) -> None:
    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=provider_stream())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()):
        _ = [event async for event in orchestrator._execute_with_tools_streaming([], {})]
    orchestrator._enforce_finding_papers_stage_after_search.assert_not_called()
    orchestrator._record_quality_metrics.assert_not_called()
    assert any("tool_results" in call.kwargs for call in orchestrator._run_streaming_db_work.call_args_list)


@pytest.mark.asyncio
async def test_multiple_tool_rounds_do_not_repeat_streamed_prose(orchestrator: OpenRouterOrchestrator) -> None:
    responses = [
        {"content": "I will inspect it. ", "tool_calls": [{"id": "call-1", "name": "get_project_references", "arguments": {}}]},
        {"content": "It has five references.", "tool_calls": []},
    ]

    async def call_stream(messages: list[dict], ctx: dict) -> AsyncGenerator[dict, None]:
        response = responses.pop(0)
        # Mirror the real generator: only the text before the first backslash
        # streams as tokens; the whole round arrives in the result event.
        yield {"type": "token", "content": response["content"].split("\\", 1)[0]}
        if response["tool_calls"]:
            yield {"type": "tool_call_detected"}
        yield {"type": "result", "ok": True, **response}

    orchestrator._call_ai_with_tools_streaming = call_stream
    orchestrator._run_streaming_db_work = AsyncMock(side_effect=[[{"name": "get_project_references", "result": {"references": []}}], None, None])
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()):
        events = [event async for event in orchestrator._execute_with_tools_streaming([], {"user_message": "Explain the library"})]
    text = "".join(event["content"] for event in events if event["type"] == "token")
    assert text.count("It has five references.") == 1
    assert text == events[-1]["data"]["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
async def test_ttfb_records_first_emission_not_completion(
    orchestrator: OpenRouterOrchestrator, lite: bool, caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    clock = [0.0]

    async def chunks() -> AsyncGenerator[Any, None]:
        for seconds, text in [(1.0, "First "), (40.0, "last.")]:
            clock[0] = seconds
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])

    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=chunks())
    with patch("app.services.discussion_ai.openrouter_orchestrator.time.monotonic", side_effect=lambda: clock[0]), patch(
        "app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()
    ), caplog.at_level(logging.INFO, logger="app.services.discussion_ai.openrouter_orchestrator"):
        stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
        _ = [event async for event in stream]
    assert "ttfb_ms=1000 total_ms=40000" in caplog.text


@pytest.mark.asyncio
async def test_stage_and_metrics_use_worker_session_with_expired_request_entities(
    orchestrator: OpenRouterOrchestrator,
) -> None:
    import threading
    from uuid import uuid4

    from sqlalchemy.orm import Session, make_transient_to_detached
    from app.models import ProjectDiscussionChannel

    channel = ProjectDiscussionChannel(id=uuid4())
    channel_id = channel.id
    make_transient_to_detached(channel)
    request_db = Session()
    request_db.add(channel)
    request_db.expire(channel)
    orchestrator.db = request_db
    worker_db = MagicMock()
    worker_channel = SimpleNamespace(id=channel_id)
    worker_db.get.return_value = worker_channel
    loop_thread = threading.get_ident()
    calls = []

    def stage(self: OpenRouterOrchestrator, ctx: dict, results: list[dict]) -> bool:
        assert threading.get_ident() != loop_thread
        assert self.db is worker_db
        assert ctx["channel"] is worker_channel
        calls.append("stage")
        return True

    def metrics(self: OpenRouterOrchestrator, ctx: dict, policy: Any, results: list[dict], applied: bool, success: bool) -> None:
        assert threading.get_ident() != loop_thread
        assert self.db is worker_db
        assert ctx["channel"] is worker_channel
        assert success
        calls.append("metrics")

    del orchestrator._enforce_finding_papers_stage_after_search
    del orchestrator._record_quality_metrics
    orchestrator._get_ai_memory = MagicMock(return_value={})
    orchestrator._save_ai_memory = MagicMock()
    try:
        with patch("app.database.SessionLocal") as session_factory, patch.object(
            OpenRouterOrchestrator, "_enforce_finding_papers_stage_after_search", stage
        ), patch.object(OpenRouterOrchestrator, "_record_quality_metrics", metrics):
            session_factory.return_value.__enter__.return_value = worker_db
            await OpenRouterOrchestrator._run_streaming_db_work(
                orchestrator, {"channel": channel}, tool_results=[], policy_decision=None,
            )
        assert calls == ["stage", "metrics"]
        worker_db.get.assert_called_once_with(ProjectDiscussionChannel, channel_id)
        orchestrator._save_ai_memory.assert_called_once_with(worker_channel, {"facts": {"_last_tools_called": []}})
    finally:
        request_db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
async def test_internal_reasoning_does_not_delay_later_prose(
    orchestrator: OpenRouterOrchestrator, lite: bool,
) -> None:
    async def chunks() -> AsyncGenerator[Any, None]:
        for text in ["<thi", "nk>private</think>Visible ", "prose."]:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])

    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=chunks())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()):
        stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
        events = [event async for event in stream]
    assert [event["content"] for event in events if event["type"] == "token"] == ["Visible ", "prose."]
    assert events[-1]["data"]["message"] == "Visible prose."


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
async def test_citation_diagnostic_spans_include_streamed_prefix(
    orchestrator: OpenRouterOrchestrator, lite: bool,
) -> None:
    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=provider_stream())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()), patch(
        "app.services.discussion_ai.tool_orchestrator.settings.CITATION_FILTER_MODE", "strict"
    ):
        stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
        events = [event async for event in stream]
    invalid = events[-1]["data"]["invalid_citations"][0]
    original = r"Supported \cite{fabricated} conclusion."
    assert original[invalid["span_start"]:invalid["span_end"]] == "fabricated"


@pytest.mark.asyncio
async def test_partial_batch_returns_skipped_topics_to_model(orchestrator: OpenRouterOrchestrator) -> None:
    responses = [
        {"content": "", "tool_calls": [{"id": "call-1", "name": "batch_search_papers", "arguments": {}}]},
        {"content": "Topic C was skipped because the budget had only two credits.", "tool_calls": []},
    ]

    async def call_stream(messages: list[dict], ctx: dict) -> AsyncGenerator[dict, None]:
        response = responses.pop(0)
        yield {"type": "result", "ok": True, **response}

    orchestrator._call_ai_with_tools_streaming = call_stream
    partial_result = {"name": "batch_search_papers", "result": {
        "status": "partial", "message": "Topic C skipped: budget has two credits.",
        "topic_results": [{"topic": "C", "status": "skipped", "count": 0}],
    }}
    orchestrator._run_streaming_db_work = AsyncMock(side_effect=[[partial_result], None, None])
    messages = []
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()):
        events = [event async for event in orchestrator._execute_with_tools_streaming(messages, {})]
    assert not responses
    assert "Topic C was skipped" in events[-1]["data"]["message"]
    assert "skipped" in next(message["content"] for message in messages if message["role"] == "tool")


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
@pytest.mark.parametrize("whitespace", ["\n", "\t"])
async def test_internal_tag_whitespace_never_streams_reasoning(
    orchestrator: OpenRouterOrchestrator, lite: bool, whitespace: str,
) -> None:
    async def chunks() -> AsyncGenerator[Any, None]:
        for text in [f"<think{whitespace}>internal draft</think>", "Final prose."]:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])

    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=chunks())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()):
        stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
        events = [event async for event in stream]
    assert [event["content"] for event in events if event["type"] == "token"] == ["Final prose."]
    assert events[-1]["data"]["message"] == "Final prose."


@pytest.mark.asyncio
@pytest.mark.parametrize("lite", [True, False])
async def test_split_orphan_internal_closer_is_removed_without_repetition(
    orchestrator: OpenRouterOrchestrator, lite: bool,
) -> None:
    async def chunks() -> AsyncGenerator[Any, None]:
        for text in ["</thi", "nk>", "Final prose."]:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])

    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(return_value=chunks())
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value=set()):
        stream = orchestrator._execute_lite_streaming([], {}) if lite else orchestrator._execute_with_tools_streaming([], {})
        events = [event async for event in stream]
    assert [event["content"] for event in events if event["type"] == "token"] == ["Final prose."]
    assert events[-1]["data"]["message"] == "Final prose."


@pytest.mark.asyncio
async def test_real_generator_flushes_buffered_prose_before_tool_calls(orchestrator: OpenRouterOrchestrator) -> None:
    def chunk(text: str | None = None, tool_call: Any = None) -> Any:
        delta = SimpleNamespace(content=text, tool_calls=[tool_call] if tool_call else None)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    async def first_round() -> AsyncGenerator[Any, None]:
        for text in ["I will look at ", r"\cite{fake2021}", " and check the library."]:
            yield chunk(text)
        yield chunk(tool_call=SimpleNamespace(index=0, id="call-1", function=SimpleNamespace(name="get_project_references", arguments="{}")))

    async def second_round() -> AsyncGenerator[Any, None]:
        for text in ["Here are the results ", r"\cite{real2020}."]:
            yield chunk(text)

    orchestrator.async_openrouter_client.chat.completions.create = AsyncMock(side_effect=[first_round(), second_round()])
    orchestrator._run_streaming_db_work = AsyncMock(side_effect=[[{"name": "get_project_references", "result": {"references": []}}], None, None])
    orchestrator._serialize_tool_result = MagicMock(return_value='{"references": []}')
    with patch("app.services.discussion_ai.tool_orchestrator.build_allowed_citation_keys", return_value={"real2020"}), patch(
        "app.services.discussion_ai.tool_orchestrator.settings.CITATION_FILTER_MODE", "strict"
    ):
        events = [event async for event in orchestrator._execute_with_tools_streaming([], {"user_message": "find papers", "channel": None})]
    result = events[-1]["data"]
    tokens = "".join(event["content"] for event in events if event["type"] == "token")
    assert tokens == result["message"]
    assert tokens == "I will look at \\cite{?MISSING:fake2021?} and check the library.Here are the results \\cite{real2020}."
    assert [item["original_key"] for item in result["invalid_citations"]] == ["fake2021"]
