"""
P0 Tests: Search for References

Tests the search skill which should:
- Parse search queries correctly
- Extract count from message
- Return search_references action
- Be single-turn (no clarification needed)
"""

import pytest
from uuid import uuid4

# Test cases: (user_message, expected_query_contains, expected_count)
SEARCH_TEST_CASES = [
    # Basic searches
    ("find 5 papers about transformers", "transformers", 5),
    ("search for references on NLP", "NLP", 5),  # default count
    ("look for 10 papers about attention mechanisms", "attention", 10),

    # Different phrasings
    ("find papers about machine learning", "machine learning", 5),
    ("search references regarding deep learning", "deep learning", 5),
    ("get me 3 papers on computer vision", "computer vision", 3),

    # Specific topics
    ("find 5 references about population-based metaheuristics", "metaheuristics", 5),
    ("search for papers on vision transformers ViT", "vision transformer", 5),
    ("look for 7 papers about BERT language models", "BERT", 7),

    # Edge cases
    ("find 20 papers about AI", "AI", 20),  # max count
    ("find 100 papers about AI", "AI", 20),  # should cap at 20
    ("papers about quantum computing", "quantum computing", 5),  # implicit search
]


class TestSearchIntent:
    """Test that search intent is correctly classified."""

    @pytest.mark.parametrize("message,expected_query,expected_count", SEARCH_TEST_CASES)
    def test_search_intent_classification(self, message, expected_query, expected_count):
        """Search messages should be classified as SEARCH intent."""
        from app.services.discussion_ai.skills.router import IntentRouter
        from app.services.discussion_ai.skills.base import Intent

        router = IntentRouter()
        result = router.classify(message)

        assert result.intent == Intent.SEARCH, f"Expected SEARCH intent for: {message}"
        assert result.confidence >= 0.8, f"Low confidence for: {message}"


class TestSearchSkill:
    """Test the search skill behavior."""

    @pytest.fixture
    def mock_ai_service(self):
        """Mock AI service - search skill doesn't need LLM calls."""
        class MockAI:
            pass
        return MockAI()

    @pytest.fixture
    def search_skill(self, mock_ai_service):
        from app.services.discussion_ai.skills.search import SearchSkill
        return SearchSkill(mock_ai_service)

    @pytest.fixture
    def make_context(self):
        """Factory for creating test contexts."""
        from app.services.discussion_ai.skills.base import SkillContext, SkillState

        def _make(message: str, skill_data: dict = None):
            return SkillContext(
                project_id=uuid4(),
                project_title="Test Project",
                channel_id=uuid4(),
                user_message=message,
                skill_state=SkillState.IDLE,
                skill_data=skill_data or {},
            )
        return _make

    def test_search_returns_action(self, search_skill, make_context):
        """Search should return a search_references action."""
        ctx = make_context("find 5 papers about transformers")
        ctx.skill_data = {"query": "transformers", "count": 5}

        result = search_skill.handle(ctx)

        assert len(result.actions) == 1, "Should return exactly one action"
        assert result.actions[0]["type"] == "search_references"
        assert result.actions[0]["payload"]["max_results"] == 5
        assert "transformers" in result.actions[0]["payload"]["query"].lower()

    def test_search_is_single_turn(self, search_skill, make_context):
        """Search should complete in single turn (no follow-up needed)."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context("find papers about NLP")
        ctx.skill_data = {"query": "NLP", "count": 5}

        result = search_skill.handle(ctx)

        assert result.next_state == SkillState.COMPLETE, "Search should complete immediately"

    def test_search_message_format(self, search_skill, make_context):
        """Search response should confirm what's being searched."""
        ctx = make_context("find 7 papers about BERT")
        ctx.skill_data = {"query": "BERT", "count": 7}

        result = search_skill.handle(ctx)

        assert "7" in result.message, "Should mention count"
        assert "BERT" in result.message or "bert" in result.message.lower(), "Should mention topic"


class TestSearchQueryExtraction:
    """Test query extraction from natural language."""

    def test_extract_query_removes_prefix(self):
        """Should extract clean query from message."""
        from app.services.discussion_ai.skills.router import IntentRouter

        router = IntentRouter()

        # Test various phrasings
        assert "transformers" in router._extract_search_query("find 5 papers about transformers").lower()
        assert "NLP" in router._extract_search_query("search for references on NLP")
        assert "attention" in router._extract_search_query("look for papers about attention mechanisms").lower()

    def test_extract_count(self):
        """Should extract count from message."""
        from app.services.discussion_ai.skills.router import IntentRouter

        router = IntentRouter()

        assert router._extract_count("find 5 papers about X") == 5
        assert router._extract_count("get 10 references") == 10
        assert router._extract_count("search for papers") == 5  # default
        assert router._extract_count("find 100 papers") == 20  # capped


class TestSearchE2E:
    """End-to-end tests for search flow."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mock AI service."""
        from app.services.discussion_ai.skills.orchestrator import DiscussionOrchestrator

        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {'choices': [type('Choice', (), {'message': type('Msg', (), {'content': 'test'})()})]})()
            def extract_response_text(self, resp):
                return "test response"

        return DiscussionOrchestrator(MockAI())

    @pytest.fixture
    def mock_project(self):
        """Create mock project."""
        return type('Project', (), {'id': uuid4(), 'title': 'Test Project'})()

    @pytest.fixture
    def mock_channel(self):
        """Create mock channel."""
        return type('Channel', (), {'id': uuid4(), 'name': 'General'})()

    def test_full_search_flow(self, orchestrator, mock_project, mock_channel):
        """Test complete search flow from message to action."""
        result = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "find 5 papers about vision transformers"
        )

        assert "message" in result
        assert "actions" in result
        assert len(result["actions"]) == 1
        assert result["actions"][0]["type"] == "search_references"
