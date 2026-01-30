from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, UploadFile, File
import uuid
import os
import aiofiles
import httpx
import logging
from pydantic import EmailStr
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User as UserModel
from app.schemas.user import UserUpdate, UserResponse
from app.core.security import get_password_hash, verify_password
from app.core.encryption import decrypt_openrouter_key, encrypt_openrouter_key, mask_openrouter_key
from app.services.subscription_service import SubscriptionService
from typing import List
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Avatar upload directory
AVATAR_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "avatars")
os.makedirs(AVATAR_UPLOAD_DIR, exist_ok=True)

router = APIRouter()

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: UserModel = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user information"""
    update_data = user_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    db.commit()
    db.refresh(current_user)
    return current_user

@router.post("/change-password")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Validate new password
    if len(password_data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )
    
    # Hash and update new password
    current_user.password_hash = get_password_hash(password_data.new_password)
    current_user.refresh_token = None
    current_user.refresh_token_expires_at = None
    db.commit()

    return {"message": "Password changed successfully"}

@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload user avatar image"""
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed: JPEG, PNG, GIF, WebP"
        )

    # Validate file size (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 5MB"
        )

    # Generate unique filename
    file_ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    file_path = os.path.join(AVATAR_UPLOAD_DIR, filename)

    # Delete old avatar if exists
    if current_user.avatar_url:
        old_filename = current_user.avatar_url.split("/")[-1]
        old_path = os.path.join(AVATAR_UPLOAD_DIR, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    # Save new avatar
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(contents)

    # Update user avatar URL
    current_user.avatar_url = f"/uploads/avatars/{filename}"
    db.commit()
    db.refresh(current_user)

    return current_user

@router.delete("/me/avatar", response_model=UserResponse)
async def delete_avatar(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete user avatar"""
    if current_user.avatar_url:
        filename = current_user.avatar_url.split("/")[-1]
        file_path = os.path.join(AVATAR_UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        current_user.avatar_url = None
        db.commit()
        db.refresh(current_user)

    return current_user

@router.get("/users/lookup-by-email")
async def lookup_user(
    email: EmailStr = Query(..., description="Email to look up"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lookup a user by email (for invitations). Returns minimal info or 404 if not found."""
    user = db.query(UserModel).filter(UserModel.email == str(email)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name
    }

@router.get("/users", response_model=List[UserResponse])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve users."""
    users = db.query(UserModel).offset(skip).limit(limit).all()
    return users

@router.get("/users/{user_id}", response_model=UserResponse)
async def read_user(
    user_id: uuid.UUID,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific user by ID."""
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    user_update: UserUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a user."""
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


# ========== API Keys Management ==========

class OpenRouterKeyRequest(BaseModel):
    api_key: str | None = None  # None to clear the key


async def validate_openrouter_key(api_key: str) -> tuple[bool, str]:
    """
    Validate an OpenRouter API key by making a test API call.
    Returns (is_valid, error_message).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test the key by fetching available models (lightweight call)
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://scholarhub.space",
                    "X-Title": "ScholarHub API Key Validation"
                }
            )

            if response.status_code == 200:
                return True, ""
            elif response.status_code == 401:
                return False, "Invalid API key. Please check your key and try again."
            elif response.status_code == 403:
                return False, "API key is not authorized. Please check your OpenRouter account."
            else:
                return False, f"OpenRouter returned error: {response.status_code}"

    except httpx.TimeoutException:
        return False, "Timeout connecting to OpenRouter. Please try again."
    except httpx.RequestError as e:
        logger.error(f"Error validating OpenRouter key: {e}")
        return False, "Failed to connect to OpenRouter. Please try again later."


@router.get("/me/api-keys")
async def get_api_keys(
    current_user: UserModel = Depends(get_current_user),
):
    """Get user's API key status (not the actual keys for security)."""
    masked_key = None
    if current_user.openrouter_api_key:
        try:
            decrypted = decrypt_openrouter_key(current_user.openrouter_api_key)
            masked_key = mask_openrouter_key(decrypted)
        except ValueError:
            logger.error("Failed to decrypt stored OpenRouter API key for user %s", current_user.id)
            masked_key = None
    return {
        "openrouter": {
            "configured": bool(current_user.openrouter_api_key),
            # Return masked key if present (last 4 chars)
            "masked_key": masked_key,
        }
    }


@router.put("/me/api-keys/openrouter")
async def set_openrouter_key(
    request: OpenRouterKeyRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Set or clear the user's OpenRouter API key.

    When an API key is set:
    1. The key is validated by making a test API call to OpenRouter
    2. If valid, the user is automatically assigned to the BYOK tier
       which gives unlimited AI usage (since they're paying for their own API)

    When the key is removed, they're reverted to their previous tier.
    """
    if request.api_key:
        # Basic format validation - OpenRouter keys start with sk-or-
        if not request.api_key.startswith("sk-or-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OpenRouter API key format. Keys should start with 'sk-or-'"
            )

        # Validate the key by testing it against OpenRouter API
        is_valid, error_message = await validate_openrouter_key(request.api_key)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )

        # Key is valid - save it encrypted
        current_user.openrouter_api_key = encrypt_openrouter_key(request.api_key)

        # Auto-assign BYOK tier
        subscription = SubscriptionService.assign_byok_tier(db, current_user.id)
        tier_message = f"You've been upgraded to the BYOK tier with unlimited AI usage."
    else:
        current_user.openrouter_api_key = None

        # Revert to previous tier
        subscription = SubscriptionService.remove_byok_tier(db, current_user.id)
        tier_message = f"Reverted to '{subscription.tier_id}' tier."

    db.commit()

    return {
        "message": f"OpenRouter API key updated successfully. {tier_message}",
        "configured": bool(current_user.openrouter_api_key),
        "tier": subscription.tier_id,
    }
