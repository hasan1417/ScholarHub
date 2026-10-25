"""Blocking providers must leave the API loop available to other requests."""

import asyncio
from threading import Event, get_ident
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.test_ai_billing_integrity import _load_assistant_module


@pytest.mark.parametrize("stream", [False, True])
def test_editor_provider_does_not_block_other_requests(stream: bool) -> None:
    _load_assistant_module()
    from app.api.v1 import ai

    app = FastAPI()
    app.include_router(ai.router)
    request_db = MagicMock()
    app.dependency_overrides[ai.get_db] = lambda: request_db
    app.dependency_overrides[ai.get_current_user] = lambda: SimpleNamespace(id=uuid4())

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    entered, release = Event(), Event()
    provider_threads: list[int] = []

    def generate(**kwargs: Any) -> dict[str, Any]:
        provider_threads.append(get_ident())
        entered.set()
        assert release.wait(3), "API loop failed to release blocking provider"
        return {"generated_text": "Generated answer", "processing_time": 0.1}

    def generate_stream(**kwargs: Any) -> Iterator[str]:
        yield generate(**kwargs)["generated_text"]

    async def exercise() -> None:
        loop_thread = get_ident()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = "/writing/generate/stream" if stream else "/writing/generate"
            task = asyncio.create_task(client.post(path, json={"text": "Draft", "instruction": "expand"}))
            try:
                assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 2), timeout=2.5)
                response = await asyncio.wait_for(client.get("/ping"), timeout=0.5)
                assert response.json() == {"ok": True}
                assert len(provider_threads) == 1
                assert provider_threads[0] != loop_thread
            finally:
                release.set()
                result = await task
            assert result.status_code == 200
            assert "Generated answer" in result.text

    with (
        patch.object(ai.ai_service, "initialization_status", "ready"),
        patch.object(ai.ai_service, "generate_text", side_effect=generate),
        patch.object(ai.ai_service, "stream_generate_text", side_effect=generate_stream),
        patch.object(ai, "_admit_editor_ai_usage", return_value=5),
        patch.object(ai, "build_allowed_citation_keys", return_value=set()),
        patch.object(ai, "_filter_ai_response_text", return_value=("Generated answer", [])),
        patch.object(ai, "_increment_editor_ai_usage"),
        patch.object(ai, "_increment_editor_ai_usage_in_new_session"),
    ):
        asyncio.run(exercise())


@pytest.mark.parametrize("fail", [False, True])
def test_discussion_worker_owns_session_and_reloads_entities(fail: bool) -> None:
    assistant = _load_assistant_module()
    worker_db = MagicMock()
    project_id, channel_id, user_id = uuid4(), uuid4(), uuid4()
    entities = [SimpleNamespace(id=entity_id) for entity_id in (project_id, channel_id, user_id)]
    worker_db.get.side_effect = entities
    threads: list[int] = []

    def create_session() -> MagicMock:
        threads.append(get_ident())
        return worker_db

    def handle(project: Any, channel: Any, question: str, **kwargs: Any) -> dict[str, Any]:
        threads.append(get_ident())
        assert project is entities[0]
        assert channel is entities[1]
        assert kwargs["current_user"] is entities[2]
        if fail:
            raise RuntimeError("provider failed")
        return {"message": "Answer"}

    orchestrator = MagicMock()
    orchestrator.handle_message.side_effect = handle
    worker_db.close.side_effect = lambda: threads.append(get_ident())

    async def exercise() -> None:
        loop_thread = get_ident()
        call = asyncio.to_thread(
            assistant._handle_message_in_new_session,
            project_id, channel_id, user_id, "test-model", "test-key", "Question",
        )
        if fail:
            with pytest.raises(RuntimeError, match="provider failed"):
                await call
        else:
            assert await call == {"message": "Answer"}
        assert len(threads) == 3
        assert len(set(threads)) == 1
        assert threads[0] != loop_thread

    with (
        patch.object(assistant, "SessionLocal", side_effect=create_session),
        patch.object(assistant, "OpenRouterOrchestrator", return_value=orchestrator) as factory,
    ):
        asyncio.run(exercise())
    assert factory.call_args.args[1] is worker_db
    worker_db.close.assert_called_once()
