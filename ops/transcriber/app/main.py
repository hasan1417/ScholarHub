import logging
import os
import tempfile
import time
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

logger = logging.getLogger("transcriber")

app = FastAPI(title="ScholarHub Transcriber", version="0.1.0")

_model: Optional[WhisperModel] = None
_model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
_device = os.getenv("WHISPER_DEVICE", "cpu")
_compute_type = os.getenv("WHISPER_COMPUTE_TYPE")
_max_audio_seconds = int(os.getenv("MAX_AUDIO_SECONDS", "3600"))


def _load_model() -> WhisperModel:
    global _model
    if _model is None:
        compute_type = _compute_type
        if not compute_type:
            compute_type = "int8" if _device == "cpu" else "float16"
        logger.info(
            "Loading faster-whisper model", extra={"model_size": _model_size, "device": _device, "compute_type": compute_type}
        )
        _model = WhisperModel(
            _model_size,
            device=_device,
            compute_type=compute_type,
            local_files_only=False,
        )
    return _model


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse({"status": "ok", "model": _model_size})


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    task: str = "transcribe",
) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    if file.content_type:
        if not (file.content_type.startswith("audio") or file.content_type == "application/octet-stream"):
            raise HTTPException(status_code=400, detail="Unsupported content type; expected audio")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    max_bytes = _max_audio_seconds * 64000  # assuming 64kbps average after encoding
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio clip exceeds configured limit")

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    model = _load_model()

    forced_language = language or os.getenv("FORCE_TRANSCRIPT_LANG")
    language = forced_language or language

    started = time.time()
    try:
        segments, info = model.transcribe(
            tmp_path,
            language=language,
            task=task,
            beam_size=5,
            vad_filter=True,
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass

    response = {
        "text": transcript,
        "detected_language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "processing_seconds": time.time() - started,
        "model": _model_size,
        "device": _device,
    }
    return JSONResponse(response)
