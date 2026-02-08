"""Tests for the lite/full route classifier."""

import pytest
from app.services.discussion_ai.route_classifier import classify_route, RouteDecision


class TestClassifyRoute:
    """Test classify_route() for correct lite/full routing."""

    # --- Lite routes ---

    @pytest.mark.parametrize("msg", ["hi", "hello", "hey", "Hi!", "Hello.", "Hey "])
    def test_greeting_routes_lite(self, msg):
        result = classify_route(msg, [], {})
        assert result.route == "lite"
        assert result.reason == "greeting_or_acknowledgment"

    @pytest.mark.parametrize("msg", [
        "thanks", "thank you", "Thanks!", "Thank you.",
        "sounds good", "got it", "ok", "okay",
        "cool", "great", "nice", "perfect", "awesome",
        "understood", "noted", "sure", "alright",
        "good morning", "good afternoon",
    ])
    def test_acknowledgment_routes_lite(self, msg):
        result = classify_route(msg, [], {})
        assert result.route == "lite"

    @pytest.mark.parametrize("msg", ["ok", "yep", "nope", "right", "k"])
    def test_short_message_routes_lite(self, msg):
        result = classify_route(msg, [], {})
        assert result.route == "lite"

    def test_empty_message_routes_lite(self):
        result = classify_route("", [], {})
        assert result.route == "lite"
        assert result.reason == "empty_message"

    def test_whitespace_only_routes_lite(self):
        result = classify_route("   ", [], {})
        assert result.route == "lite"
        assert result.reason == "empty_message"

    def test_standalone_confirmation_routes_lite(self):
        """'yes' without any pending assistant action should be lite."""
        result = classify_route("yes", [], {})
        assert result.route == "lite"
        assert result.reason == "standalone_confirmation"

    def test_standalone_confirmation_no_assistant_suggestion(self):
        """'yes' with a recent assistant message that doesn't suggest action -> lite."""
        history = [
            {"role": "assistant", "content": "Transformers are a neural network architecture."},
        ]
        result = classify_route("yes", history, {})
        assert result.route == "lite"
        assert result.reason == "standalone_confirmation"

    # --- Full routes ---

    @pytest.mark.parametrize("msg", [
        "What papers should I read?",
        "How does attention work?",
        "Can you help?",
    ])
    def test_question_routes_full(self, msg):
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert result.reason == "contains_question_mark"

    @pytest.mark.parametrize("msg", [
        "Find me papers on NLP",
        "Search for transformer architectures",
        "Create a literature review",
        "Write a summary of the findings",
        "Help me understand this",
        "Explain the methodology",
        "Suggest some related topics",
        "Analyze these results",
        "Add this to my library",
        "Generate an abstract",
    ])
    def test_action_verb_routes_full(self, msg):
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert result.reason == "action_verb_detected"

    @pytest.mark.parametrize("msg", [
        "I need to check my library",
        "Show me the paper",
        "What about the abstract",
        "Let's look at the references",
        "I'm doing research on ML",
    ])
    def test_research_term_routes_full(self, msg):
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert "research_term_detected" in result.reason or "action_verb_detected" in result.reason

    def test_long_message_routes_full(self):
        msg = "a" * 100  # 100 chars, no action verbs or research terms
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert result.reason == "long_message"

    def test_confirmation_with_pending_action_routes_full(self):
        """'yes' after assistant suggested an action should route full."""
        history = [
            {"role": "assistant", "content": "Shall I search for papers on this topic?"},
        ]
        result = classify_route("yes", history, {})
        assert result.route == "full"
        assert result.reason == "confirmation_of_pending_action"

    @pytest.mark.parametrize("msg", ["do it", "go ahead", "please do", "all of them", "go for it"])
    def test_action_confirmation_with_pending_action(self, msg):
        history = [
            {"role": "assistant", "content": "I can search for those papers. Want me to?"},
        ]
        result = classify_route(msg, history, {})
        assert result.route == "full"
        assert result.reason == "confirmation_of_pending_action"

    @pytest.mark.parametrize("hint", [
        "shall i", "should i", "want me to", "i can",
        "would you like me to", "ready to", "i'll",
        "let me know if", "do you want",
    ])
    def test_various_action_hints_detected(self, hint):
        history = [
            {"role": "assistant", "content": f"Interesting topic. {hint.capitalize()} do more research?"},
        ]
        result = classify_route("yes", history, {})
        assert result.route == "full"

    def test_default_routes_full(self):
        """Ambiguous message that doesn't match any pattern should go full."""
        msg = "I was thinking about that particular approach"  # 49 chars, no triggers
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert result.reason == "default_full"

    # --- Edge cases ---

    def test_none_message_routes_lite(self):
        result = classify_route(None, [], {})
        assert result.route == "lite"
        assert result.reason == "empty_message"

    def test_message_at_80_char_boundary(self):
        """Exactly 80 chars: >80 is false, but still routes full via default."""
        msg = "a" * 80
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert result.reason == "default_full"

    def test_message_at_81_chars_routes_full_long(self):
        """81 chars triggers the long_message rule."""
        msg = "a" * 81
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert result.reason == "long_message"

    def test_message_at_79_chars_no_triggers(self):
        """79 chars with no triggers should default to full (conservative)."""
        msg = "a" * 79
        result = classify_route(msg, [], {})
        assert result.route == "full"
        assert result.reason == "default_full"

    def test_short_message_with_question_mark_routes_full(self):
        """Even a short message with '?' should route full."""
        result = classify_route("ok?", [], {})
        assert result.route == "full"
        assert result.reason == "contains_question_mark"

    def test_greeting_with_question_mark_routes_full(self):
        """'hi?' with question mark -> full (question mark takes priority)."""
        result = classify_route("hi?", [], {})
        assert result.route == "full"
        assert result.reason == "contains_question_mark"

    def test_conversation_history_skips_user_messages(self):
        """Only checks assistant messages for pending action, not user messages."""
        history = [
            {"role": "user", "content": "shall i search?"},
            {"role": "assistant", "content": "Sure, that sounds good."},
        ]
        result = classify_route("yes", history, {})
        assert result.route == "lite"
        assert result.reason == "standalone_confirmation"

    def test_route_decision_is_frozen(self):
        """RouteDecision should be immutable."""
        result = classify_route("hi", [], {})
        with pytest.raises(AttributeError):
            result.route = "full"

    def test_memory_facts_accepted_but_unused(self):
        """memory_facts parameter accepted without error (reserved for future use)."""
        result = classify_route("hi", [], {"research_question": "some question"})
        assert result.route == "lite"
