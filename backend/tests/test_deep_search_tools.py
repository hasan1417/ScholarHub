"""
Tests for Deep Search & Paper Focus Tools

This test suite verifies the new Discussion AI tools:
1. deep_search_papers - Search and synthesize research answers
2. focus_on_papers - Load papers into focus for detailed discussion
3. analyze_across_papers - Cross-paper analysis
4. generate_section_from_discussion - Generate paper sections from insights

Run with: pytest tests/test_deep_search_tools.py -v
Or directly: python tests/test_deep_search_tools.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ============================================================
# Mock Classes
# ============================================================

class MockChannel:
    """Mock ProjectDiscussionChannel for testing."""
    def __init__(self):
        self.id = str(uuid4())
        self.name = "Test Channel"
        self.ai_memory = None


class MockProject:
    """Mock Project for testing."""
    def __init__(self):
        self.id = str(uuid4())
        self.created_by = str(uuid4())
        self.title = "Test Research Project"
        self.idea = "This is a test project about machine learning."
        self.scope = "Objective 1\nObjective 2"
        self.keywords = "ML, AI, testing"


class MockReference:
    """Mock Reference for testing."""
    def __init__(self, id=None, title="Test Paper", status="pending"):
        self.id = id or str(uuid4())
        self.title = title
        self.authors = ["Author One", "Author Two"]
        self.year = 2024
        self.abstract = "This is a test abstract about the research."
        self.doi = "10.1234/test.2024"
        self.url = "https://example.com/paper"
        self.source = "test_source"
        self.status = status
        self.summary = None
        self.key_findings = None
        self.methodology = None
        self.limitations = None

        # Set analysis fields if status is analyzed
        if status in ("ingested", "analyzed"):
            self.summary = "This paper presents a novel approach to testing."
            self.key_findings = ["Finding 1", "Finding 2", "Finding 3"]
            self.methodology = "The authors used a comprehensive testing methodology."
            self.limitations = ["Limitation 1", "Limitation 2"]


class MockDB:
    """Mock database session."""
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self._references = []

    def add_reference(self, ref: MockReference):
        """Add a reference to the mock database."""
        self._references.append(ref)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def query(self, *args, **kwargs):
        return MockQuery(self._references)


class MockQuery:
    """Mock query object."""
    def __init__(self, references=None):
        self._references = references or []
        self._filters = []

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def count(self):
        return len(self._references)

    def order_by(self, *args):
        return self

    def limit(self, n):
        return self

    def all(self):
        return self._references

    def first(self):
        return self._references[0] if self._references else None


class MockAIService:
    """Mock AI service for testing."""
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.openai_client = MockOpenAIClient()


class MockOpenAIClient:
    """Mock OpenAI client."""
    def __init__(self):
        self.chat = MockChat()


class MockChat:
    """Mock chat completions."""
    def __init__(self):
        self.completions = MockCompletions()


class MockCompletions:
    """Mock completions."""
    def create(self, **kwargs):
        return MockResponse()


class MockResponse:
    """Mock API response."""
    def __init__(self):
        self.choices = [MockChoice()]


class MockChoice:
    """Mock choice."""
    def __init__(self):
        self.message = MockMessage()


class MockMessage:
    """Mock message."""
    def __init__(self):
        self.content = json.dumps({
            "research_topic": "Machine Learning",
            "papers_discussed": [],
            "decisions_made": [],
            "pending_questions": [],
            "methodology_notes": []
        })


# ============================================================
# Test Fixtures
# ============================================================

def create_test_context(
    project: MockProject = None,
    channel: MockChannel = None,
    recent_search_results: List[Dict] = None
) -> Dict[str, Any]:
    """Create a test context dictionary."""
    return {
        "project": project or MockProject(),
        "channel": channel or MockChannel(),
        "recent_search_results": recent_search_results or [],
        "reasoning_mode": False,
        "max_papers": 100,
        "papers_requested": 0,
        "user_message": "Test message",
        "conversation_history": [],
    }


def create_sample_search_results(count: int = 5) -> List[Dict]:
    """Create sample search results for testing."""
    return [
        {
            "title": f"Test Paper {i}: Research on Topic {i}",
            "authors": f"Author {i}, Co-Author {i}",
            "year": 2024 - (i % 3),
            "abstract": f"This paper explores topic {i} in depth with novel contributions.",
            "doi": f"10.1234/paper{i}",
            "url": f"https://example.com/paper{i}",
            "source": "semantic_scholar",
            "pdf_url": f"https://example.com/paper{i}.pdf" if i % 2 == 0 else None,
            "is_open_access": i % 2 == 0,
        }
        for i in range(count)
    ]


# ============================================================
# Test Cases: Tool Definitions
# ============================================================

class TestToolDefinitions:
    """Test that new tools are properly defined in DISCUSSION_TOOLS."""

    def test_deep_search_papers_defined(self):
        """Test that deep_search_papers tool is defined."""
        from app.services.discussion_ai.tool_orchestrator import DISCUSSION_TOOLS

        tool_names = [t["function"]["name"] for t in DISCUSSION_TOOLS]
        assert "deep_search_papers" in tool_names

        # Find the tool and check its parameters
        tool = next(t for t in DISCUSSION_TOOLS if t["function"]["name"] == "deep_search_papers")
        params = tool["function"]["parameters"]["properties"]

        assert "research_question" in params
        assert "max_papers" in params
        assert "research_question" in tool["function"]["parameters"]["required"]

        print("✓ test_deep_search_papers_defined passed")

    def test_focus_on_papers_defined(self):
        """Test that focus_on_papers tool is defined."""
        from app.services.discussion_ai.tool_orchestrator import DISCUSSION_TOOLS

        tool_names = [t["function"]["name"] for t in DISCUSSION_TOOLS]
        assert "focus_on_papers" in tool_names

        tool = next(t for t in DISCUSSION_TOOLS if t["function"]["name"] == "focus_on_papers")
        params = tool["function"]["parameters"]["properties"]

        assert "paper_indices" in params
        assert "reference_ids" in params

        print("✓ test_focus_on_papers_defined passed")

    def test_analyze_across_papers_defined(self):
        """Test that analyze_across_papers tool is defined."""
        from app.services.discussion_ai.tool_orchestrator import DISCUSSION_TOOLS

        tool_names = [t["function"]["name"] for t in DISCUSSION_TOOLS]
        assert "analyze_across_papers" in tool_names

        tool = next(t for t in DISCUSSION_TOOLS if t["function"]["name"] == "analyze_across_papers")
        params = tool["function"]["parameters"]["properties"]

        assert "analysis_question" in params
        assert "analysis_question" in tool["function"]["parameters"]["required"]

        print("✓ test_analyze_across_papers_defined passed")

    def test_generate_section_from_discussion_defined(self):
        """Test that generate_section_from_discussion tool is defined."""
        from app.services.discussion_ai.tool_orchestrator import DISCUSSION_TOOLS

        tool_names = [t["function"]["name"] for t in DISCUSSION_TOOLS]
        assert "generate_section_from_discussion" in tool_names

        tool = next(t for t in DISCUSSION_TOOLS if t["function"]["name"] == "generate_section_from_discussion")
        params = tool["function"]["parameters"]["properties"]

        assert "section_type" in params
        assert "target_paper_id" in params
        assert "custom_instructions" in params
        assert "section_type" in tool["function"]["parameters"]["required"]

        # Check section type enum values
        section_types = params["section_type"]["enum"]
        expected_types = ["methodology", "related_work", "introduction", "results", "discussion", "conclusion", "abstract"]
        for expected in expected_types:
            assert expected in section_types, f"Missing section type: {expected}"

        print("✓ test_generate_section_from_discussion_defined passed")

    def test_total_tool_count(self):
        """Test that all 20 tools are defined."""
        from app.services.discussion_ai.tool_orchestrator import DISCUSSION_TOOLS

        assert len(DISCUSSION_TOOLS) == 20, f"Expected 20 tools, got {len(DISCUSSION_TOOLS)}"

        print("✓ test_total_tool_count passed")


# ============================================================
# Test Cases: deep_search_papers
# ============================================================

class TestDeepSearchPapers:
    """Test the deep_search_papers tool handler."""

    def test_deep_search_basic(self):
        """Test basic deep search functionality."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        ctx = create_test_context(channel=channel)

        result = orchestrator._tool_deep_search_papers(
            ctx,
            research_question="What are the main approaches to attention in transformers?",
            max_papers=10
        )

        assert result["status"] == "success"
        assert "research_question" in result
        assert result["research_question"] == "What are the main approaches to attention in transformers?"
        assert "action" in result
        assert result["action"]["type"] == "deep_search_references"
        assert result["action"]["payload"]["synthesis_mode"] == True

        print("✓ test_deep_search_basic passed")

    def test_deep_search_stores_in_memory(self):
        """Test that deep search stores question in memory."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel)

        question = "What methods exist for neural machine translation?"
        orchestrator._tool_deep_search_papers(ctx, research_question=question)

        # Check memory was updated
        assert channel.ai_memory.get("deep_search", {}).get("last_question") == question

        print("✓ test_deep_search_stores_in_memory passed")

    def test_deep_search_max_papers(self):
        """Test that max_papers parameter is passed correctly."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        ctx = create_test_context()

        result = orchestrator._tool_deep_search_papers(
            ctx,
            research_question="Test question",
            max_papers=25
        )

        assert result["action"]["payload"]["max_results"] == 25

        print("✓ test_deep_search_max_papers passed")


# ============================================================
# Test Cases: focus_on_papers
# ============================================================

class TestFocusOnPapers:
    """Test the focus_on_papers tool handler."""

    def test_focus_from_search_results(self):
        """Test focusing on papers from search results."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        search_results = create_sample_search_results(5)
        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(
            channel=channel,
            recent_search_results=search_results
        )

        result = orchestrator._tool_focus_on_papers(
            ctx,
            paper_indices=[0, 1, 2]
        )

        assert result["status"] == "success"
        assert result["focused_count"] == 3
        assert "papers" in result

        # Check memory was updated
        focused = channel.ai_memory.get("focused_papers", [])
        assert len(focused) == 3
        assert focused[0]["title"] == search_results[0]["title"]

        print("✓ test_focus_from_search_results passed")

    def test_focus_invalid_index(self):
        """Test focusing with invalid index."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        search_results = create_sample_search_results(3)
        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(
            channel=channel,
            recent_search_results=search_results
        )

        result = orchestrator._tool_focus_on_papers(
            ctx,
            paper_indices=[0, 10, 20]  # 10 and 20 are out of range
        )

        # Should still succeed with the valid index
        assert result["status"] == "success"
        assert result["focused_count"] == 1
        assert result.get("errors") is not None
        assert len(result["errors"]) == 2

        print("✓ test_focus_invalid_index passed")

    def test_focus_no_papers(self):
        """Test focusing with no valid papers."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        ctx = create_test_context(
            channel=channel,
            recent_search_results=[]  # No search results
        )

        result = orchestrator._tool_focus_on_papers(
            ctx,
            paper_indices=[0, 1]
        )

        assert result["status"] == "error"
        assert "No papers could be focused" in result["message"]

        print("✓ test_focus_no_papers passed")

    def test_focus_no_channel(self):
        """Test focusing without channel context."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        search_results = create_sample_search_results(3)
        ctx = create_test_context(recent_search_results=search_results)
        ctx["channel"] = None  # Remove channel

        # Should still work but not save to memory
        result = orchestrator._tool_focus_on_papers(
            ctx,
            paper_indices=[0]
        )

        assert result["status"] == "success"
        assert result["focused_count"] == 1

        print("✓ test_focus_no_channel passed")

    def test_focus_capabilities_returned(self):
        """Test that capabilities are returned in the response."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        search_results = create_sample_search_results(2)
        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(
            channel=channel,
            recent_search_results=search_results
        )

        result = orchestrator._tool_focus_on_papers(
            ctx,
            paper_indices=[0]
        )

        assert "capabilities" in result
        assert len(result["capabilities"]) >= 3
        assert any("analyze_across_papers" in cap for cap in result["capabilities"])

        print("✓ test_focus_capabilities_returned passed")


# ============================================================
# Test Cases: analyze_across_papers
# ============================================================

class TestAnalyzeAcrossPapers:
    """Test the analyze_across_papers tool handler."""

    def test_analyze_basic(self):
        """Test basic cross-paper analysis."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "focused_papers": [
                {
                    "title": "Paper 1",
                    "authors": "Author A",
                    "year": 2024,
                    "abstract": "Abstract for paper 1",
                    "has_full_text": True,
                    "summary": "Summary of paper 1",
                    "key_findings": ["Finding 1A", "Finding 1B"],
                    "methodology": "Methodology 1",
                },
                {
                    "title": "Paper 2",
                    "authors": "Author B",
                    "year": 2023,
                    "abstract": "Abstract for paper 2",
                    "has_full_text": False,
                }
            ]
        }
        ctx = create_test_context(channel=channel)

        result = orchestrator._tool_analyze_across_papers(
            ctx,
            analysis_question="How do their methodologies compare?"
        )

        assert result["status"] == "success"
        assert result["paper_count"] == 2
        assert "papers_context" in result
        assert "Paper 1" in result["papers_context"]
        assert "Paper 2" in result["papers_context"]
        assert "instruction" in result

        print("✓ test_analyze_basic passed")

    def test_analyze_no_focused_papers(self):
        """Test analysis when no papers are focused."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}  # No focused papers
        ctx = create_test_context(channel=channel)

        result = orchestrator._tool_analyze_across_papers(
            ctx,
            analysis_question="Compare the papers"
        )

        assert result["status"] == "error"
        assert "No papers in focus" in result["message"]
        assert "suggestion" in result

        print("✓ test_analyze_no_focused_papers passed")

    def test_analyze_stores_in_memory(self):
        """Test that analysis question is stored in memory."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "focused_papers": [
                {"title": "Paper 1", "authors": "Author A", "year": 2024, "abstract": "Test"}
            ]
        }
        ctx = create_test_context(channel=channel)

        question = "What are the common findings?"
        orchestrator._tool_analyze_across_papers(ctx, analysis_question=question)

        assert channel.ai_memory.get("cross_paper_analysis", {}).get("last_question") == question

        print("✓ test_analyze_stores_in_memory passed")

    def test_analyze_includes_full_text_content(self):
        """Test that analysis includes full text content when available."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "focused_papers": [
                {
                    "title": "Paper 1",
                    "authors": "Author A",
                    "year": 2024,
                    "abstract": "Abstract",
                    "has_full_text": True,
                    "summary": "This is the summary",
                    "key_findings": ["Key finding 1", "Key finding 2"],
                    "methodology": "The methodology used",
                }
            ]
        }
        ctx = create_test_context(channel=channel)

        result = orchestrator._tool_analyze_across_papers(
            ctx,
            analysis_question="Analyze the methodology"
        )

        assert "This is the summary" in result["papers_context"]
        assert "Key finding 1" in result["papers_context"]
        assert "The methodology used" in result["papers_context"]

        print("✓ test_analyze_includes_full_text_content passed")


# ============================================================
# Test Cases: generate_section_from_discussion
# ============================================================

class TestGenerateSectionFromDiscussion:
    """Test the generate_section_from_discussion tool handler."""

    def test_generate_section_basic(self):
        """Test basic section generation."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "focused_papers": [
                {"title": "Paper 1", "year": 2024, "key_findings": ["Finding 1"]}
            ],
            "summary": "User discussed machine learning approaches.",
            "facts": {
                "research_topic": "Neural Networks",
                "decisions_made": ["Use CNN architecture"]
            }
        }
        ctx = create_test_context(channel=channel)

        result = orchestrator._tool_generate_section_from_discussion(
            ctx,
            section_type="methodology"
        )

        assert result["status"] == "success"
        assert result["section_type"] == "methodology"
        assert "context" in result
        assert "generation_prompt" in result
        assert "instruction" in result

        print("✓ test_generate_section_basic passed")

    def test_generate_section_with_target_paper(self):
        """Test section generation with target paper."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel)

        paper_id = str(uuid4())
        result = orchestrator._tool_generate_section_from_discussion(
            ctx,
            section_type="related_work",
            target_paper_id=paper_id
        )

        assert result["status"] == "success"
        assert result["target_paper_id"] == paper_id
        assert "update_paper" in result["instruction"]

        print("✓ test_generate_section_with_target_paper passed")

    def test_generate_section_with_custom_instructions(self):
        """Test section generation with custom instructions."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel)

        custom = "Focus on transformer architectures"
        result = orchestrator._tool_generate_section_from_discussion(
            ctx,
            section_type="introduction",
            custom_instructions=custom
        )

        assert custom in result["generation_prompt"]

        print("✓ test_generate_section_with_custom_instructions passed")

    def test_generate_section_all_types(self):
        """Test that all section types work."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        section_types = ["methodology", "related_work", "introduction", "results", "discussion", "conclusion", "abstract"]

        for section_type in section_types:
            channel = MockChannel()
            channel.ai_memory = {}
            ctx = create_test_context(channel=channel)

            result = orchestrator._tool_generate_section_from_discussion(
                ctx,
                section_type=section_type
            )

            assert result["status"] == "success", f"Failed for section type: {section_type}"
            assert result["section_type"] == section_type

        print("✓ test_generate_section_all_types passed")

    def test_generate_section_includes_context(self):
        """Test that section generation includes all available context."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "focused_papers": [
                {"title": "Paper 1", "year": 2024, "key_findings": ["Finding A"]}
            ],
            "summary": "Discussion about ML",
            "facts": {
                "research_topic": "Deep Learning",
                "decisions_made": ["Use RNN"]
            },
            "deep_search": {
                "last_question": "What are attention mechanisms?"
            },
            "cross_paper_analysis": {
                "last_question": "Compare methods"
            }
        }
        ctx = create_test_context(channel=channel)

        result = orchestrator._tool_generate_section_from_discussion(
            ctx,
            section_type="methodology"
        )

        context = result["context"]
        assert "Paper 1" in context
        assert "Discussion about ML" in context
        assert "Deep Learning" in context
        assert "Use RNN" in context
        assert "What are attention mechanisms?" in context
        assert "Compare methods" in context

        print("✓ test_generate_section_includes_context passed")


# ============================================================
# Test Cases: Tool Status Messages
# ============================================================

class TestToolStatusMessages:
    """Test that status messages are defined for new tools."""

    def test_status_messages_defined(self):
        """Test that status messages exist for all new tools."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        new_tools = [
            "deep_search_papers",
            "focus_on_papers",
            "analyze_across_papers",
            "generate_section_from_discussion"
        ]

        for tool_name in new_tools:
            status = orchestrator._get_tool_status_message(tool_name)
            assert status != "Processing", f"Missing status message for {tool_name}"
            assert len(status) > 5, f"Status message too short for {tool_name}"

        print("✓ test_status_messages_defined passed")


# ============================================================
# Test Cases: Tool Routing
# ============================================================

class TestToolRouting:
    """Test that tools are properly routed in _execute_tool_calls."""

    def test_deep_search_routing(self):
        """Test that deep_search_papers is properly routed."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        ctx = create_test_context()
        tool_calls = [{
            "id": "call_1",
            "name": "deep_search_papers",
            "arguments": {"research_question": "Test question"}
        }]

        results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert len(results) == 1
        assert results[0]["name"] == "deep_search_papers"
        assert "error" not in results[0].get("result", {})

        print("✓ test_deep_search_routing passed")

    def test_focus_routing(self):
        """Test that focus_on_papers is properly routed."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        search_results = create_sample_search_results(3)
        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel, recent_search_results=search_results)

        tool_calls = [{
            "id": "call_1",
            "name": "focus_on_papers",
            "arguments": {"paper_indices": [0, 1]}
        }]

        results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert len(results) == 1
        assert results[0]["name"] == "focus_on_papers"
        assert results[0]["result"]["status"] == "success"

        print("✓ test_focus_routing passed")

    def test_analyze_routing(self):
        """Test that analyze_across_papers is properly routed."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "focused_papers": [{"title": "Test", "authors": "A", "year": 2024, "abstract": "Test"}]
        }
        ctx = create_test_context(channel=channel)

        tool_calls = [{
            "id": "call_1",
            "name": "analyze_across_papers",
            "arguments": {"analysis_question": "Compare them"}
        }]

        results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert len(results) == 1
        assert results[0]["name"] == "analyze_across_papers"
        assert results[0]["result"]["status"] == "success"

        print("✓ test_analyze_routing passed")

    def test_generate_section_routing(self):
        """Test that generate_section_from_discussion is properly routed."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel)

        tool_calls = [{
            "id": "call_1",
            "name": "generate_section_from_discussion",
            "arguments": {"section_type": "methodology"}
        }]

        results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert len(results) == 1
        assert results[0]["name"] == "generate_section_from_discussion"
        assert results[0]["result"]["status"] == "success"

        print("✓ test_generate_section_routing passed")


# ============================================================
# Test Cases: System Prompt
# ============================================================

class TestSystemPrompt:
    """Test that system prompt includes new tool documentation."""

    def test_system_prompt_includes_new_tools(self):
        """Test that BASE_SYSTEM_PROMPT mentions new tools."""
        from app.services.discussion_ai.tool_orchestrator import BASE_SYSTEM_PROMPT

        # Check tool names are mentioned
        assert "deep_search_papers" in BASE_SYSTEM_PROMPT
        assert "focus_on_papers" in BASE_SYSTEM_PROMPT
        assert "analyze_across_papers" in BASE_SYSTEM_PROMPT
        assert "generate_section_from_discussion" in BASE_SYSTEM_PROMPT

        print("✓ test_system_prompt_includes_new_tools passed")

    def test_system_prompt_includes_workflows(self):
        """Test that system prompt includes workflow documentation."""
        from app.services.discussion_ai.tool_orchestrator import BASE_SYSTEM_PROMPT

        # Check workflow sections
        assert "DEEP SEARCH" in BASE_SYSTEM_PROMPT
        assert "PAPER FOCUS" in BASE_SYSTEM_PROMPT or "Paper Focus" in BASE_SYSTEM_PROMPT

        print("✓ test_system_prompt_includes_workflows passed")


# ============================================================
# Test Cases: Integration
# ============================================================

class TestIntegration:
    """Integration tests for the tool workflow."""

    def test_focus_then_analyze_workflow(self):
        """Test the focus -> analyze workflow."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        # Step 1: Focus on papers
        search_results = create_sample_search_results(3)
        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel, recent_search_results=search_results)

        focus_result = orchestrator._tool_focus_on_papers(ctx, paper_indices=[0, 1])
        assert focus_result["status"] == "success"
        assert focus_result["focused_count"] == 2

        # Step 2: Analyze across papers (using same channel with updated memory)
        analyze_result = orchestrator._tool_analyze_across_papers(
            ctx,
            analysis_question="How do they compare?"
        )
        assert analyze_result["status"] == "success"
        assert analyze_result["paper_count"] == 2

        print("✓ test_focus_then_analyze_workflow passed")

    def test_focus_then_generate_workflow(self):
        """Test the focus -> generate section workflow."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        # Step 1: Focus on papers
        search_results = create_sample_search_results(2)
        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel, recent_search_results=search_results)

        focus_result = orchestrator._tool_focus_on_papers(ctx, paper_indices=[0])
        assert focus_result["status"] == "success"

        # Step 2: Generate section (using same channel)
        generate_result = orchestrator._tool_generate_section_from_discussion(
            ctx,
            section_type="related_work"
        )
        assert generate_result["status"] == "success"
        assert generate_result["focused_paper_count"] == 1

        # Check context includes the focused paper
        assert "Test Paper 0" in generate_result["context"]

        print("✓ test_focus_then_generate_workflow passed")

    def test_deep_search_then_focus_workflow(self):
        """Test the deep search -> focus workflow."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}
        ctx = create_test_context(channel=channel)

        # Step 1: Deep search
        search_result = orchestrator._tool_deep_search_papers(
            ctx,
            research_question="What are transformer attention mechanisms?"
        )
        assert search_result["status"] == "success"

        # Verify the question was stored
        assert channel.ai_memory.get("deep_search", {}).get("last_question") is not None

        # Step 2: Simulate search results coming in, then focus
        ctx["recent_search_results"] = create_sample_search_results(5)

        focus_result = orchestrator._tool_focus_on_papers(ctx, paper_indices=[0, 1, 2])
        assert focus_result["status"] == "success"
        assert focus_result["focused_count"] == 3

        print("✓ test_deep_search_then_focus_workflow passed")


# ============================================================
# Run Tests
# ============================================================

def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("Deep Search & Paper Focus Tools - Tests")
    print("=" * 60 + "\n")

    test_classes = [
        TestToolDefinitions,
        TestDeepSearchPapers,
        TestFocusOnPapers,
        TestAnalyzeAcrossPapers,
        TestGenerateSectionFromDiscussion,
        TestToolStatusMessages,
        TestToolRouting,
        TestSystemPrompt,
        TestIntegration,
    ]

    passed = 0
    failed = 0
    errors = []

    for test_class in test_classes:
        print(f"\n--- {test_class.__name__} ---")
        instance = test_class()

        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    method = getattr(instance, method_name)
                    method()
                    passed += 1
                except AssertionError as e:
                    failed += 1
                    errors.append((test_class.__name__, method_name, str(e)))
                    print(f"✗ {method_name} FAILED: {e}")
                except Exception as e:
                    failed += 1
                    errors.append((test_class.__name__, method_name, str(e)))
                    print(f"✗ {method_name} ERROR: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if errors:
        print("\nFailed tests:")
        for cls, method, error in errors:
            print(f"  - {cls}.{method}: {error}")

    return failed == 0


if __name__ == "__main__":
    # Change to backend directory for imports
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    success = run_all_tests()
    sys.exit(0 if success else 1)
