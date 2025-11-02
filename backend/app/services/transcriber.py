"""Client wrapper for the internal transcription service."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when the transcription service returns an error."""


class TranscriberService:
    def __init__(self, base_url: str, timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def transcribe_audio(
        self,
        data: bytes,
        filename: str,
        content_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> dict[str, Any]:
        if not data:
            raise ValueError("Audio payload is empty")

        url = f"{self.base_url}/transcribe"
        files = {
            "file": (
                filename,
                data,
                content_type or "audio/wav",
            )
        }
        params: dict[str, Any] = {}
        if language:
            params["language"] = language

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                response = await client.post(url, files=files, params=params)
                response.raise_for_status()
            except httpx.HTTPError as exc:  # pragma: no cover - network
                logger.error("Transcription request failed", exc_info=exc)
                raise TranscriptionError("Transcription service unavailable") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise TranscriptionError("Unexpected response from transcription service")
        return payload


_transcriber: Optional[TranscriberService] = None


def get_transcriber_service(base_url: str) -> TranscriberService:
    global _transcriber
    if _transcriber is None or _transcriber.base_url != base_url.rstrip("/"):
        _transcriber = TranscriberService(base_url=base_url)
    return _transcriber
