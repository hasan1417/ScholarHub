"""Regression coverage for provider threads and streaming session ownership."""

import asyncio
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator
from app.services.discussion_ai.route_classifier import RouteDecision
from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator


@pytest.mark.asyncio
async def test_streaming_classifier_leaves_event_loop_free(monkeypatch: pytest.MonkeyPatch) -> None:
    loop_thread = threading.get_ident()
    started = threading.Event()
    release = threading.Event()
    provider_threads = []
    orchestrator = object.__new__(ToolOrchestrator)
    orchestrator._build_request_context = MagicMock(return_value={})
    orchestrator._get_ai_memory = MagicMock(return_value={"facts": {}})
    orchestrator._build_messages_lite = MagicMock(return_value=[])

    def classify(*args: Any, **kwargs: Any) -> RouteDecision:
        provider_threads.append(threading.get_ident())
        started.set()
        assert release.wait(2), "Event loop could not release the blocking provider"
        return RouteDecision("lite", "test")

    async def execute(*args: Any) -> Any:
        yield {"type": "result", "data": {"ok": True}}

    monkeypatch.setattr("app.services.discussion_ai.route_classifier.classify_route", classify)
    orchestrator._execute_lite_streaming = execute

    async def collect() -> list[dict[str, Any]]:
        return [event async for event in orchestrator.handle_message_streaming(
            SimpleNamespace(), SimpleNamespace(is_paper_chat=False), "a little more",
        )]

    task = asyncio.create_task(collect())
    try:
        while not started.is_set():
            await asyncio.sleep(0.001)
        assert len(provider_threads) == 1
        assert provider_threads[0] != loop_thread
        release.set()
        events = await task
        assert events[-1]["data"]["ok"] is True
    finally:
        release.set()
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["tools", "memory"])
async def test_streaming_worker_owns_session_and_entities(
    monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    loop_thread = threading.get_ident()
    request_db = MagicMock()
    entities = {key: SimpleNamespace(id=key) for key in ("project", "channel", "current_user")}
    ctx = {**entities, "user_message": "test", "conversation_history": [], "papers_requested": 0}
    sessions = []

    class WorkerSession:
        def __init__(self) -> None:
            assert threading.get_ident() != loop_thread
            self.thread = threading.get_ident()
            self.closed = False
            sessions.append(self)

        def __enter__(self) -> "WorkerSession":
            return self

        def __exit__(self, *args: Any) -> None:
            assert threading.get_ident() == self.thread
            self.closed = True

        def get(self, model: Any, entity_id: str) -> SimpleNamespace:
            assert threading.get_ident() == self.thread
            return SimpleNamespace(id=entity_id, worker=True)

    def execute(self: OpenRouterOrchestrator, calls: Any, worker_ctx: dict[str, Any]) -> list[Any]:
        assert self.db is sessions[0]
        for key in entities:
            assert worker_ctx[key] is not entities[key]
            assert worker_ctx[key].worker
        worker_ctx["papers_requested"] = 3
        return [{"name": "test", "result": {"status": "success"}}]

    def update(self: OpenRouterOrchestrator, channel: Any, *args: Any) -> str:
        assert self.db is sessions[0]
        assert channel is not entities["channel"]
        assert channel.worker
        return "updated"

    monkeypatch.setattr("app.database.SessionLocal", WorkerSession)
    monkeypatch.setattr(OpenRouterOrchestrator, "_execute_tool_calls", execute)
    monkeypatch.setattr(OpenRouterOrchestrator, "update_memory_after_exchange", update)
    orchestrator = object.__new__(OpenRouterOrchestrator)
    orchestrator.db = request_db
    if operation == "tools":
        result = await orchestrator._run_streaming_db_work(ctx, tool_calls=[])
        assert result[0]["result"]["status"] == "success"
        assert ctx["papers_requested"] == 3
    else:
        assert await orchestrator._run_streaming_db_work(ctx, final_message="answer") == "updated"
    assert orchestrator.db is request_db
    assert sessions[0].closed
    for key in entities:
        assert ctx[key] is entities[key]
    assert request_db.expire.call_count == 3
