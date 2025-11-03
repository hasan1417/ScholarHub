from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    Token,
    User as UserSchema,
    UserInDB,
    UserLogin,
    RefreshTokenRequest,
    PasswordResetRequest,
)
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
)
from app.api.deps import get_current_active_user
from app.core.config import settings
from datetime import timedelta, datetime, timezone

from app.core.rate_limiter import limiter


ACCESS_COOKIE_NAME = settings.ACCESS_TOKEN_COOKIE_NAME
REFRESH_COOKIE_NAME = settings.REFRESH_TOKEN_COOKIE_NAME
COOKIE_DOMAIN = settings.COOKIE_DOMAIN
COOKIE_SECURE = not settings.DEBUG
COOKIE_SAMESITE = "lax"
REFRESH_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        domain=COOKIE_DOMAIN,
        path="/",
    )

router = APIRouter()

@router.post("/register", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
async def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if user already exists
    try:
        existing_user = db.query(User).filter(User.email == user_data.email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        first_name=user_data.first_name,
        last_name=user_data.last_name
    )
    
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    return db_user

@router.post("/login", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_BACKEND)
async def login(request: Request, login_data: UserLogin, response: Response, db: Session = Depends(get_db)):
    """Login user and return access token."""
    # Find user by email
    try:
        user = db.query(User).filter(User.email == login_data.email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # Create refresh token
    refresh_token = create_refresh_token()
    now = datetime.now(timezone.utc)
    refresh_token_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Store refresh token in database
    try:
        user.refresh_token = hash_refresh_token(refresh_token)
        user.refresh_token_expires_at = refresh_token_expires
        user.refresh_token_last_hash = None
        user.refresh_token_last_seen_at = now
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_data: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token stored in cookies (or request body for legacy clients)."""
    provided_token = None
    if refresh_data and refresh_data.refresh_token:
        provided_token = refresh_data.refresh_token
    else:
        provided_token = request.cookies.get(REFRESH_COOKIE_NAME)

    if not provided_token:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash = hash_refresh_token(provided_token)

    try:
        user = db.query(User).filter(User.refresh_token == token_hash).first()
        legacy_user = None
        if not user:
            legacy_user = db.query(User).filter(User.refresh_token == provided_token).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if not user and legacy_user:
        # Allow legacy plain-text tokens once and migrate to hashed
        user = legacy_user
        token_hash = hash_refresh_token(provided_token)
        user.refresh_token = token_hash
        db.commit()

    if not user:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(timezone.utc)

    # Reuse detection: if provided token matches the previous token hash, treat as compromise
    if user.refresh_token_last_hash and user.refresh_token_last_hash == token_hash:
        user.refresh_token = None
        user.refresh_token_expires_at = None
        user.refresh_token_last_hash = None
        user.refresh_token_last_seen_at = now
        db.commit()
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.refresh_token_expires_at < now:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    new_refresh_token = create_refresh_token()
    new_refresh_token_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    try:
        current_hash = hash_refresh_token(new_refresh_token)
        user.refresh_token_last_hash = user.refresh_token
        user.refresh_token_last_seen_at = now
        user.refresh_token = current_hash
        user.refresh_token_expires_at = new_refresh_token_expires
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")

    set_refresh_cookie(response, new_refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Invalidate the current refresh token and clear auth cookies."""
    try:
        current_user.refresh_token = None
        current_user.refresh_token_expires_at = None
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")

    clear_refresh_cookie(response)

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    """
    Accept a password reset request.
    This placeholder implementation always returns success to avoid leaking which emails exist.
    """
    try:
        _ = db.query(User).filter(User.email == payload.email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {"message": "If an account exists for this email, reset instructions have been sent."}
