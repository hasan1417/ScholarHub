"""Daily.co REST client helpers for Sync Space calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


class DailyAPIError(Exception):
    """Raised when Daily returns a non-success response."""

    def __init__(self, status_code: int, message: str, payload: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.message = message

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"DailyAPIError(status_code={self.status_code}, message={self.message})"


@dataclass
class DailyMeetingToken:
    token: str
    expires_at: datetime


class DailyClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_base_url: str,
        domain: Optional[str] = None,
        room_base_url: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.api_base_url = api_base_url.rstrip('/')

        resolved_base, resolved_domain = self._resolve_room_base(domain, room_base_url)
        self.room_base_url = resolved_base
        self.room_domain = resolved_domain

    @staticmethod
    def _resolve_room_base(domain: Optional[str], room_base_url: Optional[str]) -> tuple[str, str]:
        candidate = room_base_url or domain or ""
        if not candidate:
            return "", ""

        value = candidate.strip()
        if not value:
            return "", ""

        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"

        parsed = urlparse(value)
        host = parsed.netloc or parsed.path
        scheme = parsed.scheme or "https"
        base = f"{scheme}://{host}".rstrip('/')
        return base, host

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.api_base_url}/{path.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        timeout = kwargs.pop("timeout", self.timeout)

        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, headers=headers, **kwargs)

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:  # pragma: no cover - API returned plain text
                payload = {"error": response.text}
            message = payload.get("error") or payload.get("message") or response.text or "Daily API error"
            raise DailyAPIError(response.status_code, str(message), payload)

        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - unexpected payload
            raise DailyAPIError(response.status_code, "Unexpected Daily API response", {"detail": response.text}) from exc

    def get_room(self, room_name: str) -> dict[str, Any]:
        return self._request("GET", f"rooms/{room_name}")

    def ensure_room(
        self,
        room_name: str,
        *,
        ttl_seconds: Optional[int] = None,
        properties: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        try:
            return self.get_room(room_name)
        except DailyAPIError as error:
            if error.status_code != 404:
                raise

        payload: dict[str, Any] = {
            "name": room_name,
            "privacy": "private",
        }
        room_properties: dict[str, Any] = {}
        if ttl_seconds and ttl_seconds > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            room_properties["exp"] = int(expires_at.timestamp())
        if properties:
            room_properties.update(properties)
        if room_properties:
            payload["properties"] = room_properties

        return self._request("POST", "rooms", json=payload)

    def start_recording(
        self,
        room_name: str,
        *,
        recording_type: str = "cloud",
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": recording_type}
        if options:
            payload.update(options)
        return self._request("POST", f"rooms/{room_name}/recordings/start", json=payload)

    def stop_recording(self, room_name: str) -> dict[str, Any]:
        return self._request("POST", f"rooms/{room_name}/recordings/stop")

    def delete_room(self, room_name: str) -> dict[str, Any]:
        return self._request("DELETE", f"rooms/{room_name}")

    def list_webhooks(self) -> dict[str, Any]:
        return self._request("GET", "webhooks")

    def create_webhook(
        self,
        *,
        url: str,
        event_types: list[str],
        scope: str = "room",
        hmac_secret: Optional[str] = None,
    ) -> dict[str, Any]:
        base_payload: dict[str, Any] = {"url": url}
        optional_fields: dict[str, Any] = {}
        if scope:
            optional_fields["scope"] = scope
        if hmac_secret:
            optional_fields["hmac"] = hmac_secret
        base_payload.update(optional_fields)

        # Daily's API has shipped both snake_case and camelCase variants of the
        # event list. Try the modern schema first, then fall back when the server
        # explicitly rejects the key we supplied. Some accounts no longer accept
        # optional fields like `scope`/`hmac`; strip them when the API flags them.
        field_order = ["event_types", "eventTypes", "events"]
        last_error: Optional[DailyAPIError] = None

        active_fields = field_order[:]
        index = 0
        while index < len(active_fields):
            field_name = active_fields[index]
            payload = {**base_payload, field_name: event_types}
            try:
                return self._request("POST", "webhooks", json=payload)
            except DailyAPIError as exc:
                info_text = str(exc.payload.get("info") or exc.message or "").lower()
                # When the API refuses optional fields, drop them and retry the same
                # field name to avoid losing compatibility with older deployments.
                stripped = False
                if '"scope" is not allowed' in info_text and "scope" in base_payload:
                    base_payload.pop("scope", None)
                    stripped = True
                if '"hmac" is not allowed' in info_text and "hmac" in base_payload:
                    base_payload.pop("hmac", None)
                    stripped = True
                if '"hmac" must be a valid base64 string' in info_text and "hmac" in base_payload:
                    # Some Daily clusters only accept hex or managed secrets; fall back
                    # to an unsigned webhook when validation rejects the provided key.
                    base_payload.pop("hmac", None)
                    stripped = True
                if stripped:
                    last_error = exc
                    continue

                not_allowed = f'"{field_name}" is not allowed' in info_text
                unknown_property = "unknown property" in info_text and field_name.lower() in info_text
                if exc.status_code == 400 and (not_allowed or unknown_property):
                    last_error = exc
                    index += 1
                    continue
                raise

        if last_error is not None:
            raise last_error
        # Should be unreachable, but keep a predictable exception path just in case.
        raise DailyAPIError(500, "Unable to register Daily webhook", base_payload)

    def list_recordings(self, *, room_name: Optional[str] = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if room_name:
            params["room_name"] = room_name
        return self._request("GET", "recordings", params=params)

    def get_recording_access_link(self, recording_id: str) -> dict[str, Any]:
        """Return a short-lived download link for a recording."""
        return self._request("GET", f"recordings/{recording_id}/access-link")

    def delete_recording(self, recording_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"recordings/{recording_id}")

    def create_meeting_token(
        self,
        *,
        room_name: str,
        user_id: str,
        user_name: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        is_owner: bool = True,
    ) -> DailyMeetingToken:
        expires_at = None
        if ttl_seconds and ttl_seconds > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        properties: dict[str, Any] = {
            "room_name": room_name,
            "is_owner": is_owner,
            "user_id": user_id,
        }
        if user_name:
            properties["user_name"] = user_name
        if expires_at is not None:
            properties["exp"] = int(expires_at.timestamp())

        data = self._request("POST", "meeting-tokens", json={"properties": properties})
        token = data.get("token")
        if not token:
            raise DailyAPIError(500, "Daily meeting token missing from response", data)

        exp_ts = data.get("exp") or properties.get("exp")
        result_expires_at = expires_at
        if exp_ts:
            try:
                result_expires_at = datetime.fromtimestamp(int(exp_ts), tz=timezone.utc)
            except Exception:  # pragma: no cover - fallback to earlier calculation
                result_expires_at = expires_at

        if result_expires_at is None:
            result_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        return DailyMeetingToken(token=token, expires_at=result_expires_at)

    def build_room_url(self, room_name: str) -> Optional[str]:
        if not self.room_base_url:
            return None
        return f"{self.room_base_url}/{room_name}"
