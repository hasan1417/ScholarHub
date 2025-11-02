from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.services.transcriber import TranscriptionError, get_transcriber_service

router = APIRouter()


@router.post("/transcription", summary="Submit audio for transcription")
async def submit_transcription(
    file: UploadFile = File(...),
    language: str | None = None,
    current_user: User = Depends(get_current_user),
):
    if not settings.TRANSCRIBER_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Transcription service disabled")
    base_url = settings.TRANSCRIBER_BASE_URL
    if not base_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transcriber configuration missing")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio payload")

    service = get_transcriber_service(base_url)
    try:
        result = await service.transcribe_audio(
            data=audio_bytes,
            filename=file.filename or "audio.wav",
            content_type=file.content_type,
            language=language,
        )
    except TranscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "user_id": str(current_user.id),
        "transcript": result.get("text", ""),
        "metadata": result,
    }
