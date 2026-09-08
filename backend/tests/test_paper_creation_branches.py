"""Regression coverage for shared branch bootstrap and parent-paper validation."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Branch, Commit, ResearchPaper
from app.schemas.branch import BranchCreate
from app.services import paper_service


@pytest.mark.parametrize("failure", [None, "query", "flush", "commit"])
def test_shared_creation_bootstraps_main_nonfatally(failure: str | None) -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    owner_id = uuid4()
    added: list[object] = []

    def add(row: object) -> None:
        if isinstance(row, (ResearchPaper, Branch)):
            row.id = uuid4()
        if isinstance(row, Branch):
            assert db.commit.call_count == 1  # The paper is already committed.
        added.append(row)

    db.add.side_effect = add
    if failure == "query":
        db.query.side_effect = RuntimeError("branch query failed")
    elif failure == "flush":
        db.flush.side_effect = RuntimeError("branch flush failed")
    elif failure == "commit":
        db.commit.side_effect = [None, RuntimeError("branch commit failed"), None]

    with (
        patch.object(paper_service, "_create_initial_snapshot") as snapshot,
        patch.object(paper_service.logger, "exception") as log_exception,
    ):
        paper = paper_service.create_paper(
            db, title="Test paper", owner_id=owner_id,
            content_json={"latex_source": "Initial content"},
        )

    assert paper in added
    assert paper.title == "Test paper"
    snapshot.assert_called_once()
    if failure:
        db.rollback.assert_called_once()
        log_exception.assert_called_once()
    else:
        branch = next(row for row in added if isinstance(row, Branch))
        commit = next(row for row in added if isinstance(row, Commit))
        assert branch.name == "main"
        assert branch.is_main is True
        assert branch.paper_id == paper.id
        assert branch.author_id == owner_id
        assert commit.branch_id == branch.id
        assert commit.content_json == paper.content_json
        assert commit.author_id == owner_id
        assert commit.message == "Initial commit"
        db.rollback.assert_not_called()


def test_main_branch_bootstrap_is_idempotent() -> None:
    db = MagicMock()
    paper = ResearchPaper(id=uuid4())
    db.query.return_value.filter.return_value.first.return_value = Branch(
        id=uuid4(), paper_id=paper.id, name="main", is_main=True,
    )

    paper_service._bootstrap_main_branch(db, paper, uuid4())

    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("parent_kind", ["same_paper", "other_paper", "missing", "none"])
def test_create_branch_validates_parent_paper(parent_kind: str) -> None:
    # Load this router alone to avoid importing unrelated API integrations.
    path = Path(__file__).resolve().parents[1] / "app/api/v1/branches.py"
    spec = importlib.util.spec_from_file_location("branches_api_under_test", path)
    assert spec is not None and spec.loader is not None
    branches = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(branches)

    db = MagicMock()
    user = SimpleNamespace(id=uuid4(), first_name="Test", last_name="User")
    paper = ResearchPaper(id=uuid4(), owner_id=user.id)
    parent_id = uuid4() if parent_kind != "none" else None
    parent = None if parent_kind == "missing" else Branch(
        id=parent_id, paper_id=uuid4() if parent_kind == "other_paper" else paper.id,
    )
    db.query.return_value.filter.return_value.first.side_effect = [None, parent]

    def refresh(branch: Branch) -> None:
        branch.id = uuid4()
        branch.created_at = branch.updated_at = datetime.now(timezone.utc)
        branch.status = "active"

    db.refresh.side_effect = refresh
    request = BranchCreate(name="draft", paper_id=paper.id, parent_branch_id=parent_id)

    with patch.object(branches, "require_paper_editor", return_value=paper) as guard:
        if parent_kind in {"other_paper", "missing"}:
            with pytest.raises(HTTPException) as exc:
                branches.create_branch(request, db, user)
            assert exc.value.status_code == (400 if parent_kind == "other_paper" else 404)
            db.add.assert_not_called()
            db.commit.assert_not_called()
        else:
            response = branches.create_branch(request, db, user)
            assert response.paper_id == paper.id
            assert response.parent_branch_id == parent_id
            db.commit.assert_called_once()
        guard.assert_called_once_with(db, paper.id, user)
