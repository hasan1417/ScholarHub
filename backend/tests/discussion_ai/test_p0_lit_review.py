"""
P0 Tests: Create Literature Review

Tests the create content skill for literature reviews which should:
- Support smart multi-turn (ask only for missing parameters)
- Execute immediately if all parameters provided
- Ask for: theme, length, structure, output format
- Support writing in chat or creating as paper
"""

import pytest
from uuid import uuid4

# Test cases for intent classification: (message, should_be_create_content)
CREATE_CONTENT_INTENT_CASES = [
    # Literature review requests
    ("Create a literature review", True),
    ("Write a lit review about transformers", True),
    ("Create a literature review using these papers", True),
    ("Generate a review comparing these approaches", True),

    # Variations
    ("Make a lit review", True),
    ("Draft a literature review", True),
    ("Help me write a literature review", True),

    # NOT create content
    ("Find papers about transformers", False),
    ("Explain the first paper", False),
    ("Hello", False),
]

# Test cases for parameter extraction: (message, expected_params)
PARAMETER_EXTRACTION_CASES = [
    # Full parameters provided
    (
        "Create a 2-page thematic literature review about attention, in chat",
        {"theme": "attention", "length": "brief", "structure": "thematic", "output": "chat"}
    ),
    # Partial parameters
    (
        "Create a literature review about transformers",
        {"theme": "transformers"}  # Missing: length, structure, output
    ),
    (
        "Write a comprehensive literature review",
        {"length": "comprehensive"}  # Missing: theme, structure, output
    ),
    # No parameters
    (
        "Create a literature review",
        {}  # Missing all
    ),
]


class TestCreateContentIntent:
    """Test that create content intent is correctly classified."""

    @pytest.mark.parametrize("message,should_be_create", CREATE_CONTENT_INTENT_CASES)
    def test_create_content_intent(self, message, should_be_create):
        """Create content messages should be classified correctly."""
        from app.services.discussion_ai.skills.router import IntentRouter
        from app.services.discussion_ai.skills.base import Intent

        router = IntentRouter()
        result = router.classify(message)

        if should_be_create:
            assert result.intent == Intent.CREATE_CONTENT, f"Expected CREATE_CONTENT for: {message}"
        else:
            assert result.intent != Intent.CREATE_CONTENT, f"Should NOT be CREATE_CONTENT for: {message}"


class TestParameterExtraction:
    """Test that parameters are correctly extracted from messages."""

    @pytest.mark.parametrize("message,expected_params", PARAMETER_EXTRACTION_CASES)
    def test_parameter_extraction(self, message, expected_params):
        """Parameters should be extracted from natural language."""
        from app.services.discussion_ai.skills.router import IntentRouter

        router = IntentRouter()
        result = router.classify(message)

        # Check that expected params are present
        for key, value in expected_params.items():
            assert key in result.params, f"Missing param {key} for: {message}"
            if value:
                assert result.params[key] == value or value.lower() in str(result.params[key]).lower()


class TestLitReviewMultiTurn:
    """Test multi-turn conversation flow for literature review."""

    @pytest.fixture
    def mock_ai_service(self):
        """Mock AI service for content generation."""
        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {
                            'content': 'This is a generated literature review about the topic.'
                        })()
                    })()]
                })()

            def extract_response_text(self, resp):
                return resp.choices[0].message.content

        return MockAI()

    @pytest.fixture
    def create_content_skill(self, mock_ai_service):
        from app.services.discussion_ai.skills.create_content import CreateContentSkill
        return CreateContentSkill(mock_ai_service)

    @pytest.fixture
    def make_context(self):
        from app.services.discussion_ai.skills.base import SkillContext, SkillState

        def _make(
            message: str,
            skill_state: SkillState = SkillState.IDLE,
            skill_data: dict = None,
            search_results: list = None,
        ):
            return SkillContext(
                project_id=uuid4(),
                project_title="Test Project",
                channel_id=uuid4(),
                user_message=message,
                skill_state=skill_state,
                skill_data=skill_data or {},
                recent_search_results=search_results,
            )
        return _make

    def test_missing_all_params_asks_questions(self, create_content_skill, make_context):
        """When all parameters missing, should ask clarifying questions."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context(
            "Create a literature review",
            search_results=[{"title": "Paper 1", "abstract": "..."}],
        )

        result = create_content_skill.handle(ctx)

        # Should ask for missing parameters
        assert result.next_state == SkillState.CLARIFYING
        # Message should ask about theme, length, structure
        response_lower = result.message.lower()
        assert any(word in response_lower for word in ["theme", "topic", "about"])

    def test_partial_params_asks_only_missing(self, create_content_skill, make_context):
        """When some parameters provided, should only ask for missing ones."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context(
            "Create a literature review about transformers",
            skill_data={"theme": "transformers"},  # Theme provided
            search_results=[{"title": "Paper 1", "abstract": "..."}],
        )

        result = create_content_skill.handle(ctx)

        # Should still need clarification for length/structure
        assert result.next_state in [SkillState.CLARIFYING, SkillState.CONFIRMING]
        # Should NOT ask about theme since it's provided
        # But should ask about length/structure/output

    def test_full_params_executes_immediately(self, create_content_skill, make_context):
        """When all parameters provided, should execute immediately."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context(
            "Create a 2-page thematic literature review about attention, in chat",
            skill_data={
                "theme": "attention",
                "length": "brief",
                "structure": "thematic",
                "output": "chat",
            },
            search_results=[{"title": "Paper 1", "abstract": "About attention"}],
        )

        result = create_content_skill.handle(ctx)

        # Should complete immediately (generate content)
        assert result.next_state == SkillState.COMPLETE
        assert len(result.message) > 0  # Should have generated content

    def test_clarification_response_advances_state(self, create_content_skill, make_context):
        """Providing clarification should advance the conversation."""
        from app.services.discussion_ai.skills.base import SkillState

        # Simulate being in CLARIFYING state with partial data
        ctx = make_context(
            "2 pages, thematic",
            skill_state=SkillState.CLARIFYING,
            skill_data={"theme": "attention"},  # Theme was provided earlier
            search_results=[{"title": "Paper", "abstract": "..."}],
        )

        result = create_content_skill.handle(ctx)

        # Should advance to CONFIRMING or COMPLETE
        assert result.next_state in [SkillState.CONFIRMING, SkillState.COMPLETE]

    def test_chat_confirmation_generates_content(self, create_content_skill, make_context):
        """Confirming 'chat' should generate content in response."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context(
            "chat",
            skill_state=SkillState.CONFIRMING,
            skill_data={
                "theme": "attention",
                "length": "brief",
                "structure": "thematic",
            },
            search_results=[{"title": "Paper", "abstract": "..."}],
        )

        result = create_content_skill.handle(ctx)

        assert result.next_state == SkillState.COMPLETE
        assert len(result.message) > 0  # Generated content
        assert len(result.actions) == 0  # No action, content is in message


class TestLitReviewOutputOptions:
    """Test different output options for literature review."""

    @pytest.fixture
    def mock_ai_service(self):
        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {
                            'content': '## Literature Review\n\nThis is the generated content.'
                        })()
                    })()]
                })()

            def extract_response_text(self, resp):
                return resp.choices[0].message.content

        return MockAI()

    @pytest.fixture
    def create_content_skill(self, mock_ai_service):
        from app.services.discussion_ai.skills.create_content import CreateContentSkill
        return CreateContentSkill(mock_ai_service)

    @pytest.fixture
    def make_context(self):
        from app.services.discussion_ai.skills.base import SkillContext, SkillState

        def _make(message: str, skill_state: SkillState, skill_data: dict):
            return SkillContext(
                project_id=uuid4(),
                project_title="Test Project",
                channel_id=uuid4(),
                user_message=message,
                skill_state=skill_state,
                skill_data=skill_data,
                recent_search_results=[{"title": "Paper", "abstract": "..."}],
            )
        return _make

    def test_output_chat_returns_content_in_message(self, create_content_skill, make_context):
        """Output='chat' should return content in message, no action."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context(
            "chat",
            SkillState.CONFIRMING,
            {"theme": "attention", "length": "brief", "structure": "thematic"},
        )

        result = create_content_skill.handle(ctx)

        assert len(result.message) > 0
        assert len(result.actions) == 0

    def test_output_paper_returns_create_action(self, create_content_skill, make_context):
        """Output='paper' should return create_paper action."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context(
            "create as paper",
            SkillState.CONFIRMING,
            {"theme": "attention", "length": "brief", "structure": "thematic"},
        )

        result = create_content_skill.handle(ctx)

        # Should have a create_paper action
        assert len(result.actions) == 1
        assert result.actions[0]["type"] == "create_paper"
        assert "content" in result.actions[0]["payload"]


class TestLitReviewE2E:
    """End-to-end tests for literature review flow."""

    @pytest.fixture
    def orchestrator(self):
        from app.services.discussion_ai.skills.orchestrator import DiscussionOrchestrator

        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {
                            'content': 'Generated literature review content.'
                        })()
                    })()]
                })()

            def extract_response_text(self, resp):
                return "Generated literature review content."

        return DiscussionOrchestrator(MockAI())

    @pytest.fixture
    def mock_project(self):
        return type('Project', (), {'id': uuid4(), 'title': 'Test Project'})()

    @pytest.fixture
    def mock_channel(self):
        return type('Channel', (), {'id': uuid4(), 'name': 'General'})()

    def test_full_multi_turn_flow(self, orchestrator, mock_project, mock_channel):
        """Test complete multi-turn literature review flow."""
        search_results = [
            {"title": "Paper 1", "abstract": "About attention"},
            {"title": "Paper 2", "abstract": "About transformers"},
        ]

        # Turn 1: Initial request (missing params)
        result1 = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "Create a literature review",
            recent_search_results=search_results,
        )

        assert "message" in result1
        # Should have a response (clarifying questions via mock AI)
        assert len(result1["message"]) > 0

        # Turn 2: Provide parameters
        result2 = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "attention mechanisms, 2 pages, thematic",
            recent_search_results=search_results,
        )

        # Should ask about output format or be ready to generate
        assert "message" in result2

        # Turn 3: Confirm output
        result3 = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "chat",
            recent_search_results=search_results,
        )

        # Should have generated content
        assert "message" in result3
        assert len(result3["message"]) > 0

    def test_immediate_execution_with_full_params(self, orchestrator, mock_project, mock_channel):
        """Test immediate execution when all params provided."""
        search_results = [
            {"title": "Paper 1", "abstract": "About attention"},
        ]

        result = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "Create a 2-page thematic literature review about attention, write in chat",
            recent_search_results=search_results,
        )

        # Should complete in one turn
        assert "message" in result
        # Message should be the generated content or a short response + content
