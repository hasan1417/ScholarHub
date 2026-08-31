"""Regression tests for discussion-AI cross-project resource scoping."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.project_discussion import ChannelScopeConfig
from app.services.discussion_ai.mixins.library_tools_mixin import LibraryToolsMixin
from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator


@pytest.mark.parametrize(
    "scope_field",
    ["paper_ids", "reference_ids", "meeting_ids"],
)
def test_channel_scope_rejects_ids_outside_project(scope_field: str) -> None:
    pytest.importorskip("authlib")
    from app.api.v1.discussion.channels import _validate_channel_scope

    resource_id = uuid4()
    scope = ChannelScopeConfig(**{scope_field: [resource_id]})
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with pytest.raises(HTTPException) as exc_info:
        _validate_channel_scope(db, uuid4(), scope)

    assert exc_info.value.status_code == 400
    assert scope_field in exc_info.value.detail
    assert str(resource_id) in exc_info.value.detail


def test_channel_scope_accepts_only_project_linked_resources() -> None:
    pytest.importorskip("authlib")
    from app.api.v1.discussion.channels import _validate_channel_scope

    project_id = uuid4()
    paper_id = uuid4()
    reference_id = uuid4()
    meeting_id = uuid4()
    scope = ChannelScopeConfig(
        paper_ids=[paper_id],
        reference_ids=[reference_id],
        meeting_ids=[meeting_id],
    )
    db = MagicMock()
    queries = [MagicMock(), MagicMock(), MagicMock()]
    queries[0].filter.return_value.all.return_value = [(paper_id,)]
    queries[1].filter.return_value.all.return_value = [(reference_id,)]
    queries[2].filter.return_value.all.return_value = [(meeting_id,)]
    db.query.side_effect = queries

    _validate_channel_scope(db, project_id, scope)

    for query in queries:
        filter_conditions = query.filter.call_args.args
        assert len(filter_conditions) == 2
        assert any("project_id" in str(condition) for condition in filter_conditions)


def test_update_paper_rejects_out_of_scope_id_without_mutation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.first.return_value = None
    tools = LibraryToolsMixin()
    tools.db = db
    project = SimpleNamespace(id=uuid4())

    with caplog.at_level(logging.WARNING):
        result = tools._tool_update_paper(
            {"project": project},
            str(uuid4()),
            "replacement content",
        )

    assert result == {"status": "error", "message": "Paper not found"}
    assert len(query.filter.call_args.args) == 2
    assert any(
        "research_papers.project_id" in str(condition)
        for condition in query.filter.call_args.args
    )
    db.commit.assert_not_called()
    assert "out-of-scope paper update" in caplog.text


def test_paper_chat_drops_reference_not_linked_to_project(
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = MagicMock()
    query = db.query.return_value
    scoped_query = query.join.return_value.filter.return_value
    scoped_query.first.return_value = None
    orchestrator = object.__new__(ToolOrchestrator)
    orchestrator.db = db
    project = SimpleNamespace(id=uuid4())

    with caplog.at_level(logging.WARNING):
        context = orchestrator._build_paper_chat_context(project, str(uuid4()))

    assert context == ""
    query.join.assert_called_once()
    assert len(query.join.return_value.filter.call_args.args) == 2
    assert any(
        "project_references.project_id" in str(condition)
        for condition in query.join.return_value.filter.call_args.args
    )
    assert "Dropped 1" in caplog.text
