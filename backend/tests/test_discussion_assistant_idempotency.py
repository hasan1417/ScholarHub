"""A retried non-streaming assistant request answers with the original exchange."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.discussion import assistant as assistant_module
from app.schemas.project_discussion import DiscussionAssistantResponse


def _db_returning(exchange) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = exchange
    return db


def test_completed_duplicate_returns_the_stored_response() -> None:
    stored = DiscussionAssistantResponse(
        message="Original answer", citations=[], reasoning_used=False,
        model="openai/gpt-4o", usage=None, suggested_actions=[],
    ).model_dump(mode="json")
    exchange = SimpleNamespace(status="completed", response=stored)

    result = assistant_module._duplicate_exchange_response(_db_returning(exchange), uuid4(), uuid4(), str(uuid4()))

    assert result.message == "Original answer"
    assert result.model == "openai/gpt-4o"


@pytest.mark.parametrize("exchange", [None, SimpleNamespace(status="processing", response={})])
def test_in_flight_or_foreign_duplicate_is_a_409_with_the_exchange_id(exchange) -> None:
    existing_id = str(uuid4())
    with pytest.raises(HTTPException) as excinfo:
        assistant_module._duplicate_exchange_response(_db_returning(exchange), uuid4(), uuid4(), existing_id)
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == {
        "error": "duplicate_request",
        "message": "This request is already being processed.",
        "exchange_id": existing_id,
    }


def test_failed_original_lets_the_retry_run() -> None:
    exchange = SimpleNamespace(status="failed", response={})
    assert assistant_module._duplicate_exchange_response(_db_returning(exchange), uuid4(), uuid4(), str(uuid4())) is None


def test_lookup_is_scoped_to_channel_and_author() -> None:
    db = _db_returning(None)
    channel_id, author_id = uuid4(), uuid4()
    with pytest.raises(HTTPException):
        assistant_module._duplicate_exchange_response(db, channel_id, author_id, str(uuid4()))
    clauses = [str(clause) for clause in db.query.return_value.filter.call_args.args]
    assert any("channel_id" in clause for clause in clauses)
    assert any("author_id" in clause for clause in clauses)


def test_malformed_existing_id_never_queries() -> None:
    db = _db_returning(None)
    with pytest.raises(HTTPException):
        assistant_module._duplicate_exchange_response(db, uuid4(), uuid4(), "not-a-uuid")
    db.query.assert_not_called()
