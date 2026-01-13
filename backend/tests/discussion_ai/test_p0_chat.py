"""
P0 Tests: General Chat

Tests the chat skill which should:
- Handle greetings
- Handle thanks
- Handle general questions about capabilities
- Handle clarification requests
- Be single-turn
"""

import pytest
from uuid import uuid4

# Test cases: (user_message, should_be_chat)
CHAT_TEST_CASES = [
    # Greetings
    ("Hello", True),
    ("Hi there", True),
    ("Hey", True),
    ("Good morning", True),

    # Thanks
    ("Thanks!", True),
    ("Thank you", True),
    ("Thanks for your help", True),

    # Capability questions
    ("What can you help me with?", True),
    ("What can you do?", True),
    ("How can you assist me?", True),

    # General questions
    ("How are you?", True),
    ("Who are you?", True),

    # Clarification requests (these become CONTINUATION if in multi-turn)
    ("What do you mean?", True),
    ("Can you explain that?", True),
    ("I don't understand", True),

    # NOT chat - these should be other intents
    ("Find papers about transformers", False),
    ("Create a literature review", False),
    ("Explain the first paper", False),
    ("Edit my paper", False),
]


class TestChatIntent:
    """Test that chat intent is correctly classified."""

    @pytest.mark.parametrize("message,should_be_chat", CHAT_TEST_CASES)
    def test_chat_intent_classification(self, message, should_be_chat):
        """Chat messages should be classified as CHAT intent."""
        from app.services.discussion_ai.skills.router import IntentRouter
        from app.services.discussion_ai.skills.base import Intent

        router = IntentRouter()
        result = router.classify(message)

        if should_be_chat:
            assert result.intent == Intent.CHAT, f"Expected CHAT for: {message}"
        else:
            assert result.intent != Intent.CHAT, f"Should NOT be CHAT for: {message}"


class TestChatSkill:
    """Test the chat skill behavior."""

    @pytest.fixture
    def mock_ai_service(self):
        """Mock AI service."""
        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {
                            'content': "Hello! I'm your research assistant. I can help you search for papers, create literature reviews, summarize research, and more. What would you like to do?"
                        })()
                    })()]
                })()

            def extract_response_text(self, resp):
                return resp.choices[0].message.content

        return MockAI()

    @pytest.fixture
    def chat_skill(self, mock_ai_service):
        from app.services.discussion_ai.skills.chat import ChatSkill
        return ChatSkill(mock_ai_service)

    @pytest.fixture
    def make_context(self):
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

    def test_chat_is_single_turn(self, chat_skill, make_context):
        """Chat should complete in single turn."""
        from app.services.discussion_ai.skills.base import SkillState

        ctx = make_context("Hello")

        result = chat_skill.handle(ctx)

        assert result.next_state == SkillState.COMPLETE

    def test_chat_returns_friendly_response(self, chat_skill, make_context):
        """Chat should return a friendly response to greetings."""
        ctx = make_context("Hello")

        result = chat_skill.handle(ctx)

        assert result.message is not None
        assert len(result.message) > 0

    def test_chat_no_actions(self, chat_skill, make_context):
        """Chat should not return any actions."""
        ctx = make_context("Hi there")

        result = chat_skill.handle(ctx)

        assert len(result.actions) == 0

    def test_chat_handles_thanks(self, chat_skill, make_context):
        """Chat should respond appropriately to thanks."""
        ctx = make_context("Thanks!")

        result = chat_skill.handle(ctx)

        assert result.message is not None

    def test_chat_describes_capabilities(self, chat_skill, make_context):
        """Chat should describe capabilities when asked."""
        ctx = make_context("What can you do?")

        result = chat_skill.handle(ctx)

        assert result.message is not None
        # Response should mention some capabilities
        response_lower = result.message.lower()
        assert any(word in response_lower for word in ["help", "search", "papers", "research", "assist"])


class TestChatE2E:
    """End-to-end tests for chat flow."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mock AI service."""
        from app.services.discussion_ai.skills.orchestrator import DiscussionOrchestrator

        class MockAI:
            def create_response(self, **kwargs):
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Msg', (), {'content': 'Hello! How can I help you?'})()
                    })()]
                })()

            def extract_response_text(self, resp):
                return "Hello! How can I help you?"

        return DiscussionOrchestrator(MockAI())

    @pytest.fixture
    def mock_project(self):
        return type('Project', (), {'id': uuid4(), 'title': 'Test Project'})()

    @pytest.fixture
    def mock_channel(self):
        return type('Channel', (), {'id': uuid4(), 'name': 'General'})()

    def test_greeting_flow(self, orchestrator, mock_project, mock_channel):
        """Test complete greeting flow."""
        result = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "Hello"
        )

        assert "message" in result
        assert len(result["message"]) > 0
        assert result["actions"] == []

    def test_thanks_flow(self, orchestrator, mock_project, mock_channel):
        """Test thanks flow."""
        result = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "Thanks!"
        )

        assert "message" in result
        assert result["actions"] == []

    def test_capability_question_flow(self, orchestrator, mock_project, mock_channel):
        """Test capability question flow."""
        result = orchestrator.handle_message(
            mock_project,
            mock_channel,
            "What can you help me with?"
        )

        assert "message" in result
        assert len(result["message"]) > 0
