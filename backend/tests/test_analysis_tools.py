"""
Tests for AnalysisToolsMixin: trigger_search_ui, focus_on_papers,
analyze_across_papers, and generate_section_from_discussion.

Uses a concrete test class that inherits from AnalysisToolsMixin and
provides mock implementations of the required interface methods.
All DB and external calls are mocked -- no real database sessions.
"""

import uuid
from unittest.mock import MagicMock

from app.services.discussion_ai.mixins.analysis_tools_mixin import AnalysisToolsMixin


# ---------------------------------------------------------------------------
# Concrete test harness that satisfies the mixin contract
# ---------------------------------------------------------------------------

class ConcreteAnalysisTools(AnalysisToolsMixin):
    """Minimal concrete class that satisfies the mixin contract.

    Provides:
        - self.ai_service
        - self.db
        - self._get_ai_memory(channel) -> dict
        - self._save_ai_memory(channel, memory) -> None
    """

    def __init__(self, ai_service=None, db=None, initial_memory=None):
        self.ai_service = ai_service or MagicMock()
        self.db = db or MagicMock()
        self._memory = initial_memory if initial_memory is not None else {}
        self._saved_memories = []  # track save calls for assertions

    def _get_ai_memory(self, channel):
        return self._memory

    def _save_ai_memory(self, channel, memory):
        self._memory = memory
        self._saved_memories.append(memory.copy())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(project_id=None):
    project = MagicMock()
    project.id = project_id or uuid.uuid4()
    return project


def _make_channel(channel_id=None):
    channel = MagicMock()
    channel.id = channel_id or uuid.uuid4()
    return channel


def _make_reference(
    ref_id=None,
    title="Test Paper",
    doi=None,
    url=None,
    status="pending",
    document_id=None,
    authors=None,
    year=2024,
    abstract="Abstract text",
    summary=None,
    key_findings=None,
    methodology=None,
    limitations=None,
):
    ref = MagicMock()
    ref.id = ref_id or uuid.uuid4()
    ref.title = title
    ref.doi = doi
    ref.url = url
    ref.status = status
    ref.document_id = document_id
    ref.authors = authors or ["Author A", "Author B"]
    ref.year = year
    ref.abstract = abstract
    ref.summary = summary
    ref.key_findings = key_findings
    ref.methodology = methodology
    ref.limitations = limitations
    return ref


def _search_result(title="Search Paper", doi=None, abstract="An abstract", year=2023, **kwargs):
    result = {
        "title": title,
        "doi": doi,
        "abstract": abstract,
        "year": year,
        "authors": "Jane Doe, John Smith",
        "url": "https://example.com/paper",
        "pdf_url": None,
        "is_open_access": False,
    }
    result.update(kwargs)
    return result


# ===================================================================
# 1. _tool_trigger_search_ui
# ===================================================================

class TestTriggerSearchUI:
    """Tests for _tool_trigger_search_ui."""

    def test_basic_return_structure(self):
        """Should return success status with action payload."""
        tools = ConcreteAnalysisTools()
        channel = _make_channel()
        ctx = {"channel": channel}

        result = tools._tool_trigger_search_ui(ctx, research_question="quantum computing")

        assert result["status"] == "success"
        assert "quantum computing" in result["message"]
        assert result["research_question"] == "quantum computing"
        assert "action" in result
        assert "next_step" in result

    def test_action_payload_structure(self):
        """Action payload should contain type and correct payload fields."""
        tools = ConcreteAnalysisTools()
        ctx = {"channel": _make_channel()}

        result = tools._tool_trigger_search_ui(ctx, research_question="deep learning")

        action = result["action"]
        assert action["type"] == "deep_search_references"
        assert action["payload"]["query"] == "deep learning"
        assert action["payload"]["synthesis_mode"] is True

    def test_max_papers_passed_to_payload(self):
        """max_papers should map to max_results in the action payload."""
        tools = ConcreteAnalysisTools()
        ctx = {"channel": _make_channel()}

        result = tools._tool_trigger_search_ui(ctx, research_question="NLP", max_papers=25)

        assert result["action"]["payload"]["max_results"] == 25

    def test_default_max_papers(self):
        """Default max_papers should be 10."""
        tools = ConcreteAnalysisTools()
        ctx = {"channel": _make_channel()}

        result = tools._tool_trigger_search_ui(ctx, research_question="NLP")

        assert result["action"]["payload"]["max_results"] == 10

    def test_stores_question_in_memory(self):
        """Should store the research question in channel memory."""
        tools = ConcreteAnalysisTools()
        channel = _make_channel()
        ctx = {"channel": channel}

        tools._tool_trigger_search_ui(ctx, research_question="transformer architectures")

        assert tools._memory["search_ui_trigger"]["last_question"] == "transformer architectures"

    def test_preserves_existing_memory(self):
        """Should not overwrite unrelated memory keys."""
        tools = ConcreteAnalysisTools(initial_memory={"summary": "prior context"})
        ctx = {"channel": _make_channel()}

        tools._tool_trigger_search_ui(ctx, research_question="attention mechanisms")

        assert tools._memory["summary"] == "prior context"
        assert tools._memory["search_ui_trigger"]["last_question"] == "attention mechanisms"

    def test_no_channel_skips_memory_save(self):
        """When channel is None, should still return result but skip memory."""
        tools = ConcreteAnalysisTools()
        ctx = {}

        result = tools._tool_trigger_search_ui(ctx, research_question="test")

        assert result["status"] == "success"
        assert len(tools._saved_memories) == 0

    def test_saves_memory_exactly_once(self):
        """Should call _save_ai_memory exactly once when channel is present."""
        tools = ConcreteAnalysisTools()
        ctx = {"channel": _make_channel()}

        tools._tool_trigger_search_ui(ctx, research_question="test")

        assert len(tools._saved_memories) == 1


# ===================================================================
# 2. _tool_focus_on_papers
# ===================================================================

class TestFocusOnPapers:
    """Tests for _tool_focus_on_papers."""

    # ---- From search results (paper_indices) ----

    def test_focus_search_result_by_index(self):
        """Should load a paper from search results by index."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        project = _make_project()
        channel = _make_channel()
        search_results = [_search_result(title="Paper Zero"), _search_result(title="Paper One")]
        ctx = {"project": project, "channel": channel, "recent_search_results": search_results}

        result = tools._tool_focus_on_papers(ctx, paper_indices=[1])

        assert result["status"] == "success"
        assert result["focused_count"] == 1
        # The paper from search result should be marked as search_result source
        focused = tools._memory["focused_papers"]
        assert len(focused) == 1
        assert focused[0]["title"] == "Paper One"
        assert focused[0]["source"] == "search_result"
        assert focused[0]["has_full_text"] is False

    def test_focus_out_of_range_index(self):
        """Out-of-range indices should produce errors, not crash."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result()],
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[5])

        assert result["status"] == "error"
        assert "out of range" in result["errors"][0].lower()

    def test_focus_negative_index(self):
        """Negative indices should produce errors."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result()],
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[-1])

        assert result["status"] == "error"
        assert any("out of range" in e.lower() for e in result["errors"])

    def test_focus_empty_search_results(self):
        """Focusing with indices but no search results should produce errors."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [],
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        assert result["status"] == "error"

    def test_focus_search_result_already_in_library(self):
        """If search result matches a library paper (by DOI), should use library data."""
        ref = _make_reference(
            doi="10.1234/test",
            status="ingested",
            title="Library Paper",
            summary="A great summary",
            key_findings=["Finding 1"],
            methodology="Survey",
            limitations=["Small sample"],
        )
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        search_results = [_search_result(title="Library Paper", doi="10.1234/test")]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        assert result["status"] == "success"
        focused = tools._memory["focused_papers"]
        assert focused[0]["source"] == "library"
        assert focused[0]["has_full_text"] is True
        assert focused[0]["summary"] == "A great summary"

    def test_focus_search_result_matched_by_title(self):
        """Should match library papers by title when DOI is absent."""
        ref = _make_reference(
            doi=None,
            status="ingested",
            title="Exact Title Match",
            summary="Summary from library",
        )
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        search_results = [_search_result(title="Exact Title Match", doi=None)]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        assert result["status"] == "success"
        focused = tools._memory["focused_papers"]
        assert focused[0]["source"] == "library"

    # ---- From library (reference_ids) ----

    def test_focus_by_reference_id(self):
        """Should load a paper from library by reference_id."""
        ref_id = uuid.uuid4()
        ref = _make_reference(
            ref_id=ref_id,
            title="Library Paper",
            status="ingested",
            summary="Great paper",
            key_findings=["Key finding"],
            methodology="RCT",
            limitations=["None"],
        )

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteAnalysisTools(db=db)
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_focus_on_papers(ctx, reference_ids=[str(ref_id)])

        assert result["status"] == "success"
        assert result["focused_count"] == 1
        focused = tools._memory["focused_papers"]
        assert focused[0]["source"] == "library"
        assert focused[0]["reference_id"] == str(ref_id)
        assert focused[0]["has_full_text"] is True

    def test_focus_by_reference_id_pending_status(self):
        """A pending reference (not ingested) should have has_full_text=False."""
        ref_id = uuid.uuid4()
        ref = _make_reference(ref_id=ref_id, title="Pending Paper", status="pending")

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteAnalysisTools(db=db)
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_focus_on_papers(ctx, reference_ids=[str(ref_id)])

        assert result["status"] == "success"
        focused = tools._memory["focused_papers"]
        assert focused[0]["has_full_text"] is False

    def test_focus_by_invalid_uuid(self):
        """Invalid UUID format should produce an error, not crash."""
        tools = ConcreteAnalysisTools()
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_focus_on_papers(ctx, reference_ids=["not-a-uuid"])

        assert result["status"] == "error"
        assert any("Invalid reference ID" in e for e in result["errors"])

    def test_focus_by_nonexistent_reference(self):
        """Reference not found in project should produce an error."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = None

        tools = ConcreteAnalysisTools(db=db)
        ref_id = str(uuid.uuid4())
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_focus_on_papers(ctx, reference_ids=[ref_id])

        assert result["status"] == "error"
        assert any("not found" in e.lower() for e in result["errors"])

    # ---- Multiple papers and mixed sources ----

    def test_focus_multiple_search_results(self):
        """Should handle focusing on multiple search results at once."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        search_results = [
            _search_result(title="Paper A"),
            _search_result(title="Paper B"),
            _search_result(title="Paper C"),
        ]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0, 2])

        assert result["status"] == "success"
        assert result["focused_count"] == 2
        focused = tools._memory["focused_papers"]
        assert focused[0]["title"] == "Paper A"
        assert focused[1]["title"] == "Paper C"

    # ---- Depth info and capabilities ----

    def test_all_abstract_only_depth_info(self):
        """When all papers are abstract-only, depth should be 'shallow'."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result()],
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        assert result["depth_info"]["analysis_depth"] == "shallow"
        assert result["depth_info"]["abstract_only_papers"] == 1

    def test_all_full_text_depth_info(self):
        """When all papers have full text, depth should be 'deep'."""
        ref = _make_reference(doi="10.1234/x", status="ingested", summary="S")
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        search_results = [_search_result(doi="10.1234/x")]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        assert result["depth_info"]["analysis_depth"] == "deep"

    def test_oa_papers_suggestion(self):
        """Papers with pdf_url but not ingested should trigger auto_ingest_suggestion."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        search_results = [_search_result(pdf_url="https://example.com/paper.pdf", is_open_access=True)]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        assert "auto_ingest_suggestion" in result
        assert "oa_papers_available" in result

    # ---- Memory persistence ----

    def test_focused_papers_saved_to_memory(self):
        """Focused papers should be persisted in channel memory."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result(title="Saved Paper")],
        }

        tools._tool_focus_on_papers(ctx, paper_indices=[0])

        assert "focused_papers" in tools._memory
        assert tools._memory["focused_papers"][0]["title"] == "Saved Paper"
        assert len(tools._saved_memories) == 1

    # ---- No inputs ----

    def test_focus_no_indices_no_ids(self):
        """Calling with neither paper_indices nor reference_ids should error."""
        tools = ConcreteAnalysisTools()
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_focus_on_papers(ctx)

        assert result["status"] == "error"

    # ---- Authors formatting ----

    def test_authors_list_joined_for_library_match(self):
        """Library ref with list authors should be joined into a string."""
        ref = _make_reference(
            doi="10.1234/x",
            status="ingested",
            authors=["Alice", "Bob", "Charlie"],
            summary="S",
        )
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result(doi="10.1234/x")],
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        focused = tools._memory["focused_papers"]
        assert focused[0]["authors"] == "Alice, Bob, Charlie"

    def test_authors_string_preserved_for_library_match(self):
        """Library ref with string authors should be kept as-is."""
        ref = _make_reference(
            doi="10.1234/x",
            status="ingested",
            authors="Dr. Smith et al.",
            summary="S",
        )
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result(doi="10.1234/x")],
        }

        result = tools._tool_focus_on_papers(ctx, paper_indices=[0])

        focused = tools._memory["focused_papers"]
        assert focused[0]["authors"] == "Dr. Smith et al."


# ===================================================================
# 3. _tool_analyze_across_papers
# ===================================================================

class TestAnalyzeAcrossPapers:
    """Tests for _tool_analyze_across_papers."""

    def test_no_channel_returns_error(self):
        """Should return error when channel is missing from context."""
        tools = ConcreteAnalysisTools()
        ctx = {"project": _make_project()}

        result = tools._tool_analyze_across_papers(ctx, analysis_question="Compare methods")

        assert result["status"] == "error"
        assert "Channel context" in result["message"]

    def test_no_focused_papers_returns_error(self):
        """Should return error when no papers are focused."""
        tools = ConcreteAnalysisTools(initial_memory={})
        ctx = {"channel": _make_channel(), "project": _make_project()}

        result = tools._tool_analyze_across_papers(ctx, analysis_question="Compare methods")

        assert result["status"] == "error"
        assert "focus_on_papers" in result["message"].lower()
        assert "suggestion" in result

    def test_abstract_only_papers(self):
        """Should handle papers with only abstracts (no RAG)."""
        focused = [
            {
                "title": "Paper A",
                "authors": "Alice",
                "year": 2023,
                "abstract": "Abstract of paper A",
                "doi": None,
                "url": None,
                "has_full_text": False,
            },
            {
                "title": "Paper B",
                "authors": "Bob",
                "year": 2022,
                "abstract": "Abstract of paper B",
                "doi": None,
                "url": None,
                "has_full_text": False,
            },
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        # No project references in DB
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}

        result = tools._tool_analyze_across_papers(ctx, analysis_question="What are the key themes?")

        assert result["status"] == "success"
        assert result["paper_count"] == 2
        assert result["abstract_only_papers"] == 2
        assert result["rag_papers"] == 0
        assert result["retrieval_method"] == "abstracts_only"
        assert "Abstract Only" in result["papers_context"]

    def test_full_text_papers_with_inline_analysis(self):
        """Papers with has_full_text and summary/findings should use inline data."""
        focused = [
            {
                "title": "Full Text Paper",
                "authors": "Alice",
                "year": 2023,
                "abstract": "Abstract",
                "doi": None,
                "url": None,
                "has_full_text": True,
                "summary": "This paper explores X",
                "key_findings": ["Finding 1", "Finding 2"],
                "methodology": "Survey study",
                "limitations": ["Small sample"],
            },
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}

        result = tools._tool_analyze_across_papers(ctx, analysis_question="Summarize methods")

        assert result["status"] == "success"
        assert result["rag_papers"] == 1
        assert result["abstract_only_papers"] == 0
        assert "Full Text" in result["papers_context"]
        assert "Survey study" in result["papers_context"]
        assert "Finding 1" in result["papers_context"]

    def test_rag_retrieval_with_chunks(self):
        """Should use RAG embedding search for papers with document_id."""
        ref_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        ref = _make_reference(ref_id=ref_id, doi="10.1234/rag", document_id=doc_id)

        focused = [
            {
                "title": "RAG Paper",
                "authors": "Alice",
                "year": 2023,
                "abstract": "Abstract",
                "doi": "10.1234/rag",
                "url": None,
                "has_full_text": False,
            },
        ]

        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})

        # Mock DB: project references
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]
        # Mock DB: pgvector query
        chunk_row = MagicMock()
        chunk_row.chunk_text = "Relevant chunk content about methodology"
        chunk_row.similarity = 0.85
        db.execute.return_value.fetchall.return_value = [chunk_row]
        tools.db = db

        # Mock ai_service embedding
        ai_service = MagicMock()
        embedding_response = MagicMock()
        embedding_response.data = [MagicMock(embedding=[0.1] * 1536)]
        ai_service.openai_client.embeddings.create.return_value = embedding_response
        ai_service.embedding_model = "text-embedding-3-small"
        tools.ai_service = ai_service

        ctx = {"channel": _make_channel(), "project": _make_project()}

        result = tools._tool_analyze_across_papers(ctx, analysis_question="What is the methodology?")

        assert result["status"] == "success"
        assert result["rag_papers"] == 1
        assert result["retrieval_method"] == "semantic_search"
        assert "RAG Retrieved" in result["papers_context"]
        assert "Relevant chunk content" in result["papers_context"]

    def test_rag_failure_fallback_to_abstracts(self):
        """RAG failure should fall back to abstract-only analysis with warning."""
        ref_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        ref = _make_reference(ref_id=ref_id, doi="10.1234/fail", document_id=doc_id)

        focused = [
            {
                "title": "Failing RAG Paper",
                "authors": "Bob",
                "year": 2024,
                "abstract": "The abstract",
                "doi": "10.1234/fail",
                "url": None,
                "has_full_text": False,
            },
        ]

        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})

        # Mock DB: project references
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]
        tools.db = db

        # Mock ai_service embedding to raise an exception
        ai_service = MagicMock()
        ai_service.openai_client.embeddings.create.side_effect = Exception("Embedding API down")
        ai_service.embedding_model = "text-embedding-3-small"
        tools.ai_service = ai_service

        ctx = {"channel": _make_channel(), "project": _make_project()}

        result = tools._tool_analyze_across_papers(ctx, analysis_question="Compare findings")

        assert result["status"] == "success"
        # After RAG failure, the paper falls back to abstract-only
        assert result["abstract_only_papers"] == 1
        # depth_info should contain a RAG failure warning
        assert result["depth_info"] is not None
        assert "failed" in result["depth_info"].lower()

    def test_stores_analysis_info_in_memory(self):
        """Should store analysis question and counts in channel memory."""
        focused = [
            {
                "title": "Paper",
                "authors": "Author",
                "year": 2023,
                "abstract": "Abstract",
                "doi": None,
                "url": None,
                "has_full_text": False,
            },
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}

        tools._tool_analyze_across_papers(ctx, analysis_question="What are the themes?")

        assert tools._memory["cross_paper_analysis"]["last_question"] == "What are the themes?"
        assert tools._memory["cross_paper_analysis"]["paper_count"] == 1

    def test_instruction_includes_paper_count(self):
        """The instruction field should mention the number of focused papers."""
        focused = [
            {"title": "P1", "authors": "A", "year": 2023, "abstract": "Ab", "doi": None, "url": None, "has_full_text": False},
            {"title": "P2", "authors": "B", "year": 2022, "abstract": "Ab", "doi": None, "url": None, "has_full_text": False},
            {"title": "P3", "authors": "C", "year": 2021, "abstract": "Ab", "doi": None, "url": None, "has_full_text": False},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}
        result = tools._tool_analyze_across_papers(ctx, analysis_question="Themes?")

        assert "3 papers" in result["instruction"]

    def test_depth_warning_all_abstracts(self):
        """depth_info should warn when all papers are abstract-only."""
        focused = [
            {"title": "P1", "authors": "A", "year": 2023, "abstract": "Ab", "doi": None, "url": None, "has_full_text": False},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}
        result = tools._tool_analyze_across_papers(ctx, analysis_question="Q?")

        assert "Limited Analysis" in result["depth_info"]

    def test_mixed_depth_warning(self):
        """depth_info should indicate mixed depth when some papers have full text."""
        focused = [
            {"title": "Full", "authors": "A", "year": 2023, "abstract": "Ab",
             "doi": None, "url": None, "has_full_text": True, "summary": "S", "key_findings": ["F"]},
            {"title": "Abstract", "authors": "B", "year": 2022, "abstract": "Ab",
             "doi": None, "url": None, "has_full_text": False},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}
        result = tools._tool_analyze_across_papers(ctx, analysis_question="Q?")

        assert "Mixed Depth" in result["depth_info"]

    def test_no_depth_warning_when_all_full_text(self):
        """depth_info should be None when all papers have full text."""
        focused = [
            {"title": "Full", "authors": "A", "year": 2023, "abstract": "Ab",
             "doi": None, "url": None, "has_full_text": True, "summary": "S", "methodology": "M"},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}
        result = tools._tool_analyze_across_papers(ctx, analysis_question="Q?")

        assert result["depth_info"] is None

    def test_no_ai_service_skips_rag(self):
        """When ai_service is None, should skip RAG and use abstracts."""
        ref = _make_reference(doi="10.1234/x", document_id=uuid.uuid4())
        focused = [
            {"title": "P", "authors": "A", "year": 2023, "abstract": "Ab",
             "doi": "10.1234/x", "url": None, "has_full_text": False},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        tools.ai_service = None
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}
        result = tools._tool_analyze_across_papers(ctx, analysis_question="Compare")

        assert result["status"] == "success"
        # Should fall through to abstract-only since ai_service is None
        assert result["retrieval_method"] == "abstracts_only"

    def test_key_findings_as_list_rendered(self):
        """key_findings as a list should render each item."""
        focused = [
            {"title": "P", "authors": "A", "year": 2023, "abstract": "Ab",
             "doi": None, "url": None, "has_full_text": True,
             "summary": "S", "key_findings": ["Finding A", "Finding B"], "methodology": None},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}
        result = tools._tool_analyze_across_papers(ctx, analysis_question="Q?")

        assert "Finding A" in result["papers_context"]
        assert "Finding B" in result["papers_context"]

    def test_limitations_as_list_rendered(self):
        """limitations as a list should render each item."""
        focused = [
            {"title": "P", "authors": "A", "year": 2023, "abstract": "Ab",
             "doi": None, "url": None, "has_full_text": True,
             "summary": "S", "limitations": ["Lim 1", "Lim 2"]},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
        tools.db = db

        ctx = {"channel": _make_channel(), "project": _make_project()}
        result = tools._tool_analyze_across_papers(ctx, analysis_question="Q?")

        assert "Lim 1" in result["papers_context"]
        assert "Lim 2" in result["papers_context"]


# ===================================================================
# 4. _tool_generate_section_from_discussion
# ===================================================================

class TestGenerateSectionFromDiscussion:
    """Tests for _tool_generate_section_from_discussion."""

    def test_no_channel_returns_error(self):
        """Should return error when channel is missing."""
        tools = ConcreteAnalysisTools()
        ctx = {}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="methodology")

        assert result["status"] == "error"
        assert "Channel context" in result["message"]

    def test_basic_section_without_target_paper(self):
        """Should return generation prompt for standalone artifact."""
        tools = ConcreteAnalysisTools(initial_memory={
            "focused_papers": [
                {"title": "Paper A", "year": 2023, "key_findings": ["Finding 1"]},
            ],
            "summary": "We discussed ML methods",
            "facts": {"research_topic": "Machine Learning"},
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="methodology")

        assert result["status"] == "success"
        assert result["section_type"] == "methodology"
        assert "target_paper_id" not in result
        assert "focused_paper_count" in result
        assert result["focused_paper_count"] == 1
        # Instruction should mention creating artifact/paper
        assert "create_artifact" in result["instruction"] or "create_paper" in result["instruction"]
        # Context should include focused papers
        assert "Paper A" in result["context"]

    def test_section_with_target_paper(self):
        """Should include target_paper_id and update_paper instruction."""
        tools = ConcreteAnalysisTools(initial_memory={})
        paper_id = str(uuid.uuid4())
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(
            ctx, section_type="introduction", target_paper_id=paper_id
        )

        assert result["status"] == "success"
        assert result["target_paper_id"] == paper_id
        assert "update_paper" in result["instruction"]

    def test_known_section_types(self):
        """Each known section type should produce specific instructions."""
        known_types = [
            "methodology", "related_work", "introduction",
            "results", "discussion", "conclusion", "abstract",
        ]

        for section_type in known_types:
            tools = ConcreteAnalysisTools(initial_memory={})
            ctx = {"channel": _make_channel()}

            result = tools._tool_generate_section_from_discussion(ctx, section_type=section_type)

            assert result["status"] == "success"
            assert result["section_type"] == section_type
            # Each known type should have non-generic instructions
            prompt = result["generation_prompt"]
            assert "Generate" in prompt

    def test_unknown_section_type_uses_generic_prompt(self):
        """Unknown section types should get a generic generation prompt."""
        tools = ConcreteAnalysisTools(initial_memory={})
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="custom_section")

        assert result["status"] == "success"
        assert "custom_section" in result["generation_prompt"]

    def test_custom_instructions_appended(self):
        """custom_instructions should be appended to the generation prompt."""
        tools = ConcreteAnalysisTools(initial_memory={})
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(
            ctx,
            section_type="methodology",
            custom_instructions="Focus on survey methodology",
        )

        assert "Focus on survey methodology" in result["generation_prompt"]

    def test_context_includes_session_summary(self):
        """Session summary should appear in the context."""
        tools = ConcreteAnalysisTools(initial_memory={
            "summary": "Discussion about transformer models and attention",
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="introduction")

        assert "transformer models and attention" in result["context"]

    def test_context_includes_research_topic(self):
        """Research topic from facts should appear in the context."""
        tools = ConcreteAnalysisTools(initial_memory={
            "facts": {"research_topic": "Neural Architecture Search"},
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="introduction")

        assert "Neural Architecture Search" in result["context"]

    def test_context_includes_decisions(self):
        """Decisions made should appear in the context."""
        tools = ConcreteAnalysisTools(initial_memory={
            "facts": {
                "decisions_made": ["Use PyTorch", "Focus on NLP tasks"],
            },
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="methodology")

        assert "Use PyTorch" in result["context"]
        assert "Focus on NLP tasks" in result["context"]

    def test_context_includes_search_question(self):
        """Last search question should appear in the context."""
        tools = ConcreteAnalysisTools(initial_memory={
            "search_ui_trigger": {"last_question": "transformer efficiency"},
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="related_work")

        assert "transformer efficiency" in result["context"]

    def test_context_includes_cross_analysis_question(self):
        """Last cross-paper analysis question should appear in context."""
        tools = ConcreteAnalysisTools(initial_memory={
            "cross_paper_analysis": {"last_question": "How do approaches differ?"},
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="discussion")

        assert "How do approaches differ?" in result["context"]

    def test_empty_memory_produces_fallback_context(self):
        """With no memory data, context should be the fallback message."""
        tools = ConcreteAnalysisTools(initial_memory={})
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="abstract")

        assert result["context"] == "No prior context available."

    def test_backward_compat_deep_search_key(self):
        """Should support old 'deep_search' memory key for backward compat."""
        tools = ConcreteAnalysisTools(initial_memory={
            "deep_search": {"last_question": "legacy search question"},
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="introduction")

        assert "legacy search question" in result["context"]

    def test_instruction_contains_latex_section_heading(self):
        """Instruction should contain the LaTeX section command."""
        tools = ConcreteAnalysisTools(initial_memory={})
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="related_work")

        assert "\\section{" in result["instruction"]
        assert "Related Work" in result["instruction"]

    def test_focused_papers_with_key_findings_in_context(self):
        """Focused papers' key findings should appear in the context."""
        tools = ConcreteAnalysisTools(initial_memory={
            "focused_papers": [
                {
                    "title": "Important Paper",
                    "year": 2024,
                    "key_findings": ["Transformers outperform RNNs"],
                },
            ],
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="results")

        assert "Important Paper" in result["context"]
        assert "Transformers outperform RNNs" in result["context"]

    def test_decisions_limited_to_last_five(self):
        """Only the last 5 decisions should appear in context."""
        tools = ConcreteAnalysisTools(initial_memory={
            "facts": {
                "decisions_made": [f"Decision {i}" for i in range(10)],
            },
        })
        ctx = {"channel": _make_channel()}

        result = tools._tool_generate_section_from_discussion(ctx, section_type="methodology")

        # Last 5 decisions: 5, 6, 7, 8, 9
        assert "Decision 5" in result["context"]
        assert "Decision 9" in result["context"]
        # First decision should NOT appear
        assert "Decision 0" not in result["context"]


# ===================================================================
# 5. _tool_compare_papers
# ===================================================================

class TestComparePapers:
    """Tests for _tool_compare_papers."""

    def test_no_indices_no_ids_returns_error(self):
        """Should return error when neither paper_indices nor reference_ids given."""
        tools = ConcreteAnalysisTools()
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_compare_papers(ctx, dimensions=["methodology"])

        assert result["status"] == "error"
        assert "paper_indices" in result["message"]

    def test_no_dimensions_returns_error(self):
        """Should return error when dimensions list is empty."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result(), _search_result(title="Paper 2")],
        }

        result = tools._tool_compare_papers(ctx, paper_indices=[0, 1], dimensions=[])

        assert result["status"] == "error"
        assert "dimension" in result["message"].lower()

    def test_fewer_than_two_papers_returns_error(self):
        """Need at least 2 papers to compare."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": [_search_result()],
        }

        result = tools._tool_compare_papers(ctx, paper_indices=[0], dimensions=["methodology"])

        assert result["status"] == "error"
        assert "2 papers" in result["message"]

    def test_successful_comparison(self):
        """Should return comparison context and instruction for valid inputs."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        search_results = [
            _search_result(title="Paper Alpha", year=2023),
            _search_result(title="Paper Beta", year=2024),
        ]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_compare_papers(
            ctx, paper_indices=[0, 1], dimensions=["methodology", "results"]
        )

        assert result["status"] == "success"
        assert "comparison_context" in result
        assert "Paper Alpha" in result["comparison_context"]
        assert "Paper Beta" in result["comparison_context"]
        assert "methodology, results" in result["instruction"]
        assert len(result["papers"]) == 2

    def test_dimensions_in_instruction(self):
        """Instruction should list all requested dimensions."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        search_results = [_search_result(title="A"), _search_result(title="B")]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_compare_papers(
            ctx, paper_indices=[0, 1], dimensions=["dataset", "limitations"]
        )

        assert "dataset" in result["instruction"]
        assert "limitations" in result["instruction"]

    def test_papers_focused_in_memory(self):
        """Compare should also focus papers in memory (via _tool_focus_on_papers)."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        search_results = [_search_result(title="X"), _search_result(title="Y")]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        tools._tool_compare_papers(ctx, paper_indices=[0, 1], dimensions=["methods"])

        assert "focused_papers" in tools._memory
        assert len(tools._memory["focused_papers"]) == 2

    def test_comparison_includes_full_text_data(self):
        """Papers with summary/findings should include them in comparison context."""
        ref = _make_reference(
            doi="10.1234/ft",
            status="ingested",
            title="Full Text Paper",
            summary="Great summary",
            key_findings=["Finding 1"],
            methodology="RCT",
        )
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        search_results = [
            _search_result(title="Full Text Paper", doi="10.1234/ft"),
            _search_result(title="Abstract Only"),
        ]
        ctx = {
            "project": _make_project(),
            "channel": _make_channel(),
            "recent_search_results": search_results,
        }

        result = tools._tool_compare_papers(
            ctx, paper_indices=[0, 1], dimensions=["methodology"]
        )

        assert result["status"] == "success"
        assert "Great summary" in result["comparison_context"]
        assert "RCT" in result["comparison_context"]


# ===================================================================
# 6. _tool_suggest_research_gaps
# ===================================================================

class TestSuggestResearchGaps:
    """Tests for _tool_suggest_research_gaps."""

    def test_focused_scope_no_channel_returns_error(self):
        """Should error when scope=focused but no channel in ctx."""
        tools = ConcreteAnalysisTools()
        ctx = {"project": _make_project()}

        result = tools._tool_suggest_research_gaps(ctx, scope="focused")

        assert result["status"] == "error"
        assert "Channel" in result["message"]

    def test_focused_scope_no_papers_returns_error(self):
        """Should error when no papers are in focus."""
        tools = ConcreteAnalysisTools(initial_memory={})
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(ctx, scope="focused")

        assert result["status"] == "error"
        assert "focus_on_papers" in result["message"]

    def test_focused_scope_success(self):
        """Should analyze focused papers and return context + instruction."""
        focused = [
            {
                "title": "Paper A",
                "authors": "Alice",
                "year": 2023,
                "abstract": "Abstract A",
                "has_full_text": False,
            },
            {
                "title": "Paper B",
                "authors": "Bob",
                "year": 2022,
                "abstract": "Abstract B",
                "has_full_text": True,
                "summary": "Summary of B",
                "key_findings": ["Finding B1"],
                "methodology": "Survey",
                "limitations": ["Limitation B1"],
            },
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(ctx, scope="focused")

        assert result["status"] == "success"
        assert result["papers_analyzed"] == 2
        assert "Paper A" in result["context"]
        assert "Paper B" in result["context"]
        assert "Finding B1" in result["context"]
        assert "Understudied" in result["instruction"]

    def test_research_question_in_instruction(self):
        """Research question should be included in the instruction."""
        focused = [
            {"title": "P", "authors": "A", "year": 2023, "abstract": "Ab"},
        ]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(
            ctx, scope="focused", research_question="How does X affect Y?"
        )

        assert result["status"] == "success"
        assert "How does X affect Y?" in result["instruction"]

    def test_library_scope_success(self):
        """Should query DB for library refs when scope=library."""
        ref = _make_reference(title="Lib Paper", abstract="Lib abstract", status="pending")
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(ctx, scope="library")

        assert result["status"] == "success"
        assert result["papers_analyzed"] == 1
        assert "Lib Paper" in result["context"]

    def test_library_scope_empty_returns_error(self):
        """Should error when library has no refs."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteAnalysisTools(db=db)
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(ctx, scope="library")

        assert result["status"] == "error"
        assert "No references" in result["message"]

    def test_channel_scope_success(self):
        """Should query channel-scoped refs."""
        ref = _make_reference(title="Chan Paper", abstract="Chan abstract", status="ingested", summary="Chan summary")
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = [ref]

        tools = ConcreteAnalysisTools(db=db)
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(ctx, scope="channel")

        assert result["status"] == "success"
        assert "Chan Paper" in result["context"]

    def test_channel_scope_no_channel_returns_error(self):
        """Should error when scope=channel but no channel in ctx."""
        tools = ConcreteAnalysisTools()
        ctx = {"project": _make_project()}

        result = tools._tool_suggest_research_gaps(ctx, scope="channel")

        assert result["status"] == "error"
        assert "Channel" in result["message"]

    def test_invalid_scope_returns_error(self):
        """Should error on invalid scope."""
        tools = ConcreteAnalysisTools()
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(ctx, scope="invalid")

        assert result["status"] == "error"
        assert "Invalid scope" in result["message"]

    def test_instruction_has_five_sections(self):
        """Instruction should list 5 analysis dimensions."""
        focused = [{"title": "P", "authors": "A", "year": 2023, "abstract": "Ab"}]
        tools = ConcreteAnalysisTools(initial_memory={"focused_papers": focused})
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_suggest_research_gaps(ctx, scope="focused")

        assert "Understudied" in result["instruction"]
        assert "Contradictions" in result["instruction"]
        assert "future research" in result["instruction"].lower()
