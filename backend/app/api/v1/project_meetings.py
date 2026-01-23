from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse, unquote
from uuid import UUID, uuid4

import aiofiles
import httpx
import io
from openai import OpenAI
from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Request, UploadFile, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.config import settings
from app.database import SessionLocal, get_db
from app.models import (
    Meeting,
    MeetingStatus,
    Project,
    ProjectRole,
    ProjectSyncMessage,
    ProjectSyncSession,
    SyncMessageRole,
    SyncSessionStatus,
    User,
)
from app.services.daily import DailyAPIError
from app.services.video import VideoService
from app.services.transcriber import get_transcriber_service
from app.services.activity_feed import record_project_activity, preview_text


router = APIRouter()
logger = logging.getLogger(__name__)


DEFAULT_MEETING_TITLE_PREFIX = "Sync Space"
LEGACY_SUMMARY_PLACEHOLDER = "Summary will appear here soon. (Preview)"
LEGACY_SUMMARY_PHRASES = {
    LEGACY_SUMMARY_PLACEHOLDER.strip().casefold(),
    "summary will appear here soon.".casefold(),
}


def _extract_transcript_text(transcript: Optional[dict | list | str]) -> Optional[str]:
    """Return a normalized transcript string from stored meeting transcript payloads."""

    if not transcript:
        return None

    if isinstance(transcript, str):
        return transcript.strip() or None

    if isinstance(transcript, dict):
        text = transcript.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

        segments = transcript.get("segments")
        if isinstance(segments, list):
            collected = []
            for segment in segments:
                if isinstance(segment, dict):
                    seg_text = segment.get("text")
                    if isinstance(seg_text, str) and seg_text.strip():
                        collected.append(seg_text.strip())
                elif isinstance(segment, str) and segment.strip():
                    collected.append(segment.strip())
            if collected:
                return "\n".join(collected)

        content = transcript.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    if isinstance(transcript, list):
        collected = []
        for item in transcript:
            if isinstance(item, str) and item.strip():
                collected.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    collected.append(text.strip())
        if collected:
            return "\n".join(collected)

    return None


def _default_meeting_summary(
    session: Optional[ProjectSyncSession],
    reference_dt: Optional[datetime] = None,
) -> str:
    """Generate a stable fallback summary for meeting transcripts."""

    cand_dates: list[Optional[datetime]] = []
    if session:
        cand_dates.append(session.ended_at)
        cand_dates.append(session.started_at)
    cand_dates.append(reference_dt)

    timestamp: Optional[datetime] = next((dt for dt in cand_dates if dt is not None), None)
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    date_str = timestamp.astimezone(timezone.utc).date().isoformat()
    return f"{DEFAULT_MEETING_TITLE_PREFIX} - {date_str}"


def _is_legacy_summary(value: Optional[str]) -> bool:
    if value is None:
        return False
    trimmed = value.strip()
    if not trimmed:
        return False
    return trimmed.casefold() in LEGACY_SUMMARY_PHRASES


def _normalize_summary(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed or _is_legacy_summary(trimmed):
        return None
    return trimmed


def _resolved_meeting_summary(
    meeting: Meeting,
) -> str:
    normalized = _normalize_summary(meeting.summary)
    if normalized:
        return normalized
    session = getattr(meeting, "session", None)
    return _default_meeting_summary(session, meeting.created_at)


def _ensure_recording_placeholder(
    db: Session,
    project: Project,
    session: ProjectSyncSession,
    current_user: User,
) -> Meeting:
    if session.recording:
        return session.recording

    placeholder = Meeting(
        project_id=project.id,
        created_by=current_user.id if current_user else None,
        status=MeetingStatus.TRANSCRIBING.value,
        summary=_default_meeting_summary(session),
        action_items={"items": []},
        transcript={},
        session_id=session.id,
    )
    db.add(placeholder)
    db.commit()
    db.refresh(placeholder)
    db.refresh(session)
    return placeholder
def _guard_feature() -> None:
    if not settings.PROJECT_MEETINGS_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meetings feature disabled")

def _update_meeting_transcription(
    meeting_id: UUID,
    status_value: str,
    transcript: Optional[dict] = None,
    summary: Optional[str] = None,
) -> None:
    with SessionLocal() as db:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            return
        meeting.status = status_value
        if transcript is not None:
            meeting.transcript = transcript
        if summary is not None:
            meeting.summary = summary
        meeting.updated_at = datetime.now(timezone.utc)
        db.commit()


async def _generate_meeting_summary(transcript_text: str) -> Optional[str]:
    """Generate a short descriptive title for the meeting from its transcript."""
    if not transcript_text or len(transcript_text.strip()) < 10:
        return None

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        return None

    try:
        client = OpenAI(api_key=api_key)
        loop = asyncio.get_running_loop()

        def _call_openai() -> str:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate very short meeting titles (3-6 words max). "
                            "Based on the transcript, create a concise title that captures "
                            "the main topic. Examples: 'Project Timeline Discussion', "
                            "'Bug Fix Planning', 'Weekly Sync', 'Feature Demo Review'. "
                            "Return ONLY the title, no quotes or punctuation."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Generate a short title for this meeting:\n\n{transcript_text[:1500]}",
                    },
                ],
                max_tokens=20,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip() if response.choices else None

        summary = await loop.run_in_executor(None, _call_openai)
        if summary:
            # Clean up the summary - remove quotes if present
            summary = summary.strip('"\'')
            # Limit length
            if len(summary) > 50:
                summary = summary[:47] + "..."
            logger.info("Generated meeting summary", extra={"summary": summary})
        return summary

    except Exception as exc:
        logger.warning("Failed to generate meeting summary", extra={"error": str(exc)})
        return None


def _cleanup_stuck_transcriptions(max_age_minutes: int = 10) -> int:
    """Mark transcriptions stuck for too long as failed.

    This handles cases where:
    - No recording was captured
    - Transcription failed silently
    - Backend restarted during transcription
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    cleaned = 0

    with SessionLocal() as db:
        stuck_meetings = (
            db.query(Meeting)
            .filter(
                Meeting.status == MeetingStatus.TRANSCRIBING.value,
                Meeting.created_at < cutoff,
            )
            .all()
        )

        for meeting in stuck_meetings:
            has_audio = bool(meeting.audio_url)
            if has_audio:
                # Had audio but transcription failed
                meeting.status = MeetingStatus.FAILED.value
                meeting.transcript = {"error": "Transcription timed out"}
            else:
                # No recording was captured
                meeting.status = MeetingStatus.FAILED.value
                meeting.transcript = {"error": "No recording was captured"}
            meeting.updated_at = datetime.now(timezone.utc)
            cleaned += 1

        if cleaned > 0:
            db.commit()
            logger.info(f"Cleaned up {cleaned} stuck transcriptions")

    return cleaned


async def _transcribe_meeting_audio(meeting_id: UUID, audio_url: str, base_url: str) -> None:
    try:
        local_path = _resolve_upload_file(audio_url)
        if local_path and local_path.exists():
            audio_bytes = await asyncio.to_thread(local_path.read_bytes)
            content_type = None
        else:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                audio_bytes = response.content
                content_type = response.headers.get('content-type')
    except Exception as exc:  # pragma: no cover - network
        logger.exception("Failed to download meeting audio", extra={"meeting_id": str(meeting_id), "audio_url": audio_url})
        _update_meeting_transcription(meeting_id, MeetingStatus.FAILED.value, transcript={"error": str(exc)})
        return

    try:
        transcript_payload = await _run_transcription(audio_bytes, audio_url, base_url, content_type)
        transcript_text = transcript_payload.get("text") if isinstance(transcript_payload, dict) else ""
        payload = {
            "text": transcript_text,
            "metadata": transcript_payload,
        }

        # Generate a summary title from the transcript
        summary = await _generate_meeting_summary(transcript_text)

        _update_meeting_transcription(
            meeting_id,
            MeetingStatus.COMPLETED.value,
            transcript=payload,
            summary=summary,
        )
        await _delete_daily_recording_for_meeting(meeting_id)
    except Exception as exc:  # pragma: no cover - external service
        logger.exception("Transcription job failed", extra={"meeting_id": str(meeting_id)})
        _update_meeting_transcription(meeting_id, MeetingStatus.FAILED.value, transcript={"error": str(exc)})


async def _run_transcription(
    audio_bytes: bytes,
    audio_url: str,
    base_url: str,
    content_type: Optional[str],
) -> dict[str, Any]:
    parsed_url = urlparse(audio_url)
    path_fragment = parsed_url.path.rsplit('/', 1)[-1] if parsed_url.path else ""
    filename = unquote(path_fragment or "") or "call-audio.mp4"
    if "." not in filename:
        filename = f"{filename}.mp4"

    if settings.USE_OPENAI_TRANSCRIBE and settings.OPENAI_API_KEY:
        return await _transcribe_with_openai(audio_bytes, filename)

    if settings.TRANSCRIBER_ENABLED and base_url:
        service = get_transcriber_service(base_url)
        return await service.transcribe_audio(
            data=audio_bytes,
            filename=filename,
            content_type=content_type,
        )

    raise RuntimeError("No transcription provider configured")


def _convert_fmp4_to_mp3(audio_bytes: bytes) -> bytes:
    """Convert fragmented MP4 (fMP4) to MP3 using ffmpeg.

    Daily.co outputs fragmented MP4 files which OpenAI's transcription API
    doesn't fully process. Converting to MP3 ensures the full audio is transcribed.
    """
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
        input_file.write(audio_bytes)
        input_path = input_file.name

    output_path = input_path.replace('.mp4', '.mp3')

    try:
        result = subprocess.run(
            [
                'ffmpeg', '-y', '-i', input_path,
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-ar', '16000',  # 16kHz sample rate (good for speech)
                '-ac', '1',  # Mono
                '-b:a', '64k',  # 64kbps bitrate
                output_path
            ],
            capture_output=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.warning(
                "ffmpeg conversion failed, using original file",
                extra={"stderr": result.stderr.decode()[:500] if result.stderr else ""},
            )
            return audio_bytes

        with open(output_path, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("ffmpeg not found, using original file")
        return audio_bytes
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg conversion timed out, using original file")
        return audio_bytes
    finally:
        # Clean up temp files
        import os
        try:
            os.unlink(input_path)
        except OSError:
            pass
        try:
            os.unlink(output_path)
        except OSError:
            pass


async def _transcribe_with_openai(audio_bytes: bytes, filename: str) -> dict[str, Any]:
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=api_key)
    loop = asyncio.get_running_loop()

    def _call_openai() -> dict[str, Any]:
        # Convert fMP4 to MP3 if the file is an MP4 (Daily recordings are fMP4)
        processed_bytes = audio_bytes
        output_filename = filename or "call-audio.mp4"

        if filename and filename.lower().endswith('.mp4'):
            logger.info("Converting fMP4 to MP3 for transcription", extra={"filename": filename})
            processed_bytes = _convert_fmp4_to_mp3(audio_bytes)
            output_filename = filename.replace('.mp4', '.mp3').replace('.MP4', '.mp3')

        buffer = io.BytesIO(processed_bytes)
        buffer.name = output_filename

        # Use diarization model for meetings to identify speakers
        model = settings.OPENAI_TRANSCRIBE_MODEL
        use_diarization = "diarize" in model.lower()

        # Build API parameters
        api_params: dict[str, Any] = {
            "model": model,
            "file": buffer,
            "language": "en",  # Default to English for better accuracy
        }

        # Diarization models require chunking_strategy
        if use_diarization:
            api_params["chunking_strategy"] = "auto"

        response = client.audio.transcriptions.create(**api_params)
        result = response.model_dump()
        result.setdefault("provider", "openai")
        result.setdefault("model", model)

        # Extract text - diarization model returns structured format with speaker labels
        if hasattr(response, 'text'):
            result.setdefault("text", response.text)
        else:
            result.setdefault("text", "")

        return result

    return await loop.run_in_executor(None, _call_openai)


class MeetingCreatePayload(BaseModel):
    audio_url: Optional[str] = None
    status: MeetingStatus = MeetingStatus.UPLOADED
    summary: Optional[str] = None
    action_items: Optional[dict] = None
    transcript: Optional[dict] = None
    session_id: Optional[UUID] = None


class MeetingUpdatePayload(BaseModel):
    status: Optional[MeetingStatus] = None
    summary: Optional[str] = None
    action_items: Optional[dict] = None
    transcript: Optional[dict] = None
    audio_url: Optional[str] = None
    session_id: Optional[UUID] = None


def _serialize(meeting: Meeting) -> dict:
    status_value = meeting.status.value if isinstance(meeting.status, MeetingStatus) else str(meeting.status)
    summary_value = _resolved_meeting_summary(meeting)
    return {
        "id": str(meeting.id),
        "project_id": str(meeting.project_id),
        "created_by": str(meeting.created_by) if meeting.created_by else None,
        "status": status_value,
        "audio_url": meeting.audio_url,
        "transcript": meeting.transcript,
        "summary": summary_value,
        "action_items": meeting.action_items,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
        "updated_at": meeting.updated_at.isoformat() if meeting.updated_at else None,
    }


class SyncSessionCreatePayload(BaseModel):
    provider: Optional[str] = "daily"
    provider_room_id: Optional[str] = None
    provider_payload: Optional[dict] = None
    status: SyncSessionStatus = SyncSessionStatus.LIVE


class SyncSessionEndPayload(BaseModel):
    status: SyncSessionStatus = SyncSessionStatus.ENDED
    provider_payload: Optional[dict] = None


class SyncMessageCreatePayload(BaseModel):
    content: str
    role: Optional[SyncMessageRole] = None
    is_command: bool = False
    command: Optional[str] = None
    metadata: Optional[dict] = None


class MeetingEndPayload(BaseModel):
    audio_url: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[dict] = None
    transcript: Optional[dict] = None


class SyncSessionTokenResponse(BaseModel):
    session_id: UUID
    token: str
    expires_at: datetime
    provider: str
    room_name: str
    room_url: Optional[str]
    domain: Optional[str]
    join_url: Optional[str] = None


class RecordingCallbackPayload(BaseModel):
    audio_url: str
    summary: Optional[str] = None
    action_items: Optional[dict] = None
    transcript: Optional[dict] = None


def _resolve_daily_base() -> tuple[Optional[str], Optional[str]]:
    configured = (settings.DAILY_ROOM_BASE_URL or settings.DAILY_DOMAIN or "").strip()
    if not configured:
        return None, None
    value = configured
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    domain = parsed.netloc or parsed.path
    scheme = parsed.scheme or "https"
    base_url = f"{scheme}://{domain}".rstrip("/")
    return base_url, domain


def _build_room_name(session: ProjectSyncSession, project_id: UUID) -> str:
    if session.provider_room_id:
        return session.provider_room_id
    prefix = (settings.SYNC_ROOM_PREFIX or "sync").strip() or "sync"
    return f"{prefix}-{project_id.hex[:6]}-{session.id.hex}"


def _build_room_url(provider: Optional[str], room_id: Optional[str]) -> Optional[str]:
    if not room_id:
        return None
    if provider == "daily":
        base_url, _ = _resolve_daily_base()
        if not base_url:
            return None
        return f"{base_url}/{room_id}"
    return None


def _build_join_url(provider: Optional[str], room_url: Optional[str], token: str) -> Optional[str]:
    if not room_url or not token:
        return room_url
    if provider == "daily":
        separator = '&' if '?' in room_url else '?'
        return f"{room_url}{separator}t={token}"
    return room_url


def _serialize_session(session: ProjectSyncSession) -> dict:
    status_value = session.status.value if isinstance(session.status, SyncSessionStatus) else session.status
    payload = {
        "id": str(session.id),
        "project_id": str(session.project_id),
        "started_by": str(session.started_by) if session.started_by else None,
        "status": status_value,
        "provider": session.provider,
        "provider_room_id": session.provider_room_id,
        "provider_payload": session.provider_payload,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }
    payload["room_url"] = _build_room_url(session.provider, session.provider_room_id) if status_value == SyncSessionStatus.LIVE.value else None
    if session.recording:
        payload["recording"] = _serialize(session.recording)
    else:
        payload["recording"] = None
    return payload


def _uploads_root() -> Path:
    uploads_dir = Path(settings.UPLOADS_DIR)
    if not uploads_dir.is_absolute():
        uploads_dir = Path(__file__).resolve().parent.parent.parent / settings.UPLOADS_DIR
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir.resolve()


def _resolve_upload_file(url: str) -> Optional[Path]:
    parsed = urlparse(url)
    path = parsed.path if parsed.scheme else url
    if not path.startswith('/uploads/'):
        return None
    relative = Path(path.lstrip('/'))
    base = Path(__file__).resolve().parent.parent.parent
    file_path = (base / relative).resolve()
    uploads_root = _uploads_root()
    if not str(file_path).startswith(str(uploads_root)):
        return None
    return file_path


def _serialize_message(message: ProjectSyncMessage) -> dict:
    return {
        "id": str(message.id),
        "session_id": str(message.session_id),
        "author_id": str(message.author_id) if message.author_id else None,
        "role": message.role.value,
        "content": message.content,
        "is_command": message.is_command,
        "command": message.command,
        "metadata": message.payload,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _require_sync_callback_token(
    legacy_token: Optional[str] = Header(None, alias="X-Jitsi-Token"),
    sync_token: Optional[str] = Header(None, alias="X-Sync-Token"),
) -> None:
    expected = settings.SYNC_CALLBACK_TOKEN
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sync callback token not configured",
        )
    token = sync_token or legacy_token
    if token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid callback token")


def _get_session_by_room(db: Session, room_name: str) -> Optional[ProjectSyncSession]:
    normalized = room_name.strip().lower()
    if not normalized:
        return None
    return (
        db.query(ProjectSyncSession)
        .filter(func.lower(ProjectSyncSession.provider_room_id) == normalized)
        .order_by(ProjectSyncSession.created_at.desc())
        .first()
    )


def _upsert_session_recording(
    db: Session,
    project: Project,
    session: ProjectSyncSession,
    created_by: Optional[UUID],
    payload: MeetingEndPayload,
    background_tasks: BackgroundTasks,
) -> Meeting:
    transcriber_ready = bool(settings.TRANSCRIBER_ENABLED and settings.TRANSCRIBER_BASE_URL)
    has_audio = bool(payload.audio_url)
    has_transcript = bool(payload.transcript)
    should_transcribe = transcriber_ready and has_audio and not has_transcript

    meeting = session.recording
    if meeting:
        if payload.audio_url is not None:
            meeting.audio_url = payload.audio_url
        incoming_summary = _normalize_summary(payload.summary)
        if incoming_summary is not None:
            meeting.summary = incoming_summary
        elif meeting.summary is None or _is_legacy_summary(meeting.summary):
            meeting.summary = _default_meeting_summary(session, meeting.created_at)
        if payload.action_items is not None:
            meeting.action_items = payload.action_items
        elif meeting.action_items is None:
            meeting.action_items = {"items": []}
        if payload.transcript is not None:
            meeting.transcript = payload.transcript
        elif should_transcribe:
            meeting.transcript = {}
        meeting.status = MeetingStatus.TRANSCRIBING.value if should_transcribe else MeetingStatus.COMPLETED.value
    else:
        meeting = Meeting(
            project_id=project.id,
            created_by=created_by,
            status=MeetingStatus.TRANSCRIBING.value if should_transcribe else MeetingStatus.COMPLETED.value,
            audio_url=payload.audio_url,
            summary=_normalize_summary(payload.summary) or _default_meeting_summary(session),
            action_items=payload.action_items or {"items": []},
            transcript=payload.transcript or ({} if should_transcribe else {}),
            session_id=session.id,
        )
        db.add(meeting)

    db.commit()
    db.refresh(meeting)
    db.refresh(session)

    if should_transcribe and payload.audio_url:
        background_tasks.add_task(
            _transcribe_meeting_audio,
            meeting.id,
            payload.audio_url,
            settings.TRANSCRIBER_BASE_URL,
        )

    return meeting


@router.post("/projects/{project_id}/meetings", status_code=status.HTTP_201_CREATED)
def create_meeting(
    project_id: str,
    body: MeetingCreatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    meeting = Meeting(
        project_id=project.id,
        created_by=current_user.id,
        status=body.status,
        audio_url=body.audio_url,
        summary=body.summary,
        action_items=body.action_items,
        transcript=body.transcript,
        session_id=body.session_id,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return _serialize(meeting)


@router.post("/projects/{project_id}/sync-sessions/{session_id}/token", response_model=SyncSessionTokenResponse)
def generate_sync_session_token(
    project_id: str,
    session_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    session = _get_session_for_project(db, project.id, session_id)

    if not session.provider_room_id:
        session.provider_room_id = _build_room_name(session, project.id)
        db.commit()
        db.refresh(session)

    status_value = session.status.value if isinstance(session.status, SyncSessionStatus) else session.status
    if status_value != SyncSessionStatus.LIVE.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sync session is not live")

    video_service = VideoService()
    room_name = session.provider_room_id or session.id.hex
    display_name = " ".join(filter(None, [current_user.first_name, current_user.last_name])) or current_user.email
    provider = (session.provider or video_service.provider_name).lower()

    if provider == "daily" and session.provider_room_id:
        try:
            video_service.ensure_room(room_name)
        except DailyAPIError as exc:
            logger.exception(
                "Failed to ensure Daily room",
                extra={"project_id": str(project.id), "session_id": str(session.id)},
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to prepare video room") from exc

    try:
        token, expires_at = video_service.create_token(
            session_id=session.id,
            room_name=room_name,
            user_name=display_name,
            user_email=current_user.email,
        )
    except DailyAPIError as exc:
        logger.exception(
            "Failed to mint Daily meeting token",
            extra={"project_id": str(project.id), "session_id": str(session.id)},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to issue meeting token") from exc

    if provider == "daily" and session.provider_room_id:
        background_tasks.add_task(video_service.ensure_recording_active, room_name, max_attempts=12, delay_seconds=5.0)

    room_url = _build_room_url(provider, room_name)
    domain = video_service.provider_domain()
    if not domain and room_url:
        parsed = urlparse(room_url)
        domain = parsed.netloc or parsed.path
    join_url = _build_join_url(provider, room_url, token)

    logger.info(
        "Issued sync session token",
        extra={
            "project_id": str(project.id),
            "session_id": str(session.id),
            "room_name": room_name,
            "room_url": room_url,
            "join_url": join_url,
        },
    )

    return SyncSessionTokenResponse(
        session_id=session.id,
        token=token,
        expires_at=expires_at,
        provider=provider,
        room_name=room_name,
        room_url=room_url,
        domain=domain,
        join_url=join_url,
    )


@router.get("/projects/{project_id}/meetings")
def list_meetings(
    project_id: str,
    status_filter: Optional[MeetingStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    query = db.query(Meeting).filter(Meeting.project_id == project.id)
    if status_filter:
        query = query.filter(Meeting.status == status_filter)

    meetings = query.order_by(Meeting.created_at.desc()).all()
    return {
        "project_id": str(project.id),
        "meetings": [_serialize(item) for item in meetings],
    }


@router.patch("/projects/{project_id}/meetings/{meeting_id}")
def update_meeting(
    project_id: str,
    meeting_id: UUID,
    body: MeetingUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    meeting = (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id, Meeting.project_id == project.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    update_data = body.dict(exclude_unset=True)
    if "status" in update_data and isinstance(update_data["status"], MeetingStatus):
        update_data["status"] = update_data["status"].value
    for key, value in update_data.items():
        setattr(meeting, key, value)

    db.commit()
    db.refresh(meeting)
    return _serialize(meeting)


@router.post("/projects/{project_id}/sync-sessions", status_code=status.HTTP_201_CREATED)
def create_sync_session(
    project_id: str,
    body: SyncSessionCreatePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    now = datetime.now(timezone.utc)
    status_enum = body.status if isinstance(body.status, SyncSessionStatus) else SyncSessionStatus(body.status)
    started_at = now if status_enum in {SyncSessionStatus.LIVE, SyncSessionStatus.ENDED} else None
    ended_at = now if status_enum == SyncSessionStatus.ENDED else None
    provider = (body.provider or "daily").lower()
    logger.info(
        "Creating sync session",
        extra={
            "project_id": str(project.id),
            "requested_provider": body.provider,
            "resolved_provider": provider,
        },
    )

    session = ProjectSyncSession(
        project_id=project.id,
        started_by=current_user.id,
        status=status_enum.value,
        provider=provider,
        provider_room_id=body.provider_room_id,
        provider_payload=body.provider_payload,
        started_at=started_at,
        ended_at=ended_at,
    )

    db.add(session)
    db.flush()
    if not session.provider_room_id:
        session.provider_room_id = _build_room_name(session, project.id)
    if not session.provider:
        session.provider = provider

    room_name = session.provider_room_id
    video_service = VideoService()
    if provider == "daily" and room_name:
        try:
            video_service.ensure_room(room_name)
        except DailyAPIError as exc:
            logger.exception(
                "Failed to prepare Daily room",
                extra={"project_id": str(project.id), "session_id": str(session.id)},
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to prepare video room") from exc
        else:
            background_tasks.add_task(video_service.ensure_recording_active, room_name, max_attempts=12, delay_seconds=5.0)

    status_value = status_enum.value
    event_type = {
        SyncSessionStatus.LIVE.value: "sync-session.started",
        SyncSessionStatus.ENDED.value: "sync-session.ended",
    }.get(status_value, "sync-session.created")
    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type=event_type,
        payload={
            "category": "sync-session",
            "action": event_type.split(".")[-1],
            "session_id": str(session.id),
            "status": status_value,
            "provider": session.provider,
            "provider_room_id": session.provider_room_id,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        },
    )

    db.commit()
    db.refresh(session)

    status_value = session.status.value if isinstance(session.status, SyncSessionStatus) else session.status
    if status_value == SyncSessionStatus.ENDED.value:
        placeholder = _ensure_recording_placeholder(db, project, session, current_user)
        db.refresh(session)

    return _serialize_session(session)


@router.get("/projects/{project_id}/sync-sessions")
def list_sync_sessions(
    project_id: str,
    status_filter: Optional[SyncSessionStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    # Clean up any stuck transcriptions (older than 10 minutes)
    _cleanup_stuck_transcriptions(max_age_minutes=10)

    query = db.query(ProjectSyncSession).filter(ProjectSyncSession.project_id == project.id)
    if status_filter:
        query = query.filter(ProjectSyncSession.status == status_filter)

    sessions = query.order_by(ProjectSyncSession.created_at.desc()).all()
    return {
        "project_id": str(project.id),
        "sessions": [_serialize_session(item) for item in sessions],
    }


@router.post("/projects/{project_id}/sync-sessions/{session_id}/end")
def end_sync_session(
    project_id: str,
    session_id: UUID,
    body: SyncSessionEndPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    session = (
        db.query(ProjectSyncSession)
        .filter(ProjectSyncSession.id == session_id, ProjectSyncSession.project_id == project.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync session not found")

    update_status = body.status if isinstance(body.status, SyncSessionStatus) else SyncSessionStatus(body.status)
    session.status = update_status.value
    if body.provider_payload is not None:
        session.provider_payload = body.provider_payload

    now = datetime.now(timezone.utc)
    if update_status in {SyncSessionStatus.LIVE, SyncSessionStatus.ENDED} and session.started_at is None:
        session.started_at = now
    if update_status in {SyncSessionStatus.ENDED, SyncSessionStatus.CANCELLED}:
        session.ended_at = now

    status_value = update_status.value
    duration_seconds: Optional[int] = None
    if session.started_at and session.ended_at:
        duration_seconds = int((session.ended_at - session.started_at).total_seconds())

    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type={
            SyncSessionStatus.ENDED.value: "sync-session.ended",
            SyncSessionStatus.CANCELLED.value: "sync-session.cancelled",
            SyncSessionStatus.LIVE.value: "sync-session.started",
        }.get(status_value, "sync-session.updated"),
        payload={
            "category": "sync-session",
            "action": {
                SyncSessionStatus.ENDED.value: "ended",
                SyncSessionStatus.CANCELLED.value: "cancelled",
                SyncSessionStatus.LIVE.value: "started",
            }.get(status_value, "updated"),
            "session_id": str(session.id),
            "status": status_value,
            "provider": session.provider,
            "provider_room_id": session.provider_room_id,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "duration_seconds": duration_seconds,
        },
    )

    db.commit()
    db.refresh(session)

    status_value = session.status.value if isinstance(session.status, SyncSessionStatus) else session.status
    if status_value == SyncSessionStatus.ENDED.value:
        _ensure_recording_placeholder(db, project, session, current_user)
        db.refresh(session)

    provider = (session.provider or "").lower()
    if provider == "daily" and session.provider_room_id:
        video_service = VideoService()
        video_service.stop_recording(session.provider_room_id)
        background_tasks.add_task(_poll_daily_recording, session.provider_room_id)
        video_service.delete_room(session.provider_room_id)

    return _serialize_session(session)


@router.delete("/projects/{project_id}/sync-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sync_session(
    project_id: str,
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    session = _get_session_for_project(db, project.id, session_id)
    status_value = session.status.value if isinstance(session.status, SyncSessionStatus) else session.status
    if status_value not in {SyncSessionStatus.ENDED.value, SyncSessionStatus.CANCELLED.value}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ended or cancelled sessions can be cleared",
        )

    if session.recording:
        db.delete(session.recording)

    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/integrations/daily/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def handle_daily_webhook(
    request: Request,
):
    _guard_feature()

    secret = settings.DAILY_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Daily webhook secret not configured",
        )

    raw_body = await request.body()

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc

    signature = request.headers.get("X-Daily-Signature")
    if signature:
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        received = signature.split("=", 1)[-1]
        if not hmac.compare_digest(expected, received):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook signature")
    else:
        logger.warning(
            "Daily webhook missing signature header; accepting unsigned payload",
            extra={"event": payload.get("event"), "user_agent": request.headers.get("user-agent")},
        )

    event_name = (payload.get("event") or payload.get("name") or "").lower()
    await _process_daily_event(event_name, payload)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_session_for_project(
    db: Session,
    project_id: str,
    session_id: UUID,
) -> ProjectSyncSession:
    session = (
        db.query(ProjectSyncSession)
        .filter(ProjectSyncSession.id == session_id, ProjectSyncSession.project_id == project_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync session not found")
    return session


def _flatten_transcript(transcript: Any) -> str:
    if not transcript:
        return ""
    if isinstance(transcript, str):
        return transcript
    if isinstance(transcript, list):
        parts: list[str] = []
        for item in transcript:
            if isinstance(item, dict) and 'text' in item and isinstance(item['text'], str):
                parts.append(item['text'])
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return '\n'.join(parts)
    if isinstance(transcript, dict):
        if isinstance(transcript.get('text'), str):
            return transcript['text']  # type: ignore[index]
        if isinstance(transcript.get('segments'), list):
            parts: list[str] = []
            for segment in transcript['segments']:
                text = segment.get('text') if isinstance(segment, dict) else None
                if isinstance(text, str):
                    parts.append(text)
            if parts:
                return '\n'.join(parts)
    try:
        return json.dumps(transcript, ensure_ascii=False)
    except Exception:
        return str(transcript)


@router.get("/projects/{project_id}/sync-sessions/{session_id}/messages")
def list_sync_messages(
    project_id: str,
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    session = _get_session_for_project(db, project.id, session_id)

    messages = (
        db.query(ProjectSyncMessage)
        .filter(ProjectSyncMessage.session_id == session.id)
        .order_by(ProjectSyncMessage.created_at.asc())
        .all()
    )
    return {
        "session": _serialize_session(session),
        "messages": [_serialize_message(message) for message in messages],
    }


@router.post("/projects/{project_id}/sync-sessions/{session_id}/messages", status_code=status.HTTP_201_CREATED)
def create_sync_message(
    project_id: str,
    session_id: UUID,
    body: SyncMessageCreatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    membership_record, effective_role = ensure_project_member(db, project, current_user)

    session = _get_session_for_project(db, project.id, session_id)

    role = body.role or SyncMessageRole.PARTICIPANT
    if role != SyncMessageRole.PARTICIPANT and effective_role not in {ProjectRole.ADMIN, ProjectRole.EDITOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for non-participant message")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message content cannot be empty")

    message = ProjectSyncMessage(
        session_id=session.id,
        author_id=current_user.id if role == SyncMessageRole.PARTICIPANT else None,
        role=role,
        content=content,
        is_command=body.is_command,
        command=body.command,
        payload=body.metadata,
    )

    db.add(message)
    db.commit()
    db.refresh(message)
    return _serialize_message(message)



@router.post("/projects/{project_id}/sync-sessions/{session_id}/recording", status_code=status.HTTP_201_CREATED)
def attach_recording(
    project_id: str,
    session_id: UUID,
    body: MeetingEndPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    session = _get_session_for_project(db, project.id, session_id)

    meeting = _upsert_session_recording(
        db,
        project,
        session,
        current_user.id,
        body,
        background_tasks,
    )

    return _serialize(meeting)


@router.post("/projects/{project_id}/sync-sessions/{session_id}/recording/upload", status_code=status.HTTP_201_CREATED)
async def upload_recording(
    project_id: str,
    session_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    session = _get_session_for_project(db, project.id, session_id)

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recording file is required")

    uploads_root = Path(settings.UPLOADS_DIR)
    if not uploads_root.is_absolute():
        uploads_root = Path(__file__).resolve().parent.parent.parent / settings.UPLOADS_DIR
    recordings_dir = uploads_root / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".webm"
    filename = f"sync-{session.id}-{uuid4().hex}{suffix}"
    destination = recordings_dir / filename

    async with aiofiles.open(destination, "wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            await output.write(chunk)

    public_url_base = settings.BACKEND_PUBLIC_URL.rstrip('/')
    audio_url = f"{public_url_base}/uploads/recordings/{filename}"

    payload = MeetingEndPayload(audio_url=audio_url)
    meeting = _upsert_session_recording(
        db,
        project,
        session,
        current_user.id,
        payload,
        background_tasks,
    )

    return _serialize(meeting)


@router.post(
    "/projects/{project_id}/sync-sessions/{session_id}/recording/callback",
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/projects/{project_id}/sync-sessions/{session_id}/recording/jibri",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def ingest_recording_callback(
    project_id: str,
    session_id: UUID,
    body: RecordingCallbackPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(_require_sync_callback_token),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    session = _get_session_for_project(db, project.id, session_id)

    payload = MeetingEndPayload(
        audio_url=body.audio_url,
        summary=body.summary,
        action_items=body.action_items,
        transcript=body.transcript,
    )

    meeting = _upsert_session_recording(
        db,
        project,
        session,
        created_by=None,
        payload=payload,
        background_tasks=background_tasks,
    )

    return _serialize(meeting)


@router.get("/sync-sessions/by-room/{room_name}")
def get_sync_session_by_room(
    room_name: str,
    token_check: None = Depends(_require_sync_callback_token),
    db: Session = Depends(get_db),
):
    _guard_feature()
    session = _get_session_by_room(db, room_name)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync session not found")
    return {
        "project_id": str(session.project_id),
        "session": _serialize_session(session),
    }


@router.post(
    "/projects/{project_id}/sync-sessions/{session_id}/recording/callback/upload",
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/projects/{project_id}/sync-sessions/{session_id}/recording/jibri/upload",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def upload_recording_callback(
    project_id: str,
    session_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_sync_callback_token),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    session = _get_session_for_project(db, project.id, session_id)

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recording file is required")

    uploads_root = _uploads_root()
    recordings_dir = uploads_root / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".webm"
    filename = f"sync-{session.id}-{uuid4().hex}{suffix}"
    destination = recordings_dir / filename

    async with aiofiles.open(destination, "wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            await output.write(chunk)

    public_url = f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/uploads/recordings/{filename}"

    payload = MeetingEndPayload(audio_url=public_url)
    meeting = _upsert_session_recording(
        db,
        project,
        session,
        created_by=None,
        payload=payload,
        background_tasks=background_tasks,
    )

    return _serialize(meeting)


async def _process_daily_event(event_name: str, payload: dict) -> None:
    data = payload.get("data") or payload.get("payload") or {}

    recording_value = data.get("recording")
    if isinstance(recording_value, dict):
        recording_id = recording_value.get("id") or recording_value.get("recording_id")
    else:
        recording_id = None

    recording_id = recording_id or data.get("recording_id") or data.get("id")

    room_name = data.get("room_name")
    room_value = data.get("room")
    if not room_name and isinstance(room_value, dict):
        room_name = room_value.get("name") or room_value.get("room_name") or room_value.get("id")
    elif not room_name and isinstance(room_value, str):
        room_name = room_value

    download_url = data.get("download_link") or data.get("s3_url") or data.get("url")
    if not download_url and isinstance(recording_value, dict):
        download_url = recording_value.get("download_link") or recording_value.get("url")

    normalized = event_name.replace("_", ".").lower()
    normalized = normalized.replace("ready-to-download", "ready")
    normalized = normalized.replace("ready.to.download", "ready")

    logger.debug(
        "Received Daily webhook",
        extra={
            "event": event_name,
            "normalized": normalized,
            "payload_keys": list(data.keys()),
        },
    )

    if normalized in {"participant.joined", "participant-joined"}:
        if not room_name:
            logger.warning(
                "Participant webhook missing room name",
                extra={"event": event_name, "payload_keys": list(data.keys())},
            )
            return
        video_service = VideoService()
        await video_service.ensure_recording_active(room_name, max_attempts=12, delay_seconds=5.0)
        return

    if normalized not in {"recording.ready", "recording-completed"}:
        logger.info("Ignoring Daily webhook event", extra={"event": event_name})
        return

    if not download_url and recording_id:
        recording_data = await _fetch_daily_recording(recording_id)
        if recording_data:
            room_name = room_name or recording_data.get("room_name")
            download_url = _extract_recording_download_link(recording_data)

    if not room_name or not download_url:
        logger.warning(
            "Daily recording event missing required data",
            extra={
                "recording_id": recording_id,
                "room_name": room_name,
                "download_available": bool(download_url),
            },
        )
        return

    _store_daily_recording(room_name, download_url, recording_id)


async def _fetch_daily_recording(recording_id: str) -> Optional[dict]:
    api_key = settings.DAILY_API_KEY
    if not api_key:
        logger.warning("Daily API key missing; cannot fetch recording", extra={"recording_id": recording_id})
        return None

    url = f"{settings.DAILY_API_BASE_URL.rstrip('/')}/recordings/{recording_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code >= 400:
        logger.warning(
            "Failed to fetch Daily recording details",
            extra={"recording_id": recording_id, "status_code": response.status_code},
        )
        return None

    try:
        return response.json()
    except ValueError:
        logger.warning("Daily recording response not JSON", extra={"recording_id": recording_id})
        return None


def _extract_recording_download_link(recording: dict) -> Optional[str]:
    download_url = recording.get("download_link") or recording.get("s3_url")
    if download_url:
        return download_url

    files = recording.get("files") or []
    for file in files:
        candidate = file.get("download_link") or file.get("s3_url") or file.get("url")
        if candidate:
            return candidate

    playback = recording.get("playback") or {}
    return playback.get("download_link") or playback.get("hls")


def _store_daily_recording(room_name: str, download_url: str, recording_id: Optional[str]) -> None:
    video_service = VideoService()

    effective_download = download_url
    if not effective_download and recording_id:
        effective_download = video_service.recording_download_url(recording_id)

    if not effective_download:
        logger.warning(
            "Unable to resolve Daily recording download link",
            extra={
                "room_name": room_name,
                "recording_id": recording_id,
            },
        )
        return

    background = BackgroundTasks()
    with SessionLocal() as db:
        session = _get_session_by_room(db, room_name)
        if not session:
            logger.warning(
                "No sync session found for Daily recording",
                extra={"room_name": room_name, "recording_id": recording_id},
            )
            return

        project = db.query(Project).filter(Project.id == session.project_id).first()
        if not project:
            logger.warning(
                "Project missing for Daily recording",
                extra={"project_id": str(session.project_id), "room_name": room_name},
            )
            return

        meeting_payload = MeetingEndPayload(audio_url=effective_download)
        _upsert_session_recording(
            db,
            project,
            session,
            created_by=None,
            payload=meeting_payload,
            background_tasks=background,
        )

        session.provider_payload = session.provider_payload or {}
        session.provider_payload.update(
            {
                "recording_id": recording_id,
                "recording_url": download_url,
                "recording_ready_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        db.commit()

    for task in background.tasks:
        try:
            asyncio.run(task())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(task())
            finally:
                loop.close()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Background recording task failed", extra={"room_name": room_name})


async def _delete_daily_recording_for_meeting(meeting_id: UUID) -> None:
    video_service = VideoService()
    if video_service.provider_name != "daily":
        return

    recording_id: Optional[str] = None
    session_id: Optional[UUID] = None
    with SessionLocal() as db:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting or not meeting.session_id:
            return
        session = db.query(ProjectSyncSession).filter(ProjectSyncSession.id == meeting.session_id).first()
        if not session:
            return
        payload = session.provider_payload or {}
        recording_id = payload.get("recording_id")
        session_id = session.id

    if not recording_id:
        return

    delete_error: Optional[str] = None
    try:
        await asyncio.to_thread(video_service.delete_recording, recording_id)
    except Exception as exc:  # pragma: no cover - defensive
        delete_error = str(exc)
        logger.warning(
            "Failed to delete Daily recording",
            extra={
                "meeting_id": str(meeting_id),
                "recording_id": recording_id,
                "error": delete_error,
            },
        )

    with SessionLocal() as db:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if meeting:
            meeting.audio_url = None
            meeting.updated_at = datetime.now(timezone.utc)
        if session_id:
            session = db.query(ProjectSyncSession).filter(ProjectSyncSession.id == session_id).first()
            if session:
                payload = dict(session.provider_payload or {})
                payload.pop("recording_id", None)
                payload.pop("recording_url", None)
                payload["recording_deleted_at"] = datetime.now(timezone.utc).isoformat()
                if delete_error:
                    payload["recording_delete_error"] = delete_error
                else:
                    payload.pop("recording_delete_error", None)
                db.query(ProjectSyncSession).filter(ProjectSyncSession.id == session_id).update(
                    {"provider_payload": payload if payload else None}
                )
        db.commit()


def _poll_daily_recording(room_name: str, attempts: int = 12, delay_seconds: float = 10.0) -> None:
    video_service = VideoService()
    for attempt in range(1, attempts + 1):
        recording = video_service.fetch_recent_recording(room_name)
        if recording:
            download = _extract_recording_download_link(recording)
            if not download:
                recording_id = recording.get("id") if isinstance(recording, dict) else None
                if recording_id:
                    download = video_service.recording_download_url(recording_id)
            if download:
                _store_daily_recording(room_name, download, recording.get("id"))
                return
        time.sleep(delay_seconds)
    logger.warning(
        "Timed out waiting for Daily recording",
        extra={"room_name": room_name, "attempts": attempts},
    )
