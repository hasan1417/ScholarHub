"""Client construction must be local, bounded, and safe to log."""

import logging
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.services.ai_client import AIClient


def test_initialization_is_offline_and_does_not_log_key_material(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api_key = "sk-regression-secret-that-must-never-appear-in-logs"
    monkeypatch.setenv("OPENAI_API_KEY", api_key)

    with (
        caplog.at_level(logging.INFO, logger="app.services.ai_client"),
        patch.object(httpx.Client, "send", side_effect=AssertionError("Unexpected network request")) as send,
    ):
        client = AIClient()

    try:
        assert client.initialization_status == "ready"
        assert client.openai_client is not None
        assert client.openai_client.timeout == 120.0
        assert client.openai_client.max_retries == 1
        send.assert_not_called()
        assert "OpenAI API key loaded" in caplog.text
        assert api_key[:20] not in caplog.text
    finally:
        if client.openai_client is not None:
            client.openai_client.close()


def test_document_processors_reuse_the_shared_ai_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.services.ai_service import ai_service
    from app.services.document_processing_service import DocumentProcessingService

    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))

    with patch.object(AIClient, "__init__", side_effect=AssertionError("Unexpected client construction")):
        first = DocumentProcessingService()
        second = DocumentProcessingService()

    assert first.ai_service is ai_service
    assert second.ai_service is ai_service
