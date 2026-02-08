"""
Tests for OpenRouter API retry logic.

Tests that transient errors (429, 5xx, timeouts) are retried with exponential backoff,
while non-retryable errors (auth, invalid request) fail immediately.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from openai import RateLimitError, APIStatusError, APIConnectionError, APITimeoutError

from app.services.discussion_ai.openrouter_orchestrator import (
    OpenRouterOrchestrator,
    RETRYABLE_STATUS_CODES,
    MAX_RETRIES,
    INITIAL_BACKOFF_SECONDS,
)


async def _collect_async_gen(gen):
    """Helper to collect all events from an async generator."""
    events = []
    async for event in gen:
        events.append(event)
    return events


class TestIsRetryableError:
    """Test _is_retryable_error() classification."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.services.discussion_ai.openrouter_orchestrator.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.REDIS_URL = "redis://localhost"
            mock_settings.OPENROUTER_FALLBACK_MODELS_PATH = None
            orch = OpenRouterOrchestrator(
                ai_service=MagicMock(),
                db=MagicMock(),
                model="openai/gpt-4o",
                user_api_key="test-key",
            )
            return orch

    def test_rate_limit_error_is_retryable(self, orchestrator):
        """RateLimitError (429) should be retryable."""
        error = RateLimitError("rate limited", response=MagicMock(), body={})
        assert orchestrator._is_retryable_error(error) is True

    def test_connection_error_is_retryable(self, orchestrator):
        """APIConnectionError should be retryable."""
        error = APIConnectionError(request=MagicMock())
        assert orchestrator._is_retryable_error(error) is True

    def test_timeout_error_is_retryable(self, orchestrator):
        """APITimeoutError should be retryable."""
        error = APITimeoutError(request=MagicMock())
        assert orchestrator._is_retryable_error(error) is True

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_5xx_errors_are_retryable(self, orchestrator, status_code):
        """5xx status codes should be retryable."""
        error = APIStatusError(
            f"Server error {status_code}",
            response=MagicMock(status_code=status_code),
            body={},
        )
        assert orchestrator._is_retryable_error(error) is True

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_errors_not_retryable(self, orchestrator, status_code):
        """401/403 auth errors should NOT be retryable."""
        error = APIStatusError(
            f"Auth error {status_code}",
            response=MagicMock(status_code=status_code),
            body={},
        )
        assert orchestrator._is_retryable_error(error) is False

    def test_bad_request_not_retryable(self, orchestrator):
        """400 Bad Request should NOT be retryable."""
        error = APIStatusError(
            "Bad request",
            response=MagicMock(status_code=400),
            body={},
        )
        assert orchestrator._is_retryable_error(error) is False

    def test_not_found_not_retryable(self, orchestrator):
        """404 Not Found should NOT be retryable."""
        error = APIStatusError(
            "Not found",
            response=MagicMock(status_code=404),
            body={},
        )
        assert orchestrator._is_retryable_error(error) is False

    def test_generic_exception_not_retryable(self, orchestrator):
        """Generic exceptions should NOT be retryable."""
        error = ValueError("some error")
        assert orchestrator._is_retryable_error(error) is False


class TestNonStreamingRetry:
    """Test retry behavior for _call_ai_with_tools (non-streaming)."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.services.discussion_ai.openrouter_orchestrator.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.REDIS_URL = "redis://localhost"
            mock_settings.OPENROUTER_FALLBACK_MODELS_PATH = None
            orch = OpenRouterOrchestrator(
                ai_service=MagicMock(),
                db=MagicMock(),
                model="openai/gpt-4o",
                user_api_key="test-key",
            )
            # Mock _get_tools_for_user to return empty list
            orch._get_tools_for_user = MagicMock(return_value=[])
            return orch

    def _make_success_response(self, content="Success"):
        """Create a mock successful API response."""
        mock_message = MagicMock()
        mock_message.content = content
        mock_message.tool_calls = None
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    @patch('time.sleep')
    def test_succeeds_on_first_try(self, mock_sleep, orchestrator):
        """Should return result immediately if first call succeeds."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            return_value=self._make_success_response("Hello!")
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert result["content"] == "Hello!"
        assert result["tool_calls"] == []
        assert mock_sleep.call_count == 0

    @patch('time.sleep')
    def test_retries_on_rate_limit_then_succeeds(self, mock_sleep, orchestrator):
        """Should retry on rate limit and succeed on subsequent attempt."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=[
                RateLimitError("rate limited", response=MagicMock(), body={}),
                self._make_success_response("Success after retry"),
            ]
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert result["content"] == "Success after retry"
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(INITIAL_BACKOFF_SECONDS)

    @patch('time.sleep')
    def test_retries_with_exponential_backoff(self, mock_sleep, orchestrator):
        """Should use exponential backoff: 1s, 2s, 4s."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=[
                RateLimitError("rate limited", response=MagicMock(), body={}),
                RateLimitError("rate limited", response=MagicMock(), body={}),
                self._make_success_response("Success"),
            ]
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert result["content"] == "Success"
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)  # First backoff
        mock_sleep.assert_any_call(2.0)  # Second backoff

    @patch('time.sleep')
    def test_fails_after_max_retries(self, mock_sleep, orchestrator):
        """Should fail with user-friendly message after MAX_RETRIES exhausted."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=RateLimitError("rate limited", response=MagicMock(), body={})
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert "temporarily unavailable" in result["content"]
        assert "try again or switch models" in result["content"]
        assert orchestrator.openrouter_client.chat.completions.create.call_count == MAX_RETRIES
        assert mock_sleep.call_count == MAX_RETRIES - 1

    def test_no_retry_on_auth_error(self, orchestrator):
        """Should fail immediately on 401, no retry."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=APIStatusError(
                "Unauthorized",
                response=MagicMock(status_code=401),
                body={},
            )
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert "Error:" in result["content"]
        assert orchestrator.openrouter_client.chat.completions.create.call_count == 1

    def test_no_retry_on_bad_request(self, orchestrator):
        """Should fail immediately on 400, no retry."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=APIStatusError(
                "Invalid model",
                response=MagicMock(status_code=400),
                body={},
            )
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert "Error:" in result["content"]
        assert orchestrator.openrouter_client.chat.completions.create.call_count == 1

    @patch('time.sleep')
    def test_retries_on_503_service_unavailable(self, mock_sleep, orchestrator):
        """Should retry on 503 Service Unavailable."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=[
                APIStatusError("Service unavailable", response=MagicMock(status_code=503), body={}),
                self._make_success_response("Recovered"),
            ]
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert result["content"] == "Recovered"
        assert mock_sleep.call_count == 1

    @patch('time.sleep')
    def test_retries_on_connection_error(self, mock_sleep, orchestrator):
        """Should retry on connection errors."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=[
                APIConnectionError(request=MagicMock()),
                self._make_success_response("Connected"),
            ]
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert result["content"] == "Connected"
        assert mock_sleep.call_count == 1

    @patch('time.sleep')
    def test_retries_on_timeout(self, mock_sleep, orchestrator):
        """Should retry on timeout errors."""
        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            side_effect=[
                APITimeoutError(request=MagicMock()),
                self._make_success_response("Completed"),
            ]
        )

        result = orchestrator._call_ai_with_tools([], {})

        assert result["content"] == "Completed"
        assert mock_sleep.call_count == 1

    def test_non_streaming_handles_malformed_tool_args(self, orchestrator):
        """Malformed tool args should not crash response parsing."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "tc-1"
        mock_tool_call.function.name = "search_papers"
        mock_tool_call.function.arguments = "{bad-json"

        mock_message = MagicMock()
        mock_message.content = ""
        mock_message.tool_calls = [mock_tool_call]
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        orchestrator.openrouter_client.chat.completions.create = MagicMock(
            return_value=mock_response
        )

        result = orchestrator._call_ai_with_tools([], {"user_message": "find papers"})

        assert result["content"] == ""
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search_papers"
        assert result["tool_calls"][0]["arguments"] == {}


class TestStreamingRetry:
    """Test retry behavior for _call_ai_with_tools_streaming (async)."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.services.discussion_ai.openrouter_orchestrator.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.REDIS_URL = "redis://localhost"
            mock_settings.OPENROUTER_FALLBACK_MODELS_PATH = None
            orch = OpenRouterOrchestrator(
                ai_service=MagicMock(),
                db=MagicMock(),
                model="openai/gpt-4o",
                user_api_key="test-key",
            )
            orch._get_tools_for_user = MagicMock(return_value=[])
            return orch

    @staticmethod
    def _make_async_stream_chunks(content="Hello"):
        """Create a mock async stream that yields chunks."""
        chunks = []
        for char in content:
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content=char, tool_calls=None))]
            chunks.append(chunk)

        class AsyncStreamMock:
            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                for c in chunks:
                    yield c

        return AsyncStreamMock()

    def test_streaming_retries_on_init_failure(self, orchestrator):
        """Should retry stream initialization on transient errors."""
        call_count = 0
        stream_result = self._make_async_stream_chunks("OK")

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError("rate limited", response=MagicMock(), body={})
            return stream_result

        orchestrator.async_openrouter_client.chat.completions.create = mock_create

        async def run():
            with patch('asyncio.sleep', new_callable=AsyncMock):
                return await _collect_async_gen(
                    orchestrator._call_ai_with_tools_streaming([], {})
                )

        events = asyncio.run(run())

        result = events[-1]
        assert result["type"] == "result"
        assert result["content"] == "OK"

    def test_streaming_fails_after_max_retries(self, orchestrator):
        """Should fail with message after MAX_RETRIES exhausted."""
        async def mock_create(**kwargs):
            raise RateLimitError("rate limited", response=MagicMock(), body={})

        orchestrator.async_openrouter_client.chat.completions.create = mock_create

        async def run():
            with patch('asyncio.sleep', new_callable=AsyncMock):
                return await _collect_async_gen(
                    orchestrator._call_ai_with_tools_streaming([], {})
                )

        events = asyncio.run(run())

        result = events[-1]
        assert result["type"] == "result"
        assert "temporarily unavailable" in result["content"]

    def test_streaming_no_retry_on_auth_error(self, orchestrator):
        """Should fail immediately on auth error, no retry."""
        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            raise APIStatusError(
                "Unauthorized",
                response=MagicMock(status_code=401),
                body={},
            )

        orchestrator.async_openrouter_client.chat.completions.create = mock_create

        events = asyncio.run(_collect_async_gen(
            orchestrator._call_ai_with_tools_streaming([], {})
        ))

        result = events[-1]
        assert result["type"] == "result"
        assert "Error:" in result["content"]
        assert call_count == 1

class TestNoClientConfigured:
    """Test behavior when OpenRouter client is not configured."""

    def test_non_streaming_returns_error_message(self):
        """Should return helpful error when no API key configured."""
        with patch('app.services.discussion_ai.openrouter_orchestrator.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = None
            mock_settings.REDIS_URL = "redis://localhost"
            mock_settings.OPENROUTER_FALLBACK_MODELS_PATH = None
            orch = OpenRouterOrchestrator(
                ai_service=MagicMock(),
                db=MagicMock(),
                model="openai/gpt-4o",
                user_api_key=None,
            )

            result = orch._call_ai_with_tools([], {})

            assert "not configured" in result["content"]
            assert result["tool_calls"] == []

    def test_streaming_returns_error_message(self):
        """Should yield error result when no API key configured."""
        with patch('app.services.discussion_ai.openrouter_orchestrator.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = None
            mock_settings.REDIS_URL = "redis://localhost"
            mock_settings.OPENROUTER_FALLBACK_MODELS_PATH = None
            orch = OpenRouterOrchestrator(
                ai_service=MagicMock(),
                db=MagicMock(),
                model="openai/gpt-4o",
                user_api_key=None,
            )

            events = asyncio.run(_collect_async_gen(
                orch._call_ai_with_tools_streaming([], {})
            ))

            assert len(events) == 1
            assert events[0]["type"] == "result"
            assert "not configured" in events[0]["content"]
