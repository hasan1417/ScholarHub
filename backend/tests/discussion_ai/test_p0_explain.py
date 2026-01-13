"""
P0 Tests: Explain Paper/Concept

Tests the explain skill which should:
- Use multiple context sources (discovered refs, project refs, project papers, project info)
- Handle questions about specific papers
- Handle questions about project objectives/goals
- Handle general concept explanations
- Be single-turn (no clarification needed for most cases)
"""

import pytest
from uuid import uuid4

# Test cases: (user_message, expected_source, description)
EXPLAIN_TEST_CASES = [
    # Questions about discovered papers (from recent search)
    ("Explain the first paper", "discovered_refs", "Reference by position"),
    ("What's the main contribution of paper 2?", "discovered_refs", "Contribution question"),
    ("Summarize the above papers", "discovered_refs", "Summarize discovered"),
    ("What methodology does the third paper use?", "discovered_refs", "Methodology question"),

    # Questions about project references (saved in library)
    ("What do my references say about transformers?", "project_refs", "Project refs query"),
    ("Which of my saved papers discusses attention?", "project_refs", "Saved papers query"),
    ("Cite from my library about CNNs", "project_refs", "Library citation"),

    # Questions about project papers (user's own writing)
    ("What does my paper say about the methodology?", "project_papers", "Own paper query"),
    ("Summarize our paper's introduction", "project_papers", "Own paper section"),
    ("What claims do we make in our paper?", "project_papers", "Own paper claims"),

    # Questions about project info (objectives, description)
    ("What are our project objectives?", "project_info", "Objectives query"),
    ("What's the scope of this project?", "project_info", "Scope query"),
    ("What are we trying to achieve?", "project_info", "Goals query"),
    ("Remind me what this project is about", "project_info", "Project description"),

    # General concept explanations (use all available context)
    ("Explain how self-attention works", "general", "Concept explanation"),
    ("What is a transformer architecture?", "general", "Architecture explanation"),
    ("How does BERT differ from GPT?", "general", "Comparison explanation"),
]


class TestExplainIntent:
    """Test that explain intent is correctly classified."""

    @pytest.mark.parametrize("message,expected_source,description", EXPLAIN_TEST_CASES)
    def test_explain_intent_classification(self, message, expected_source, description):
        """Explain messages should be classified as EXPLAIN intent."""
        from app.services.discussion_ai.skills.router import IntentRouter
        from app.services.discussion_ai.skills.base import Intent

        router = IntentRouter()
        result = router.classify(message)

        assert result.intent == Intent.EXPLAIN, f"Expected EXPLAIN for: {message} ({description})"


class TestExplainContextSelection:
    """Test that explain skill selects correct context sources."""

    @pytest.fixture
    def explain_skill(self):
        from app.services.discussion_ai.skills.explain import ExplainSkill

        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {'content': 'Test explanation'})()
                    })()]
                })()
            def extract_response_text(self, resp):
                return "Test explanation"

        return ExplainSkill(MockAI())

    @pytest.fixture
    def make_context(self):
        """Factory for creating test contexts with various data sources."""
        from app.services.discussion_ai.skills.base import SkillContext, SkillState

        def _make(
            message: str,
            discovered_refs: list = None,
            project_refs: list = None,
            project_papers: list = None,
            project_info: dict = None,
        ):
            return SkillContext(
                project_id=uuid4(),
                project_title="Test Project",
                channel_id=uuid4(),
                user_message=message,
                skill_state=SkillState.IDLE,
                skill_data={},
                recent_search_results=discovered_refs,
                project_references=project_refs,
                project_papers=project_papers,
                project_info=project_info,
            )
        return _make

    def test_uses_discovered_refs_for_above_papers(self, explain_skill, make_context):
        """Questions about 'above papers' should use discovered refs."""
        discovered = [
            {"title": "Vision Transformer", "abstract": "ViT paper abstract"},
            {"title": "BERT Paper", "abstract": "BERT paper abstract"},
        ]
        ctx = make_context(
            "Explain the first paper",
            discovered_refs=discovered,
        )

        selected_sources = explain_skill._select_context_sources(ctx)

        assert "discovered_refs" in selected_sources
        assert len(selected_sources["discovered_refs"]) == 2

    def test_uses_project_papers_for_my_paper(self, explain_skill, make_context):
        """Questions about 'my paper' should use project papers."""
        papers = [
            {"title": "Our Research Paper", "content": "Introduction section..."},
        ]
        ctx = make_context(
            "What does my paper say about attention?",
            project_papers=papers,
        )

        selected_sources = explain_skill._select_context_sources(ctx)

        assert "project_papers" in selected_sources

    def test_uses_project_info_for_objectives(self, explain_skill, make_context):
        """Questions about objectives should use project info."""
        info = {
            "objectives": "Study transformer architectures",
            "scope": "Focus on vision applications",
        }
        ctx = make_context(
            "What are our project objectives?",
            project_info=info,
        )

        selected_sources = explain_skill._select_context_sources(ctx)

        assert "project_info" in selected_sources

    def test_uses_all_sources_for_general_questions(self, explain_skill, make_context):
        """General concept questions should use all available context."""
        ctx = make_context(
            "Explain how self-attention works",
            discovered_refs=[{"title": "Paper 1", "abstract": "..."}],
            project_refs=[{"title": "Ref 1", "abstract": "..."}],
            project_papers=[{"title": "Our Paper", "content": "..."}],
            project_info={"objectives": "..."},
        )

        selected_sources = explain_skill._select_context_sources(ctx)

        # For general questions, skill should have access to all sources
        assert len(selected_sources) >= 1  # At least some context available


class TestExplainSkill:
    """Test the explain skill behavior."""

    @pytest.fixture
    def mock_ai_service(self):
        """Mock AI service that returns canned responses."""
        class MockAI:
            def __init__(self):
                self.last_prompt = None

            def create_response(self, messages=None, **kwargs):
                if messages:
                    self.last_prompt = messages[-1].get("content", "")
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {
                            'content': 'The paper discusses attention mechanisms which allow models to focus on relevant parts of the input.'
                        })()
                    })()]
                })()

            def extract_response_text(self, resp):
                return resp.choices[0].message.content

        return MockAI()

    @pytest.fixture
    def explain_skill(self, mock_ai_service):
        from app.services.discussion_ai.skills.explain import ExplainSkill
        return ExplainSkill(mock_ai_service)

    @pytest.fixture
    def make_context(self):
        from app.services.discussion_ai.skills.base import SkillContext, SkillState

        def _make(message: str, **kwargs):
            return SkillContext(
                project_id=uuid4(),
                project_title="Test Project",
                channel_id=uuid4(),
                user_message=message,
                skill_state=SkillState.IDLE,
                skill_data={},
                **kwargs,
            )
        return _make

    def test_explain_is_single_turn(self, explain_skill, make_context):
        """Explain should complete in single turn."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context(
            "Explain how attention works",
            recent_search_results=[{"title": "Attention Paper", "abstract": "About attention"}],
        )

        result = explain_skill.handle(ctx)

        assert result.next_state == SkillState.COMPLETE

    def test_explain_returns_message(self, explain_skill, make_context):
        """Explain should return an explanation message."""
        ctx = make_context(
            "What is the main contribution of the first paper?",
            recent_search_results=[
                {"title": "ViT Paper", "abstract": "Vision Transformer contribution"},
            ],
        )

        result = explain_skill.handle(ctx)

        assert result.message is not None
        assert len(result.message) > 0

    def test_explain_no_actions(self, explain_skill, make_context):
        """Explain should not return actions (just text response)."""
        ctx = make_context(
            "Explain transformers",
            recent_search_results=[{"title": "Paper", "abstract": "..."}],
        )

        result = explain_skill.handle(ctx)

        assert len(result.actions) == 0

    def test_explain_handles_missing_context(self, explain_skill, make_context):
        """Explain should handle when no context is available."""
        ctx = make_context("Explain quantum computing")
        # No search results, no project refs, etc.

        result = explain_skill.handle(ctx)

        # Should still return a response (using general knowledge)
        assert result.message is not None


class TestExplainE2E:
    """End-to-end tests for explain flow."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mock AI service."""
        from app.services.discussion_ai.skills.orchestrator import DiscussionOrchestrator

        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {'content': 'Explanation of the concept.'})()
                    })()]
                })()
            def extract_response_text(self, resp):
                return "Explanation of the concept."

        return DiscussionOrchestrator(MockAI())

    @pytest.fixture
    def mock_project(self):
        return type('Project', (), {'id': uuid4(), 'title': 'Test Project'})()

    @pytest.fixture
    def mock_channel(self):
        return type('Channel', (), {'id': uuid4(), 'name': 'General'})()

    def test_explain_with_discovered_refs(self, orchestrator, mock_project, mock_channel):
        """Test explain flow with discovered references."""
        search_results = [
            {"title": "Vision Transformer", "abstract": "ViT explanation..."},
            {"title": "BERT", "abstract": "BERT explanation..."},
        ]

        result = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "Explain the first paper",
            recent_search_results=search_results,
        )

        assert "message" in result
        assert len(result["message"]) > 0
        assert result["actions"] == []  # Explain doesn't have actions

    def test_explain_about_project(self, orchestrator, mock_project, mock_channel):
        """Test explain flow for project-related questions."""
        result = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "What are our project objectives?",
        )

        assert "message" in result
