"""Regression tests for AI provider failures and usage accounting."""

import asyncio
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.sql.dml import Update

from app.schemas.project_discussion import DiscussionAssistantRequest
from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator
from app.services.subscription_service import SubscriptionService, get_model_credit_cost


_MISSING_MODULE = object()


def _load_assistant_module() -> ModuleType:
    previous_modules: dict[str, object] = {}

    try:
        try:
            import authlib  # noqa: F401
        except ModuleNotFoundError:
            authlib_module = ModuleType("authlib")
            integrations_module = ModuleType("authlib.integrations")
            starlette_client_module = ModuleType("authlib.integrations.starlette_client")
            starlette_client_module.OAuth = type(
                "OAuth",
                (),
                {"register": lambda self, **kwargs: None},
            )
            stub_modules = {
                "authlib": authlib_module,
                "authlib.integrations": integrations_module,
                "authlib.integrations.starlette_client": starlette_client_module,
            }
            previous_modules = {
                name: sys.modules.get(name, _MISSING_MODULE) for name in stub_modules
            }
            sys.modules.update(stub_modules)

        from app.api.v1.discussion import assistant

        return assistant
    finally:
        for name, previous_module in reversed(previous_modules.items()):
            if previous_module is _MISSING_MODULE:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module


def test_feature_limit_accounts_for_pending_credit_cost() -> None:
    db = MagicMock()
    usage = SimpleNamespace(discussion_ai_calls=45)

    with (
        patch.object(SubscriptionService, "get_user_limits", return_value={"discussion_ai_calls": 50}),
        patch.object(SubscriptionService, "get_or_create_usage", return_value=usage),
    ):
        assert SubscriptionService.check_feature_limit(
            db, uuid4(), "discussion_ai_calls", amount=5
        ) == (True, 45, 50)

        usage.discussion_ai_calls = 46
        assert SubscriptionService.check_feature_limit(
            db, uuid4(), "discussion_ai_calls", amount=5
        ) == (False, 46, 50)


def test_direct_openai_model_ids_use_the_same_credit_policy() -> None:
    assert get_model_credit_cost("gpt-5-mini") == 5
    assert get_model_credit_cost("text-embedding-3-small") == 1


def test_increment_usage_uses_atomic_update() -> None:
    db = MagicMock()
    usage = SimpleNamespace(id=uuid4(), editor_ai_calls=7)

    with patch.object(SubscriptionService, "get_or_create_usage", return_value=usage):
        SubscriptionService.increment_usage(db, uuid4(), "editor_ai_calls", amount=5)

    statement = db.execute.call_args.args[0]
    assert isinstance(statement, Update)
    assert "editor_ai_calls=(usage_tracking.editor_ai_calls+" in str(statement).replace(" ", "")
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(usage)


def test_increment_usage_rejects_unknown_column() -> None:
    db = MagicMock()

    with pytest.raises(ValueError, match="Unknown usage feature"):
        SubscriptionService.increment_usage(db, uuid4(), "unsafe_column", amount=1)

    db.execute.assert_not_called()


@pytest.fixture
def openrouter_orchestrator() -> OpenRouterOrchestrator:
    with patch("app.services.discussion_ai.openrouter_orchestrator.settings") as mock_settings:
        mock_settings.OPENROUTER_API_KEY = "test-key"
        mock_settings.REDIS_URL = "redis://localhost"
        mock_settings.OPENROUTER_FALLBACK_MODELS_PATH = None
        orchestrator = OpenRouterOrchestrator(
            ai_service=MagicMock(),
            db=MagicMock(),
            model="openai/gpt-4o",
            user_api_key="test-key",
        )
    orchestrator._get_tools_for_user = MagicMock(return_value=[])
    return orchestrator


def test_successful_answer_starting_with_error_is_not_a_failure(
    openrouter_orchestrator: OpenRouterOrchestrator,
) -> None:
    message = MagicMock(content="Error: this heading is part of the requested answer", tool_calls=None)
    openrouter_orchestrator.openrouter_client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=message)])
    )

    result = openrouter_orchestrator._call_ai_with_tools([], {})

    assert result["ok"] is True
    assert result["content"].startswith("Error:")


def test_lite_provider_failure_has_no_cheerful_fallback(
    openrouter_orchestrator: OpenRouterOrchestrator,
) -> None:
    openrouter_orchestrator.openrouter_client.chat.completions.create = MagicMock(
        side_effect=RuntimeError("provider outage")
    )

    result = openrouter_orchestrator._execute_lite([], {"project": SimpleNamespace(title="Test")})

    assert result["ok"] is False
    assert "Got it!" not in result["message"]


def _discussion_dependencies() -> tuple[MagicMock, SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    project = SimpleNamespace(
        id=uuid4(),
        created_by=uuid4(),
        discussion_settings={
            "enabled": True,
            "model": "openai/gpt-5.2-20251211",
            "use_owner_key_for_team": False,
        },
    )
    channel = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(
        id=uuid4(),
        email="billing-test@example.com",
        first_name="Billing",
        last_name="Test",
    )
    return db, project, channel, user


def test_json_provider_failure_is_persisted_failed_and_not_billed() -> None:
    assistant_module = _load_assistant_module()
    db, project, channel, user = _discussion_dependencies()
    failure = {
        "ok": False,
        "error": {
            "code": "provider_unavailable",
            "message": "The AI provider is temporarily unavailable. Please try again.",
            "retryable": True,
            "status_code": 503,
        },
        "message": "Please try again.",
        "actions": [],
        "citations": [],
        "conversation_state": {},
    }
    orchestrator = MagicMock()
    orchestrator.handle_message.return_value = failure

    with (
        patch.object(assistant_module, "get_project_or_404", return_value=project),
        patch.object(assistant_module, "ensure_project_member"),
        patch.object(assistant_module, "_get_channel_or_404", return_value=channel),
        patch.object(
            assistant_module,
            "resolve_openrouter_key_for_project",
            return_value={"api_key": "test-key", "source": "user"},
        ),
        patch.object(assistant_module, "OpenRouterOrchestrator", return_value=orchestrator),
        patch.object(assistant_module, "_persist_assistant_exchange") as persist,
        patch.object(SubscriptionService, "check_feature_limit", return_value=(True, 0, 50)) as check,
        patch.object(SubscriptionService, "increment_usage") as increment,
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                assistant_module.invoke_discussion_assistant(
                    str(project.id),
                    channel.id,
                    DiscussionAssistantRequest(question="hello"),
                    BackgroundTasks(),
                    stream=False,
                    db=db,
                    current_user=user,
                )
            )

    assert exc_info.value.status_code == 503
    assert persist.call_args.kwargs["status"] == "failed"
    increment.assert_not_called()
    check.assert_called_once_with(db, user.id, "discussion_ai_calls", amount=5)


def test_json_answer_starting_with_error_is_completed_and_billed() -> None:
    assistant_module = _load_assistant_module()
    db, project, channel, user = _discussion_dependencies()
    orchestrator = MagicMock()
    orchestrator.handle_message.return_value = {
        "message": "Error: this is a valid heading in the requested answer.",
        "actions": [],
        "citations": [],
        "conversation_state": {},
    }

    with (
        patch.object(assistant_module, "get_project_or_404", return_value=project),
        patch.object(assistant_module, "ensure_project_member"),
        patch.object(assistant_module, "_get_channel_or_404", return_value=channel),
        patch.object(
            assistant_module,
            "resolve_openrouter_key_for_project",
            return_value={"api_key": "test-key", "source": "user"},
        ),
        patch.object(assistant_module, "OpenRouterOrchestrator", return_value=orchestrator),
        patch.object(assistant_module, "_persist_assistant_exchange") as persist,
        patch.object(SubscriptionService, "check_feature_limit", return_value=(True, 0, 50)),
        patch.object(SubscriptionService, "increment_usage") as increment,
    ):
        response = asyncio.run(
            assistant_module.invoke_discussion_assistant(
                str(project.id),
                channel.id,
                DiscussionAssistantRequest(question="use an Error heading"),
                BackgroundTasks(),
                stream=False,
                db=db,
                current_user=user,
            )
        )

    assert response.message.startswith("Error:")
    assert persist.call_args.kwargs["status"] == "completed"
    increment.assert_called_once_with(
        db,
        user.id,
        "discussion_ai_calls",
        amount=5,
    )


def test_sse_provider_failure_emits_error_and_is_not_billed() -> None:
    assistant_module = _load_assistant_module()
    db, project, channel, user = _discussion_dependencies()
    failure = {
        "ok": False,
        "error": {
            "code": "provider_unavailable",
            "message": "The AI provider is temporarily unavailable. Please try again.",
            "retryable": True,
            "status_code": 503,
        },
        "message": "Please try again.",
        "actions": [],
        "citations": [],
        "conversation_state": {},
    }

    class StreamingFailureOrchestrator:
        async def handle_message_streaming(self, *args, **kwargs):
            yield {"type": "result", "data": failure}

    async def invoke_and_collect() -> str:
        response = await assistant_module.invoke_discussion_assistant(
            str(project.id),
            channel.id,
            DiscussionAssistantRequest(question="hello"),
            BackgroundTasks(),
            stream=True,
            db=db,
            current_user=user,
        )
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    with (
        patch.object(assistant_module, "get_project_or_404", return_value=project),
        patch.object(assistant_module, "ensure_project_member"),
        patch.object(assistant_module, "_get_channel_or_404", return_value=channel),
        patch.object(
            assistant_module,
            "resolve_openrouter_key_for_project",
            return_value={"api_key": "test-key", "source": "user"},
        ),
        patch.object(
            assistant_module,
            "OpenRouterOrchestrator",
            return_value=StreamingFailureOrchestrator(),
        ),
        patch.object(assistant_module, "_persist_assistant_exchange") as persist,
        patch.object(assistant_module, "_broadcast_discussion_event", new_callable=AsyncMock),
        patch.object(SubscriptionService, "check_feature_limit", return_value=(True, 0, 50)),
        patch.object(SubscriptionService, "increment_usage") as increment,
    ):
        body = asyncio.run(invoke_and_collect())

    assert '"type": "error"' in body
    assert '"retryable": true' in body
    statuses = [call.args[8] for call in persist.call_args_list]
    assert statuses == ["processing", "failed"]
    increment.assert_not_called()


def test_sse_success_uses_fresh_session_for_usage_increment() -> None:
    assistant_module = _load_assistant_module()
    db, project, channel, user = _discussion_dependencies()
    success = {
        "message": "Completed answer",
        "actions": [],
        "citations": [],
        "conversation_state": {},
    }

    class StreamingSuccessOrchestrator:
        async def handle_message_streaming(self, *args, **kwargs):
            yield {"type": "result", "data": success}

    usage_db = MagicMock()

    async def invoke_and_collect() -> str:
        response = await assistant_module.invoke_discussion_assistant(
            str(project.id),
            channel.id,
            DiscussionAssistantRequest(question="hello"),
            BackgroundTasks(),
            stream=True,
            db=db,
            current_user=user,
        )
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        await asyncio.sleep(0.05)
        return "".join(chunks)

    with (
        patch.object(assistant_module, "get_project_or_404", return_value=project),
        patch.object(assistant_module, "ensure_project_member"),
        patch.object(assistant_module, "_get_channel_or_404", return_value=channel),
        patch.object(
            assistant_module,
            "resolve_openrouter_key_for_project",
            return_value={"api_key": "test-key", "source": "user"},
        ),
        patch.object(
            assistant_module,
            "OpenRouterOrchestrator",
            return_value=StreamingSuccessOrchestrator(),
        ),
        patch.object(assistant_module, "_persist_assistant_exchange"),
        patch.object(assistant_module, "_broadcast_discussion_event", new_callable=AsyncMock),
        patch.object(assistant_module, "SessionLocal", return_value=usage_db),
        patch.object(SubscriptionService, "check_feature_limit", return_value=(True, 0, 50)),
        patch.object(SubscriptionService, "increment_usage") as increment,
    ):
        body = asyncio.run(invoke_and_collect())

    assert '"type": "result"' in body
    increment.assert_called_once_with(
        usage_db,
        user.id,
        "discussion_ai_calls",
        5,
    )
    usage_db.close.assert_called_once()
