"""Video session helpers backed by Daily.co."""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from app.core.config import settings
from app.services.daily import DailyClient, DailyMeetingToken, DailyAPIError


logger = logging.getLogger(__name__)


class VideoService:
    """Utility for preparing Daily rooms and issuing meeting tokens."""

    DEFAULT_TOKEN_TTL: timedelta = timedelta(hours=1)
    DEFAULT_ROOM_TTL: timedelta = timedelta(hours=6)

    _webhook_checked: bool = False

    def __init__(self) -> None:
        api_key = settings.DAILY_API_KEY
        room_hint = settings.DAILY_ROOM_BASE_URL or settings.DAILY_DOMAIN

        self._daily_client: Optional[DailyClient] = None
        if api_key and room_hint:
            self._daily_client = DailyClient(
                api_key=api_key,
                api_base_url=settings.DAILY_API_BASE_URL,
                domain=settings.DAILY_DOMAIN,
                room_base_url=settings.DAILY_ROOM_BASE_URL,
            )
            self._ensure_daily_webhook()

    @property
    def provider_name(self) -> str:
        return "daily" if self._daily_client else "stub"

    def ensure_room(self, room_name: str) -> None:
        if not self._daily_client:
            return

        ttl_seconds = settings.DAILY_ROOM_TTL_SECONDS or int(self.DEFAULT_ROOM_TTL.total_seconds())
        room_properties: dict[str, Any] = {}
        recording_mode = (settings.DAILY_ENABLE_RECORDING or "cloud").lower()
        if recording_mode:
            room_properties["enable_recording"] = recording_mode

        try:
            _ = self._daily_client.ensure_room(
                room_name,
                ttl_seconds=ttl_seconds,
                properties=room_properties or None,
            )
        except DailyAPIError as exc:
            info_text = str(exc.payload.get("info") or exc.message or "").lower()
            raise

    def _ensure_daily_webhook(self) -> None:
        if VideoService._webhook_checked:
            return
        if not self._daily_client:
            return
        secret = settings.DAILY_WEBHOOK_SECRET
        if not secret:
            logger.debug("Skipping Daily webhook setup: secret not configured")
            VideoService._webhook_checked = True
            return

        webhook_url = settings.DAILY_WEBHOOK_URL
        if not webhook_url and settings.BACKEND_PUBLIC_URL:
            base = settings.BACKEND_PUBLIC_URL.rstrip('/')
            webhook_url = f"{base}/api/v1/integrations/daily/webhook"

        if not webhook_url:
            logger.warning("Unable to derive Daily webhook URL; set DAILY_WEBHOOK_URL or BACKEND_PUBLIC_URL")
            return

        encoded_secret = base64.b64encode(secret.encode("utf-8")).decode("utf-8")

        try:
            existing = self._daily_client.list_webhooks()
            entries = []
            if isinstance(existing, dict):
                entries = existing.get("data") or existing.get("webhooks") or []
            elif isinstance(existing, list):
                entries = existing

            legacy_events = {"participant.joined", "recording.ready"}
            modern_events = {"participant.joined", "recording.ready-to-download"}
            desired_event_variants = [modern_events, legacy_events]
            for item in entries:
                if not isinstance(item, dict):
                    continue
                if item.get("url") != webhook_url:
                    continue
                current = set(
                    item.get("event_types")
                    or item.get("eventTypes")
                    or item.get("events")
                    or []
                )
                if any(variant.issubset(current) for variant in desired_event_variants):
                    VideoService._webhook_checked = True
                    return

            last_error: Optional[DailyAPIError] = None
            for variant in desired_event_variants:
                try:
                    self._daily_client.create_webhook(
                        url=webhook_url,
                        event_types=list(variant),
                        scope="account",
                        hmac_secret=encoded_secret,
                    )
                    logger.info(
                        "Registered Daily webhook",
                        extra={"url": webhook_url, "events": list(variant)},
                    )
                    VideoService._webhook_checked = True
                    return
                except DailyAPIError as exc_variant:
                    last_error = exc_variant
                    info_text = str(exc_variant.payload.get("info") or exc_variant.message or "").lower()
                    if exc_variant.status_code == 400:
                        if any(event in info_text for event in variant):
                            # The server rejected one of the requested events; try the
                            # next variant (old vs new naming).
                            continue
                        if '"scope" is not allowed' in info_text:
                            # Let DailyClient retry without the optional scope value.
                            continue
                    break

            if last_error is not None:
                raise last_error
            VideoService._webhook_checked = True
        except DailyAPIError as exc:
            info_text = str(exc.payload.get("info") or exc.message or "").lower()
            if "non-200 status code returned from webhook endpoint" in info_text:
                logger.warning(
                    "Daily webhook endpoint is unreachable from Daily's network; skipping auto-registration",
                    extra={"url": webhook_url},
                )
                VideoService._webhook_checked = True
                return

            logger.warning(
                "Failed to register Daily webhook",
                extra={"url": webhook_url, "error": str(exc)},
            )
        except Exception as exc:  # pragma: no cover - unexpected payload shape
            logger.warning(
                "Unexpected response while ensuring Daily webhook",
                extra={"url": webhook_url, "error": str(exc)},
            )

    def stop_recording(self, room_name: str) -> None:
        if not self._daily_client or not settings.DAILY_START_CLOUD_RECORDING:
            return
        try:
            self._daily_client.stop_recording(room_name)
        except DailyAPIError as exc:
            logger.warning(
                "Failed to stop Daily recording",
                extra={"room_name": room_name, "error": str(exc)},
            )

    def delete_room(self, room_name: str) -> None:
        if not self._daily_client:
            return
        try:
            self._daily_client.delete_room(room_name)
        except DailyAPIError as exc:
            logger.warning(
                "Failed to delete Daily room",
                extra={"room_name": room_name, "error": str(exc)},
            )

    def fetch_recent_recording(self, room_name: str) -> Optional[dict[str, Any]]:
        if not self._daily_client:
            return None
        try:
            response = self._daily_client.list_recordings(room_name=room_name)
        except DailyAPIError as exc:
            logger.warning(
                "Failed to list Daily recordings",
                extra={"room_name": room_name, "error": str(exc)},
            )
            return None

        items = []
        if isinstance(response, dict):
            items = response.get("data") or response.get("recordings") or []
        elif isinstance(response, list):
            items = response

        first_item: Optional[dict[str, Any]] = None
        for item in items:
            if not isinstance(item, dict):
                continue
            if first_item is None:
                first_item = item
            if item.get("download_link"):
                return item

        return first_item

    def delete_recording(self, recording_id: str) -> None:
        if not self._daily_client:
            return
        try:
            self._daily_client.delete_recording(recording_id)
        except DailyAPIError as exc:
            logger.warning(
                "Failed to delete Daily recording",
                extra={"recording_id": recording_id, "error": str(exc)},
            )

    async def ensure_recording_active(
        self,
        room_name: str,
        *,
        max_attempts: int = 8,
        delay_seconds: float = 8.0,
    ) -> None:
        if not self._daily_client or not settings.DAILY_START_CLOUD_RECORDING:
            return

        recording_type = (settings.DAILY_ENABLE_RECORDING or "cloud").lower()
        options: dict[str, Any] = {}
        if recording_type == "cloud" and settings.DAILY_RECORDING_AUDIO_ONLY:
            options["audio_only"] = True

        attempts = 0
        while attempts < max_attempts:
            try:
                self._daily_client.start_recording(room_name, recording_type=recording_type, options=options or None)
                logger.info(
                    "Started Daily recording",
                    extra={
                        "room_name": room_name,
                        "attempt": attempts + 1,
                        "recording_type": recording_type,
                        "audio_only": options.get("audio_only") if options else False,
                    },
                )
                return
            except DailyAPIError as exc:
                status = exc.status_code
                message = (exc.message or "").lower()
                attempts += 1

                if status == 429:
                    if attempts >= max_attempts:
                        logger.warning(
                            "Abandoning Daily recording start after rate-limit retries",
                            extra={"room_name": room_name, "attempts": attempts},
                        )
                        return
                    wait_time = max(delay_seconds * 2.0, 15.0)
                    logger.info(
                        "Daily recording start rate-limited; retrying",
                        extra={"room_name": room_name, "retry_in": wait_time, "attempt": attempts},
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if status in {404, 409} or "does not seem to be hosting" in message:
                    if attempts >= max_attempts:
                        logger.warning(
                            "Abandoning Daily recording start after %s attempts", attempts,
                            extra={"room_name": room_name},
                        )
                        return
                    await asyncio.sleep(delay_seconds)
                    continue

                logger.warning(
                    "Failed to start Daily recording",
                    extra={"room_name": room_name, "error": str(exc)},
                )
                return

    def create_token(
        self,
        *,
        session_id: UUID,
        room_name: str,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None,
    ) -> tuple[str, datetime]:
        ttl_seconds = settings.DAILY_TOKEN_TTL_SECONDS or int(self.DEFAULT_TOKEN_TTL.total_seconds())

        if self._daily_client:
            meeting_token: DailyMeetingToken = self._daily_client.create_meeting_token(
                room_name=room_name,
                user_id=str(session_id),
                user_name=user_name or user_email,
                ttl_seconds=ttl_seconds,
                is_owner=True,
                start_cloud_recording=settings.DAILY_START_CLOUD_RECORDING,
            )
            return meeting_token.token, meeting_token.expires_at

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        token = secrets.token_urlsafe(32)
        return token, expires_at

    def build_room_url(self, room_name: str) -> Optional[str]:
        if not self._daily_client:
            return None
        return self._daily_client.build_room_url(room_name)

    def recording_download_url(self, recording_id: str) -> Optional[str]:
        """Return a signed URL for downloading a Daily recording."""
        if not self._daily_client:
            return None
        try:
            payload = self._daily_client.get_recording_access_link(recording_id)
        except DailyAPIError as exc:
            logger.warning(
                "Failed to fetch Daily recording access link",
                extra={"recording_id": recording_id, "error": str(exc)},
            )
            return None

        download = payload.get("download_link")
        if not download:
            logger.warning(
                "Daily recording access link missing download URL",
                extra={"recording_id": recording_id},
            )
            return None
        return download

    def provider_domain(self) -> Optional[str]:
        if not self._daily_client:
            return None
        return self._daily_client.room_domain
