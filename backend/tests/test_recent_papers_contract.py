"""
Contract tests for recent-papers state flow.

Verifies the single source of truth for recent search results:
1. Within-turn: search_papers -> add_to_library sees papers via ctx
2. Within-turn: search_papers -> get_recent_search_results sees papers via ctx
3. _set_recent_papers updates both ctx and Redis
4. _get_recent_papers reads from ctx

Run with: pytest tests/test_recent_papers_contract.py -v
"""

import os
import sys
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────

FAKE_PAPERS = [
    {
        "id": "10.1234/paper1",
        "title": "Attention Is All You Need",
        "authors": ["Vaswani, A.", "Shazeer, N."],
        "year": 2017,
        "abstract": "The dominant sequence transduction models...",
        "doi": "10.1234/paper1",
        "url": "https://example.com/paper1",
        "pdf_url": "https://example.com/paper1.pdf",
        "source": "semantic_scholar",
        "is_open_access": True,
        "journal": "NeurIPS",
    },
    {
        "id": "10.1234/paper2",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "authors": ["Devlin, J.", "Chang, M."],
        "year": 2019,
        "abstract": "We introduce a new language representation model...",
        "doi": "10.1234/paper2",
        "url": "https://example.com/paper2",
        "pdf_url": None,
        "source": "openalex",
        "is_open_access": False,
        "journal": "NAACL",
    },
    {
        "id": "10.1234/paper3",
        "title": "GPT-4 Technical Report",
        "authors": ["OpenAI"],
        "year": 2023,
        "abstract": "We report the development of GPT-4...",
        "doi": "10.1234/paper3",
        "url": "https://example.com/paper3",
        "pdf_url": "https://example.com/paper3.pdf",
        "source": "semantic_scholar",
        "is_open_access": True,
        "journal": "arXiv",
    },
]


class MockProject:
    def __init__(self):
        self.id = str(uuid4())
        self.title = "Test Project"
        self.idea = "Test idea"
        self.scope = None
        self.keywords = ["ML", "NLP"]
        self.created_by = str(uuid4())


class MockChannel:
    def __init__(self):
        self.id = str(uuid4())
        self.name = "test-channel"
        self.ai_memory = None


class MockDB:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def query(self, *args, **kwargs):
        return MockQuery()

    def add(self, *args):
        pass

    def refresh(self, *args):
        pass


class MockQuery:
    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def count(self):
        return 0

    def limit(self, n):
        return self

    def first(self):
        return None

    def all(self):
        return []

    def order_by(self, *args):
        return self


class MockAIService:
    def __init__(self):
        self.default_model = "gpt-5-mini"


def _make_ctx(project=None, channel=None, recent_search_results=None):
    """Build a minimal ctx dict matching _build_ctx() output."""
    return {
        "project": project or MockProject(),
        "channel": channel or MockChannel(),
        "current_user": MagicMock(id=str(uuid4())),
        "user_role": "admin",
        "is_owner": True,
        "recent_search_results": recent_search_results or [],
        "recent_search_id": None,
        "reasoning_mode": False,
        "max_papers": 999,
        "papers_requested": 0,
        "user_message": "",
        "conversation_history": [],
    }


# ── Helper tests ─────────────────────────────────────────────────────

class TestRecentPapersHelpers:
    """Test _get_recent_papers and _set_recent_papers."""

    def setup_method(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
        self.orch = ToolOrchestrator(MockAIService(), MockDB())

    def test_get_recent_papers_empty_ctx(self):
        ctx = _make_ctx()
        assert self.orch._get_recent_papers(ctx) == []

    def test_get_recent_papers_with_data(self):
        ctx = _make_ctx(recent_search_results=FAKE_PAPERS)
        result = self.orch._get_recent_papers(ctx)
        assert len(result) == 3
        assert result[0]["title"] == "Attention Is All You Need"

    @patch("app.services.discussion_ai.search_cache.store_search_results")
    def test_set_recent_papers_updates_ctx(self, mock_store):
        ctx = _make_ctx()
        assert ctx["recent_search_results"] == []

        self.orch._set_recent_papers(ctx, FAKE_PAPERS, search_id="test-id")

        assert ctx["recent_search_results"] == FAKE_PAPERS
        assert len(ctx["recent_search_results"]) == 3

    @patch("app.services.discussion_ai.search_cache.store_search_results")
    def test_set_recent_papers_persists_to_redis(self, mock_store):
        ctx = _make_ctx()
        self.orch._set_recent_papers(ctx, FAKE_PAPERS, search_id="test-id")

        mock_store.assert_called_once_with("test-id", FAKE_PAPERS)

    @patch("app.services.discussion_ai.search_cache.store_search_results")
    def test_set_recent_papers_skips_redis_without_search_id(self, mock_store):
        ctx = _make_ctx()
        self.orch._set_recent_papers(ctx, FAKE_PAPERS)

        mock_store.assert_not_called()
        # But ctx is still updated
        assert ctx["recent_search_results"] == FAKE_PAPERS


# ── Within-turn contract tests ───────────────────────────────────────

class TestWithinTurnChaining:
    """Contract: tools chained within a single turn share state via ctx."""

    def setup_method(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
        self.orch = ToolOrchestrator(MockAIService(), MockDB())

    @patch("app.services.discussion_ai.search_cache.store_search_results")
    def test_search_then_add_to_library(self, mock_store):
        """search_papers -> add_to_library: add_to_library must see the papers."""
        ctx = _make_ctx()

        # Simulate what search_papers does after finding papers
        self.orch._set_recent_papers(ctx, FAKE_PAPERS, search_id="search-123")

        # Now add_to_library reads via _get_recent_papers
        recent = self.orch._get_recent_papers(ctx)
        assert len(recent) == 3, "add_to_library must see papers from search_papers"
        assert recent[0]["title"] == "Attention Is All You Need"
        assert recent[1]["doi"] == "10.1234/paper2"

    @patch("app.services.discussion_ai.search_cache.store_search_results")
    def test_search_then_get_recent_search_results(self, mock_store):
        """search_papers -> get_recent_search_results: must return non-empty."""
        ctx = _make_ctx()

        # Simulate search_papers
        self.orch._set_recent_papers(ctx, FAKE_PAPERS, search_id="search-456")

        # get_recent_search_results calls _get_recent_papers internally
        result = self.orch._tool_get_recent_search_results(ctx)
        assert result["count"] == 3, "get_recent_search_results must see papers"
        assert len(result["papers"]) == 3

    @patch("app.services.discussion_ai.search_cache.store_search_results")
    def test_search_overwrites_previous_results(self, mock_store):
        """A second search_papers call replaces results from the first."""
        ctx = _make_ctx(recent_search_results=FAKE_PAPERS[:1])

        new_papers = FAKE_PAPERS[1:]
        self.orch._set_recent_papers(ctx, new_papers, search_id="search-789")

        recent = self.orch._get_recent_papers(ctx)
        assert len(recent) == 2
        assert recent[0]["title"] == "BERT: Pre-training of Deep Bidirectional Transformers"


# ── Cross-turn contract tests ────────────────────────────────────────

class TestCrossTurnBehavior:
    """Contract: cross-turn state flows through ctx initialization."""

    def setup_method(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
        self.orch = ToolOrchestrator(MockAIService(), MockDB())

    def test_ctx_initialized_with_recent_search_results(self):
        """_build_ctx populates recent_search_results from API layer."""
        project = MockProject()
        channel = MockChannel()
        user = MagicMock(id=str(uuid4()))

        ctx = self.orch._build_request_context(
            project, channel, "test message",
            recent_search_results=FAKE_PAPERS,
            reasoning_mode=False,
            current_user=user,
        )

        assert ctx["recent_search_results"] == FAKE_PAPERS
        assert len(self.orch._get_recent_papers(ctx)) == 3

    def test_ctx_empty_without_recent_search_results(self):
        """_build_ctx defaults to empty when no results from API layer."""
        project = MockProject()
        channel = MockChannel()
        user = MagicMock(id=str(uuid4()))

        ctx = self.orch._build_request_context(
            project, channel, "test message",
            recent_search_results=None,
            reasoning_mode=False,
            current_user=user,
        )

        assert self.orch._get_recent_papers(ctx) == []


# ── Guard test ───────────────────────────────────────────────────────

class TestNoDirectCtxAccess:
    """Guard: mixin files must not read/write ctx['recent_search_results'] directly."""

    def test_no_direct_ctx_access_in_mixins(self):
        """Ensure mixin files use helpers, not raw ctx access."""
        import re

        mixin_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "services", "discussion_ai", "mixins",
        )

        violations = []
        pattern = re.compile(r'ctx\s*[\.\[].*["\']recent_search_results["\']')

        for fname in os.listdir(mixin_dir):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(mixin_dir, fname)
            with open(fpath) as f:
                for lineno, line in enumerate(f, 1):
                    if pattern.search(line):
                        violations.append(f"{fname}:{lineno}: {line.strip()}")

        assert violations == [], (
            "Mixin files must use _get_recent_papers/_set_recent_papers, "
            f"not raw ctx access:\n" + "\n".join(violations)
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
