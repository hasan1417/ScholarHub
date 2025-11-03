"""Application-wide rate limiting utilities."""

from fastapi import FastAPI, Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_BACKEND],
)


def init_rate_limiter(app: FastAPI) -> None:
    """Attach the limiter and exception handler to a FastAPI app."""

    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:  # pragma: no cover - FastAPI handles wiring
        return Response("Too Many Requests", status_code=429)

