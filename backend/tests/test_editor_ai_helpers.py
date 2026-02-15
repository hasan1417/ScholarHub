"""
Offline unit tests for Editor AI deterministic helpers.

These test pure functions on SmartAgentServiceV2 (and inherited by V2OR)
without requiring any API key or database connection.
"""
import pytest
from app.services.smart_agent_service_v2 import SmartAgentServiceV2
from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR


@pytest.fixture
def svc():
    """Create a V2 service with no API key (client=None). Helpers still work."""
    s = SmartAgentServiceV2()
    # client may be None if OPENAI_API_KEY is unset — that's fine for helper tests
    return s


@pytest.fixture
def svc_or():
    """Create a V2OR service with no API key. Verifies inheritance works."""
    s = SmartAgentServiceV2OR(user_api_key="dummy-key-not-used")
    return s


# ── Inheritance ──────────────────────────────────────────────────────

class TestInheritance:
    def test_v2or_is_subclass(self):
        assert issubclass(SmartAgentServiceV2OR, SmartAgentServiceV2)

    def test_inherited_helpers_available(self, svc_or):
        for method_name in (
            "_build_clarification",
            "_detect_operation",
            "_detect_target",
            "_has_constraints",
            "_is_convert_request",
            "_has_explicit_replacement",
            "_is_review_message",
            "_rewrite_affirmation",
            "_sanitize_assistant_content",
            "_format_tool_response",
            "_handle_list_templates",
            "_handle_apply_template",
            "_add_line_numbers",
            "_is_lite_route",
        ):
            assert hasattr(svc_or, method_name), f"V2OR missing inherited method: {method_name}"


# ── _build_clarification ─────────────────────────────────────────────

class TestBuildClarification:
    def test_returns_none_for_questions(self, svc):
        assert svc._build_clarification("What is the difference between A and B?", "doc") is None

    def test_returns_none_for_clarification_response(self, svc):
        assert svc._build_clarification("Clarification: I want the abstract shorter", "doc") is None

    def test_returns_none_for_convert_request(self, svc):
        assert svc._build_clarification("convert to IEEE", "doc") is None

    def test_returns_target_question_when_no_target(self, svc):
        result = svc._build_clarification("improve it", None)
        assert result is not None
        assert "options" in result

    def test_returns_constraint_question_for_improve_abstract(self, svc):
        result = svc._build_clarification("improve the abstract", "\\begin{document}")
        assert result is not None
        assert "optimize" in result["question"].lower() or "options" in result

    def test_returns_none_for_fix_grammar(self, svc):
        assert svc._build_clarification("fix grammar in the abstract", "doc") is None

    def test_returns_none_for_explicit_replacement(self, svc):
        assert svc._build_clarification('change title to "New Title"', "doc") is None

    def test_returns_none_for_empty_query(self, svc):
        assert svc._build_clarification("", "doc") is None

    def test_works_on_v2or(self, svc_or):
        """Verify the inherited method works identically on V2OR."""
        assert svc_or._build_clarification("fix grammar in the abstract", "doc") is None
        result = svc_or._build_clarification("improve it", None)
        assert result is not None


# ── _detect_operation ─────────────────────────────────────────────────

class TestDetectOperation:
    def test_fix_grammar(self, svc):
        assert svc._detect_operation("fix grammar") == "fix"

    def test_shorten(self, svc):
        assert svc._detect_operation("shorten the abstract") == "shorten"

    def test_rewrite(self, svc):
        assert svc._detect_operation("rewrite the introduction") == "rewrite"

    def test_improve(self, svc):
        assert svc._detect_operation("improve the abstract") == "improve"

    def test_expand(self, svc):
        assert svc._detect_operation("expand the methods section") == "expand"

    def test_change(self, svc):
        assert svc._detect_operation("change the title") == "change"

    def test_hello_returns_none(self, svc):
        assert svc._detect_operation("hello") is None

    def test_question_returns_none(self, svc):
        assert svc._detect_operation("what is the abstract about") is None


# ── _detect_target ────────────────────────────────────────────────────

class TestDetectTarget:
    def test_abstract(self, svc):
        assert svc._detect_target("improve the abstract") == "abstract"

    def test_methods(self, svc):
        # "method" matches before "methods" in _TARGET_TERMS (substring match)
        assert svc._detect_target("shorten the methods section") == "method"

    def test_introduction(self, svc):
        assert svc._detect_target("rewrite the introduction") == "introduction"

    def test_no_target(self, svc):
        assert svc._detect_target("fix typos") is None

    def test_conclusion(self, svc):
        assert svc._detect_target("expand the conclusion") == "conclusion"

    def test_document(self, svc):
        assert svc._detect_target("improve the document") == "document"


# ── _rewrite_affirmation ─────────────────────────────────────────────

class TestRewriteAffirmation:
    def test_yes_after_review(self, svc):
        history = [
            {"role": "user", "content": "review the abstract"},
            {"role": "assistant", "content": "## Review\n\nThe abstract is good.\n\n### Suggested Improvements\n- Be more specific"},
        ]
        result = svc._rewrite_affirmation("yes", history)
        assert result is not None
        assert "apply" in result.lower()

    def test_do_it_after_review(self, svc):
        history = [
            {"role": "assistant", "content": "## Review\n\nStrong paper.\n\n### Suggested Improvements\n- Fix typos"},
        ]
        result = svc._rewrite_affirmation("do it", history)
        assert result is not None

    def test_yes_without_prior_review(self, svc):
        history = [
            {"role": "assistant", "content": "Hello! How can I help?"},
        ]
        assert svc._rewrite_affirmation("yes", history) is None

    def test_normal_message_returns_none(self, svc):
        history = [
            {"role": "assistant", "content": "## Review\n\nGood paper."},
        ]
        assert svc._rewrite_affirmation("improve the abstract", history) is None

    def test_empty_history(self, svc):
        assert svc._rewrite_affirmation("yes", []) is None


# ── _is_lite_route ────────────────────────────────────────────────────

class TestIsLiteRoute:
    """Test _is_lite_route via the action-verb early exit (no mocking needed)."""

    def test_edit_request_is_not_lite(self, svc):
        assert svc._is_lite_route("improve the abstract", []) is False

    def test_fix_request_is_not_lite(self, svc):
        assert svc._is_lite_route("fix grammar", []) is False

    def test_convert_request_is_not_lite(self, svc):
        assert svc._is_lite_route("convert to IEEE", []) is False


# ── _is_convert_request ──────────────────────────────────────────────

class TestIsConvertRequest:
    def test_convert_to_ieee(self, svc):
        assert svc._is_convert_request("convert to ieee") is True

    def test_reformat_for_acl(self, svc):
        assert svc._is_convert_request("reformat for acl") is True

    def test_template_keyword(self, svc):
        assert svc._is_convert_request("change template") is True

    def test_improve_abstract_is_not_convert(self, svc):
        assert svc._is_convert_request("improve the abstract") is False


# ── _has_constraints ──────────────────────────────────────────────────

class TestHasConstraints:
    def test_word_count(self, svc):
        assert svc._has_constraints("make it 200 words") is True

    def test_shorter(self, svc):
        assert svc._has_constraints("make it shorter") is True

    def test_formal(self, svc):
        assert svc._has_constraints("make it more formal") is True

    def test_no_constraints(self, svc):
        assert svc._has_constraints("improve the abstract") is False


# ── _is_review_message ───────────────────────────────────────────────

class TestIsReviewMessage:
    def test_review_header(self, svc):
        assert svc._is_review_message("## Review\n\nGood paper.") is True

    def test_suggested_improvements(self, svc):
        assert svc._is_review_message("Suggested Improvements\n- Fix typos") is True

    def test_normal_message(self, svc):
        assert svc._is_review_message("I fixed the abstract.") is False

    def test_empty(self, svc):
        assert svc._is_review_message("") is False


# ── _sanitize_assistant_content ───────────────────────────────────────

class TestSanitizeAssistantContent:
    def test_strips_edit_marker(self, svc):
        result = svc._sanitize_assistant_content("Some text<<<EDIT>>>edit content")
        assert result == "Some text"

    def test_strips_clarify_marker(self, svc):
        result = svc._sanitize_assistant_content("Some text<<<CLARIFY>>>clarify content")
        assert result == "Some text"

    def test_no_markers(self, svc):
        assert svc._sanitize_assistant_content("Normal response") == "Normal response"


# ── _add_line_numbers ─────────────────────────────────────────────────

class TestAddLineNumbers:
    def test_basic(self, svc):
        result = svc._add_line_numbers("line1\nline2\nline3")
        assert "  1| line1" in result
        assert "  2| line2" in result
        assert "  3| line3" in result

    def test_single_line(self, svc):
        result = svc._add_line_numbers("only line")
        assert "  1| only line" in result


# ── _format_tool_response ─────────────────────────────────────────────

class TestFormatToolResponse:
    def test_answer_question(self, svc):
        result = "".join(svc._format_tool_response("answer_question", {"answer": "42"}))
        assert result == "42"

    def test_ask_clarification(self, svc):
        result = "".join(svc._format_tool_response("ask_clarification", {
            "question": "What should I change?",
            "options": ["Title", "Abstract"],
        }))
        assert "<<<CLARIFY>>>" in result
        assert "What should I change?" in result
        assert "Title" in result

    def test_propose_edit(self, svc):
        result = "".join(svc._format_tool_response("propose_edit", {
            "explanation": "Fixing typos",
            "edits": [{
                "description": "Fix typo",
                "start_line": 1,
                "end_line": 1,
                "anchor": "Teh quick",
                "proposed": "The quick",
            }],
        }))
        assert "<<<EDIT>>>" in result
        assert "Fixing typos" in result
        assert "<<<PROPOSED>>>" in result

    def test_review_document(self, svc):
        result = "".join(svc._format_tool_response("review_document", {
            "summary": "Good paper overall",
            "strengths": ["Clear writing"],
            "improvements": ["Add more references"],
            "offer_edits": True,
        }))
        assert "## Review" in result
        assert "Clear writing" in result
        assert "Add more references" in result

    def test_unknown_tool(self, svc):
        result = "".join(svc._format_tool_response("nonexistent_tool", {}))
        assert "Unknown tool" in result


# ── _is_retryable (V2OR-only) ────────────────────────────────────────

class TestIsRetryable:
    def test_rate_limit_error(self):
        from openai import RateLimitError
        # RateLimitError needs a response-like object
        import httpx
        resp = httpx.Response(429, request=httpx.Request("POST", "https://example.com"), json={"error": {"message": "rate limited"}})
        err = RateLimitError("rate limited", response=resp, body={"error": {"message": "rate limited"}})
        assert SmartAgentServiceV2OR._is_retryable(err) is True

    def test_api_connection_error(self):
        from openai import APIConnectionError
        import httpx
        err = APIConnectionError(request=httpx.Request("POST", "https://example.com"))
        assert SmartAgentServiceV2OR._is_retryable(err) is True

    def test_non_retryable_error(self):
        assert SmartAgentServiceV2OR._is_retryable(ValueError("bad value")) is False

    def test_api_status_502(self):
        from openai import APIStatusError
        import httpx
        resp = httpx.Response(502, request=httpx.Request("POST", "https://example.com"), json={"error": {"message": "bad gateway"}})
        err = APIStatusError("bad gateway", response=resp, body={"error": {"message": "bad gateway"}})
        assert SmartAgentServiceV2OR._is_retryable(err) is True

    def test_api_status_400_not_retryable(self):
        from openai import APIStatusError
        import httpx
        resp = httpx.Response(400, request=httpx.Request("POST", "https://example.com"), json={"error": {"message": "bad request"}})
        err = APIStatusError("bad request", response=resp, body={"error": {"message": "bad request"}})
        assert SmartAgentServiceV2OR._is_retryable(err) is False

    def test_api_timeout_error(self):
        from openai import APITimeoutError
        import httpx
        err = APITimeoutError(request=httpx.Request("POST", "https://example.com"))
        assert SmartAgentServiceV2OR._is_retryable(err) is True


# ── _unescape_json_partial (V2OR-only) ───────────────────────────────

class TestUnescapeJsonPartial:
    def test_simple_text(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("hello world")
        assert text == "hello world"
        assert rem == ""

    def test_closing_quote(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial('hello"rest')
        assert text == "hello"
        assert rem == "rest"

    def test_newline_escape(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("line1\\nline2")
        assert text == "line1\nline2"

    def test_tab_escape(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("col1\\tcol2")
        assert text == "col1\tcol2"

    def test_escaped_quote(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial('say \\"hello\\"')
        assert text == 'say "hello"'

    def test_escaped_backslash(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("path\\\\dir")
        assert text == "path\\dir"

    def test_unicode_escape(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("\\u0041BC")
        assert text == "ABC"

    def test_incomplete_unicode_at_end(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("hello\\u00")
        assert text == "hello"
        assert rem == "\\u00"

    def test_trailing_backslash(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("hello\\")
        assert text == "hello"
        assert rem == "\\"

    def test_empty_buffer(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("")
        assert text == ""
        assert rem == ""

    def test_slash_escape(self):
        text, rem = SmartAgentServiceV2OR._unescape_json_partial("a\\/b")
        assert text == "a/b"


# ── _resolve_tool_choice (V2OR-only) ─────────────────────────────────

class TestResolveToolChoice:
    def test_turn_1_normal(self, svc_or):
        assert svc_or._resolve_tool_choice("improve the abstract", 1) == "required"

    def test_turn_2_always_auto(self, svc_or):
        assert svc_or._resolve_tool_choice("improve the abstract", 2) == "auto"

    def test_empty_query(self, svc_or):
        assert svc_or._resolve_tool_choice("", 1) == "required"

    def test_template_listing_pinned(self, svc_or):
        # Regex uses \btemplate\b (singular) — "show template" matches
        result = svc_or._resolve_tool_choice("show available template format", 1)
        assert isinstance(result, dict)
        assert result["function"]["name"] == "list_available_templates"

    def test_apply_suggestions_auto(self, svc_or):
        assert svc_or._resolve_tool_choice("apply all suggested changes", 1) == "auto"

    def test_apply_critical_auto(self, svc_or):
        assert svc_or._resolve_tool_choice("apply critical fixes", 1) == "auto"
