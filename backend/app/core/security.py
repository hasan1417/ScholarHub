from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.core.config import settings
import secrets
import hashlib
import hmac
import uuid

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token with standard claims."""
    to_encode = data.copy()

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "iss": settings.PROJECT_NAME,
            "jti": uuid.uuid4().hex,
        }
    )

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token() -> str:
    """Create a secure refresh token."""
    return secrets.token_urlsafe(32)

def hash_refresh_token(token: str) -> str:
    """Derive a deterministic hash for storing refresh tokens server-side."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def verify_refresh_token(token: str, stored_hash: str) -> bool:
    """Constant-time comparison of a refresh token against the stored hash."""
    expected_hash = hash_refresh_token(token)
    return hmac.compare_digest(expected_hash, stored_hash)

def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return email."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        return email
    except JWTError:
        return None


# Email verification and password reset token functions
_email_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="email-verification")
_password_reset_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="password-reset")


def create_email_verification_token(email: str) -> str:
    """Create a URL-safe token for email verification."""
    return _email_serializer.dumps(email)


def verify_email_verification_token(token: str, max_age_hours: int = None) -> Optional[str]:
    """Verify email verification token and return the email if valid."""
    if max_age_hours is None:
        max_age_hours = settings.EMAIL_VERIFICATION_EXPIRE_HOURS
    max_age_seconds = max_age_hours * 3600
    try:
        email = _email_serializer.loads(token, max_age=max_age_seconds)
        return email
    except (BadSignature, SignatureExpired):
        return None


def create_password_reset_token(email: str) -> str:
    """Create a URL-safe token for password reset."""
    return _password_reset_serializer.dumps(email)


def verify_password_reset_token(token: str, max_age_hours: int = None) -> Optional[str]:
    """Verify password reset token and return the email if valid."""
    if max_age_hours is None:
        max_age_hours = settings.PASSWORD_RESET_EXPIRE_HOURS
    max_age_seconds = max_age_hours * 3600
    try:
        email = _password_reset_serializer.loads(token, max_age=max_age_seconds)
        return email
    except (BadSignature, SignatureExpired):
        return None


def generate_oauth_state() -> str:
    """Generate a secure random state for OAuth CSRF protection."""
    return secrets.token_urlsafe(32)
