from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.database import get_db
from app.core.security import verify_token
from app.models.user import User

# HTTP Bearer token scheme — auto_error=False so we can fall back to cookie-based
# auth deterministically (used by browser clients that cannot set the Authorization
# header, e.g. EventSource / SSE streams).
security = HTTPBearer(auto_error=False)


def _extract_access_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """Resolve the access token with explicit Bearer-over-cookie precedence."""
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie_name = settings.ACCESS_TOKEN_COOKIE_NAME
    cookie_token = request.cookies.get(cookie_name)
    if cookie_token:
        return cookie_token
    return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token.

    Precedence:
      1. Authorization: Bearer <token> header (primary — used by the SPA)
      2. access_token cookie (fallback — for SSE/EventSource or iframe embeds)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_access_token(request, credentials)
    if not token:
        raise credentials_exception

    email = verify_token(token)
    if email is None:
        raise credentials_exception

    try:
        user = db.query(User).filter(User.email == email).first()
    except SQLAlchemyError:
        # Surface a clearer error if the DB is not reachable instead of a generic 500
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while validating credentials"
        )

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


def get_current_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Get current user and require email verification.
    Used for sensitive operations like creating projects, inviting members, AI features.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email to access this feature."
        )
    return current_user
