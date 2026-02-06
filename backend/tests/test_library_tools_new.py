"""
Tests for new LibraryToolsMixin tools: export_citations, annotate_reference,
and generate_abstract.

Uses a concrete test class that inherits from LibraryToolsMixin and
provides mock implementations of the required interface methods.
All DB and external calls are mocked -- no real database sessions.
"""

import uuid
from unittest.mock import MagicMock

from app.services.discussion_ai.mixins.library_tools_mixin import LibraryToolsMixin


# ---------------------------------------------------------------------------
# Concrete test harness that satisfies the mixin contract
# ---------------------------------------------------------------------------

class ConcreteLibraryTools(LibraryToolsMixin):
    """Minimal concrete class that satisfies the mixin contract."""

    def __init__(self, ai_service=None, db=None, initial_memory=None):
        self.ai_service = ai_service or MagicMock()
        self.db = db or MagicMock()
        self._memory = initial_memory if initial_memory is not None else {}
        self._saved_memories = []

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
    authors=None,
    year=2024,
    abstract="Abstract text",
    journal=None,
):
    ref = MagicMock()
    ref.id = ref_id or uuid.uuid4()
    ref.title = title
    ref.doi = doi
    ref.url = url
    ref.status = status
    ref.authors = authors or ["Author A", "Author B"]
    ref.year = year
    ref.abstract = abstract
    ref.journal = journal
    return ref


def _make_paper(paper_id=None, title="My Paper", content=None, content_json=None):
    paper = MagicMock()
    paper.id = paper_id or uuid.uuid4()
    paper.title = title
    paper.content = content or r"\section{Introduction} This is a test paper with some content about methodology."
    paper.content_json = content_json
    return paper


# ===================================================================
# 1. _tool_export_citations
# ===================================================================

class TestExportCitations:
    """Tests for _tool_export_citations."""

    def test_selected_scope_with_ids_bibtex(self):
        """Should export selected references in BibTeX format."""
        ref_id = uuid.uuid4()
        ref = _make_reference(
            ref_id=ref_id,
            title="Deep Learning Survey",
            authors="Jane Doe, John Smith",
            year=2023,
            journal="Nature ML",
            doi="10.1234/test",
        )
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(
            ctx, reference_ids=[str(ref_id)], format="bibtex", scope="selected"
        )

        assert result["status"] == "success"
        assert result["format"] == "bibtex"
        assert result["count"] == 1
        assert "@article{" in result["citations"]
        assert "Deep Learning Survey" in result["citations"]
        assert "Jane Doe" in result["citations"]
        assert "2023" in result["citations"]

    def test_selected_scope_apa_format(self):
        """Should export in APA format."""
        ref = _make_reference(
            title="Attention Is All You Need",
            authors="Vaswani et al.",
            year=2017,
            journal="NeurIPS",
        )
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(
            ctx, reference_ids=[str(ref.id)], format="apa", scope="selected"
        )

        assert result["status"] == "success"
        assert result["format"] == "apa"
        assert "Vaswani" in result["citations"]
        assert "(2017)" in result["citations"]
        assert "Attention Is All You Need" in result["citations"]

    def test_selected_scope_mla_format(self):
        """Should export in MLA format."""
        ref = _make_reference(title="Test Paper", authors="Smith, J.", year=2020, journal="AI Journal")
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(
            ctx, reference_ids=[str(ref.id)], format="mla", scope="selected"
        )

        assert result["status"] == "success"
        assert result["format"] == "mla"
        assert '"Test Paper."' in result["citations"]

    def test_selected_scope_chicago_format(self):
        """Should export in Chicago format."""
        ref = _make_reference(title="Test Paper", authors="Smith, J.", year=2020, doi="10.1234/x")
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(
            ctx, reference_ids=[str(ref.id)], format="chicago", scope="selected"
        )

        assert result["status"] == "success"
        assert result["format"] == "chicago"
        assert "(2020)" in result["citations"]

    def test_all_scope(self):
        """Should export all library references."""
        refs = [
            _make_reference(title="Paper 1"),
            _make_reference(title="Paper 2"),
        ]
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = refs

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(ctx, format="bibtex", scope="all")

        assert result["status"] == "success"
        assert result["count"] == 2

    def test_all_scope_empty_library(self):
        """Should error when library is empty."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(ctx, format="bibtex", scope="all")

        assert result["status"] == "error"
        assert "No references" in result["message"]

    def test_focused_scope_no_focused_papers(self):
        """Should error when focused but no papers in memory."""
        tools = ConcreteLibraryTools(initial_memory={})
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_export_citations(ctx, format="bibtex", scope="focused")

        assert result["status"] == "error"
        assert "No focused papers" in result["message"]

    def test_focused_scope_with_papers(self):
        """Should export focused papers from memory."""
        ref_id = uuid.uuid4()
        ref = _make_reference(ref_id=ref_id, title="Focused Paper")
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(
            db=db,
            initial_memory={
                "focused_papers": [{"reference_id": str(ref_id), "title": "Focused Paper"}]
            },
        )
        ctx = {"project": _make_project(), "channel": _make_channel()}

        result = tools._tool_export_citations(ctx, format="bibtex", scope="focused")

        assert result["status"] == "success"
        assert result["count"] == 1
        assert "Focused Paper" in result["citations"]

    def test_invalid_ref_id_skipped(self):
        """Invalid UUIDs should be skipped without error."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = None

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(
            ctx, reference_ids=["not-a-uuid"], format="bibtex", scope="selected"
        )

        assert result["status"] == "error"
        assert "No references" in result["message"]

    def test_no_scope_no_ids_returns_error(self):
        """Should error when scope=selected but no reference_ids."""
        tools = ConcreteLibraryTools()
        ctx = {"project": _make_project()}

        result = tools._tool_export_citations(ctx, format="bibtex", scope="selected")

        assert result["status"] == "error"


# ===================================================================
# 2. _tool_annotate_reference
# ===================================================================

class TestAnnotateReference:
    """Tests for _tool_annotate_reference."""

    def test_invalid_uuid_returns_error(self):
        """Should return error for invalid reference ID."""
        tools = ConcreteLibraryTools()
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(ctx, reference_id="not-uuid", note="test")

        assert result["status"] == "error"
        assert "Invalid reference ID" in result["message"]

    def test_reference_not_found_returns_error(self):
        """Should return error when reference not in project."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = None

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4()), note="test"
        )

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_no_note_no_tags_returns_error(self):
        """Should error when neither note nor tags provided."""
        project_ref = MagicMock()
        project_ref.annotations = {}
        project_ref.project_id = uuid.uuid4()
        project_ref.reference_id = uuid.uuid4()

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = project_ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4())
        )

        assert result["status"] == "error"
        assert "note and/or tags" in result["message"].lower()

    def test_add_note_success(self):
        """Should add a note with timestamp to annotations."""
        project_ref = MagicMock()
        project_ref.annotations = {}

        ref = MagicMock()
        ref.title = "My Paper"

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = project_ref
        # Second query for reference title
        db.query.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4()), note="Great paper for methodology"
        )

        assert result["status"] == "success"
        assert "My Paper" in result["message"]
        assert result["annotations"]["notes_count"] == 1
        assert result["annotations"]["notes"][0]["text"] == "Great paper for methodology"

    def test_add_tags_success(self):
        """Should add tags to annotations."""
        project_ref = MagicMock()
        project_ref.annotations = {}

        ref = MagicMock()
        ref.title = "Tagged Paper"

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = project_ref
        db.query.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4()), tags=["methodology", "key-paper"]
        )

        assert result["status"] == "success"
        assert result["annotations"]["tags_count"] == 2
        assert "methodology" in result["annotations"]["tags"]
        assert "key-paper" in result["annotations"]["tags"]

    def test_add_note_and_tags(self):
        """Should add both note and tags."""
        project_ref = MagicMock()
        project_ref.annotations = {}

        ref = MagicMock()
        ref.title = "Paper"

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = project_ref
        db.query.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4()), note="My note", tags=["tag1"]
        )

        assert result["status"] == "success"
        assert result["annotations"]["notes_count"] == 1
        assert result["annotations"]["tags_count"] == 1

    def test_append_to_existing_annotations(self):
        """Should append to existing annotations, not replace them."""
        project_ref = MagicMock()
        project_ref.annotations = {
            "notes": [{"text": "Old note", "created_at": "2024-01-01"}],
            "tags": ["existing-tag"],
        }

        ref = MagicMock()
        ref.title = "Paper"

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = project_ref
        db.query.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4()), note="New note", tags=["new-tag"]
        )

        assert result["status"] == "success"
        assert result["annotations"]["notes_count"] == 2
        assert result["annotations"]["tags_count"] == 2

    def test_dedup_tags(self):
        """Should not add duplicate tags."""
        project_ref = MagicMock()
        project_ref.annotations = {"notes": [], "tags": ["existing"]}

        ref = MagicMock()
        ref.title = "Paper"

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = project_ref
        db.query.return_value.filter.return_value.first.return_value = ref

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4()), tags=["existing", "new"]
        )

        assert result["status"] == "success"
        assert result["annotations"]["tags_count"] == 2
        assert result["annotations"]["tags"].count("existing") == 1

    def test_db_error_rollback(self):
        """Should rollback on DB error and return error status."""
        project_ref = MagicMock()
        project_ref.annotations = {}

        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = project_ref
        db.commit.side_effect = Exception("DB error")

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_annotate_reference(
            ctx, reference_id=str(uuid.uuid4()), note="test"
        )

        assert result["status"] == "error"
        assert "Failed to annotate" in result["message"]
        db.rollback.assert_called_once()


# ===================================================================
# 3. _tool_generate_abstract
# ===================================================================

class TestGenerateAbstract:
    """Tests for _tool_generate_abstract."""

    def test_invalid_paper_id_returns_error(self):
        """Should return error for invalid paper ID."""
        tools = ConcreteLibraryTools()
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id="not-uuid")

        assert result["status"] == "error"
        assert "Invalid paper ID" in result["message"]

    def test_paper_not_found_returns_error(self):
        """Should return error when paper not in project."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id=str(uuid.uuid4()))

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_empty_content_returns_error(self):
        """Should return error when paper has insufficient content."""
        paper = _make_paper(content="short")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = paper

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id=str(paper.id))

        assert result["status"] == "error"
        assert "insufficient content" in result["message"].lower()

    def test_success_with_plain_content(self):
        """Should generate abstract instruction from plain content."""
        paper = _make_paper(
            title="Test Paper",
            content=r"\section{Introduction} " + "x" * 100,
            content_json=None,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = paper

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id=str(paper.id))

        assert result["status"] == "success"
        assert result["paper_title"] == "Test Paper"
        assert "250 words" in result["instruction"]
        assert result["content_preview"] is not None
        assert result["full_content"] is not None

    def test_success_with_latex_source_in_content_json(self):
        """Should prefer content_json.latex_source over plain content."""
        latex_content = r"\section{Methods} " + "y" * 200
        paper = _make_paper(
            title="JSON Paper",
            content="plain fallback",
            content_json={"latex_source": latex_content},
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = paper

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id=str(paper.id))

        assert result["status"] == "success"
        # The full_content should be derived from latex_source, not plain content
        assert "plain fallback" not in result["full_content"]

    def test_custom_max_words(self):
        """Should pass custom max_words to instruction."""
        paper = _make_paper(content=r"\section{Intro} " + "z" * 200)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = paper

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id=str(paper.id), max_words=150)

        assert result["status"] == "success"
        assert "150 words" in result["instruction"]

    def test_long_content_truncated(self):
        """Content longer than 8000 chars should be truncated."""
        paper = _make_paper(content=r"\section{Intro} " + "a" * 10000)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = paper

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id=str(paper.id))

        assert result["status"] == "success"
        assert "[Content truncated...]" in result["full_content"]

    def test_instruction_mentions_structured_abstract(self):
        """Instruction should mention structured abstract format."""
        paper = _make_paper(content=r"\section{Intro} " + "b" * 100)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = paper

        tools = ConcreteLibraryTools(db=db)
        ctx = {"project": _make_project()}

        result = tools._tool_generate_abstract(ctx, paper_id=str(paper.id))

        assert "structured abstract" in result["instruction"].lower()
        assert "background" in result["instruction"].lower()
        assert "methods" in result["instruction"].lower()
