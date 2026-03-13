from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
from uuid import uuid4

import pytest

from app.models import DocumentSnapshot


def _load_snapshots_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "snapshots.py"
    deps_module = ModuleType("app.api.deps")
    deps_module.get_db = lambda: None
    deps_module.get_current_user = lambda: None
    sys.modules["app.api.deps"] = deps_module

    spec = importlib.util.spec_from_file_location("snapshot_api_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshots = _load_snapshots_module()


class _FakeQuery:
    def __init__(self, result: DocumentSnapshot | None) -> None:
        self._result = result

    def filter(self, *args, **kwargs) -> "_FakeQuery":
        return self

    def first(self) -> DocumentSnapshot | None:
        return self._result


class _FakeSession:
    def __init__(self, results: list[DocumentSnapshot | None]) -> None:
        self._results = list(results)

    def query(self, model: type[DocumentSnapshot]) -> _FakeQuery:
        assert model is DocumentSnapshot
        return _FakeQuery(self._results.pop(0))


def test_compute_full_diff_returns_all_lines() -> None:
    old_text = "alpha\nbeta\ngamma"
    new_text = "alpha\nbeta updated\ngamma\ndelta"

    diff_lines, stats = snapshots._compute_full_diff(old_text, new_text)

    assert [(line.type, line.content, line.line_number) for line in diff_lines] == [
        ("unchanged", "alpha", 1),
        ("deleted", "beta", 2),
        ("added", "beta updated", 2),
        ("unchanged", "gamma", 3),
        ("added", "delta", 4),
    ]
    assert stats.additions == 2
    assert stats.deletions == 1
    assert stats.unchanged == 2


def test_get_snapshot_full_diff_returns_snapshot_diff_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_uuid = uuid4()
    paper_id = str(paper_uuid)
    user = SimpleNamespace(id=uuid4())
    created_at = datetime.now(timezone.utc)

    snapshot1 = DocumentSnapshot(
        id=uuid4(),
        paper_id=paper_uuid,
        yjs_state=b"",
        materialized_text="intro\nbody\nsummary",
        snapshot_type="manual",
        sequence_number=1,
        created_by=user.id,
        created_at=created_at,
        text_length=18,
    )
    snapshot2 = DocumentSnapshot(
        id=uuid4(),
        paper_id=paper_uuid,
        yjs_state=b"",
        materialized_text="intro\nbody updated\nsummary\nappendix",
        snapshot_type="manual",
        sequence_number=2,
        created_by=user.id,
        created_at=created_at,
        text_length=35,
    )
    db = _FakeSession([snapshot1, snapshot2])

    monkeypatch.setattr(snapshots, "_check_paper_access", lambda db, paper_id, user: None)

    response = snapshots.get_snapshot_full_diff(
        paper_id=paper_id,
        from_id=snapshot1.id,
        to_id=snapshot2.id,
        db=db,
        current_user=user,
    )

    assert response.from_snapshot.id == snapshot1.id
    assert response.to_snapshot.id == snapshot2.id
    assert [(line.type, line.content, line.line_number) for line in response.diff_lines] == [
        ("unchanged", "intro", 1),
        ("deleted", "body", 2),
        ("added", "body updated", 2),
        ("unchanged", "summary", 3),
        ("added", "appendix", 4),
    ]
    assert response.stats.additions == 2
    assert response.stats.deletions == 1
    assert response.stats.unchanged == 2
