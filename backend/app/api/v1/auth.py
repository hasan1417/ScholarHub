from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from typing import Optional
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from authlib.integrations.starlette_client import OAuth
from app.database import get_db
from app.models.user import User
from app.models.pending_invitation import PendingInvitation
from app.models.project_member import ProjectMember
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
    create_email_verification_token,
    verify_email_verification_token,
    create_password_reset_token,
    verify_password_reset_token,
    generate_oauth_state,
)
from app.services.email_service import (
    send_verification_email,
    send_password_reset_email,
    send_welcome_email,
)
from app.api.deps import get_current_active_user
from app.core.config import settings
from datetime import timedelta, datetime, timezone
import logging

from app.core.rate_limiter import limiter

logger = logging.getLogger(__name__)

# OAuth configuration
oauth = OAuth()
if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )


# Request/Response schemas for new endpoints
class EmailVerificationRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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

class RegisterResponse(BaseModel):
    """Registration response with optional dev verification URL."""
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_verified: bool = False
    message: str = "Please check your email to verify your account"
    dev_verification_url: Optional[str] = None  # Only in development
    pending_project_invites: int = 0  # Number of project invitations awaiting acceptance


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user and send verification email."""
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

    # Generate email verification token
    verification_token = create_email_verification_token(user_data.email)

    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        auth_provider="local",
        email_verification_token=verification_token,
        email_verification_sent_at=datetime.now(timezone.utc),
    )

    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Process pending invitations - convert to ProjectMember invitations
    pending_invite_count = 0
    try:
        pending_invitations = (
            db.query(PendingInvitation)
            .filter(PendingInvitation.email == user_data.email.lower())
            .all()
        )

        for invitation in pending_invitations:
            # Create ProjectMember entry with "invited" status - user must accept
            membership = ProjectMember(
                project_id=invitation.project_id,
                user_id=db_user.id,
                role=invitation.role,
                status="invited",  # User must explicitly accept the invitation
                invited_by=invitation.invited_by,
            )
            db.add(membership)
            # Delete the pending invitation (now converted to ProjectMember)
            db.delete(invitation)

        if pending_invitations:
            db.commit()
            pending_invite_count = len(pending_invitations)
            logger.info(f"Converted {pending_invite_count} pending invitation(s) for {db_user.email}")
    except Exception as e:
        logger.error(f"Failed to process pending invitations for {db_user.email}: {e}")
        # Don't fail registration if invitation processing fails

    # Send verification email (non-blocking - don't fail registration if email fails)
    try:
        send_verification_email(
            to=db_user.email,
            token=verification_token,
            name=db_user.first_name
        )
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")

    # Build response
    return {
        "id": str(db_user.id),
        "email": db_user.email,
        "first_name": db_user.first_name,
        "last_name": db_user.last_name,
        "is_verified": db_user.is_verified,
        "message": "Please check your email to verify your account",
        "pending_project_invites": pending_invite_count,
    }

@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
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

class ExtensionTokenRequest(BaseModel):
    email: EmailStr
    password: str


class ExtensionTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user_email: str
    user_name: str


@router.post("/extension-token", response_model=ExtensionTokenResponse)
@limiter.limit("5/minute")
async def create_extension_token(
    request: Request,
    payload: ExtensionTokenRequest,
    db: Session = Depends(get_db),
):
    """
    Issue a long-lived JWT for the browser extension.

    Accepts email + password and returns a 7-day access token.
    This avoids cookie-based auth which does not work in extensions.
    """
    try:
        user = db.query(User).filter(User.email == payload.email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    expires = timedelta(days=7)
    token = create_access_token(data={"sub": user.email}, expires_delta=expires)

    name_parts = [user.first_name or "", user.last_name or ""]
    display_name = " ".join(p for p in name_parts if p) or user.email

    return ExtensionTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(expires.total_seconds()),
        user_email=user.email,
        user_name=display_name,
    )


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
@limiter.limit("3/minute")
async def request_password_reset(request: Request, payload: PasswordResetRequest, db: Session = Depends(get_db)):
    """
    Request a password reset email.
    Always returns success to avoid leaking which emails exist.
    """
    try:
        user = db.query(User).filter(User.email == payload.email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if user and user.auth_provider == "local":
        # Generate password reset token
        reset_token = create_password_reset_token(user.email)

        # Store token in database
        try:
            user.password_reset_token = reset_token
            user.password_reset_sent_at = datetime.now(timezone.utc)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.error(f"Failed to save password reset token for {payload.email}")

        # Send password reset email
        try:
            send_password_reset_email(
                to=user.email,
                token=reset_token,
                name=user.first_name
            )
        except Exception as e:
            logger.error(f"Failed to send password reset email: {e}")

    return {"message": "If an account exists for this email, reset instructions have been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using a valid reset token.
    """
    # Verify the token and get the email
    email = verify_password_reset_token(payload.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    try:
        user = db.query(User).filter(User.email == email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Verify the token matches what's stored (prevents token reuse)
    if user.password_reset_token != payload.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Update password
    try:
        user.password_hash = get_password_hash(payload.new_password)
        user.password_reset_token = None
        user.password_reset_sent_at = None
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {"message": "Password has been reset successfully"}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(payload: EmailVerificationRequest, db: Session = Depends(get_db)):
    """
    Verify email using a valid verification token.
    """
    # Verify the token and get the email
    email = verify_email_verification_token(payload.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )

    try:
        user = db.query(User).filter(User.email == email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )

    # Check if already verified
    if user.is_verified:
        return {"message": "Email already verified"}

    # Verify the token matches what's stored
    if user.email_verification_token != payload.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )

    # Mark user as verified
    try:
        user.is_verified = True
        user.email_verification_token = None
        user.email_verification_sent_at = None
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Send welcome email
    try:
        send_welcome_email(to=user.email, name=user.first_name)
    except Exception as e:
        logger.error(f"Failed to send welcome email: {e}")

    return {"message": "Email verified successfully"}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)):
    """
    Resend verification email.
    Always returns success to avoid leaking which emails exist.
    """
    try:
        user = db.query(User).filter(User.email == payload.email).first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if user and not user.is_verified and user.auth_provider == "local":
        # Generate new verification token
        verification_token = create_email_verification_token(user.email)

        # Store token in database
        try:
            user.email_verification_token = verification_token
            user.email_verification_sent_at = datetime.now(timezone.utc)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.error(f"Failed to save verification token for {payload.email}")

        # Send verification email
        try:
            send_verification_email(
                to=user.email,
                token=verification_token,
                name=user.first_name
            )
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")

    return {"message": "If an unverified account exists for this email, a verification link has been sent."}


# Google OAuth endpoints
@router.get("/google")
async def google_login(request: Request):
    """
    Initiate Google OAuth flow.
    Redirects the user to Google's consent page.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured"
        )

    # Generate state for CSRF protection
    state = generate_oauth_state()
    request.session["oauth_state"] = state

    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)


@router.get("/google/callback")
async def google_callback(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Handle Google OAuth callback.
    Creates or links user account, issues tokens, and redirects to frontend.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured"
        )

    try:
        # Get the token from Google
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=oauth_failed",
            status_code=status.HTTP_302_FOUND
        )

    # Get user info from Google
    user_info = token.get('userinfo')
    if not user_info:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=oauth_failed",
            status_code=status.HTTP_302_FOUND
        )

    google_id = user_info.get('sub')
    email = user_info.get('email')
    first_name = user_info.get('given_name', '')
    last_name = user_info.get('family_name', '')
    picture = user_info.get('picture', '')

    if not google_id or not email:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=oauth_failed",
            status_code=status.HTTP_302_FOUND
        )

    try:
        # Check if user exists by Google ID
        user = db.query(User).filter(User.google_id == google_id).first()

        if not user:
            # Check if user exists by email (linking existing account)
            user = db.query(User).filter(User.email == email).first()

            if user:
                # Link existing account to Google
                user.google_id = google_id
                if not user.avatar_url and picture:
                    user.avatar_url = picture
                # If local user signs in with Google, mark as verified
                user.is_verified = True
            else:
                # Create new user
                user = User(
                    email=email,
                    password_hash="",  # OAuth users don't have a password
                    first_name=first_name,
                    last_name=last_name,
                    avatar_url=picture,
                    google_id=google_id,
                    auth_provider="google",
                    is_verified=True,  # Google accounts are pre-verified
                    is_active=True,
                )
                db.add(user)

        db.commit()
        db.refresh(user)

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during OAuth: {e}")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=oauth_failed",
            status_code=status.HTTP_302_FOUND
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
        logger.error("Failed to save refresh token after OAuth")

    # Redirect to frontend with access token
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}"
    redirect_response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    # Set refresh token cookie on the redirect response
    set_refresh_cookie(redirect_response, refresh_token)

    return redirect_response
