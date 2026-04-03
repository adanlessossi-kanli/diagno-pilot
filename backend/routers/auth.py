from datetime import datetime, timedelta, timezone
import secrets
import uuid

import bcrypt
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.database import db
from backend.core.db_metrics import timed_db_op
from backend.core.rate_limit import limiter
from backend.core.auth import get_current_user
from backend.models.common import Locale, UserRole
from backend.services.audit_service import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Security helpers ---

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> str:
    """Generate an opaque UUID refresh token."""
    return str(uuid.uuid4())


async def ensure_refresh_token_indexes() -> None:
    """Create required indexes on the refresh_tokens collection (idempotent)."""
    database = db.get_db()
    col = database["refresh_tokens"]
    # Unique index on token field
    await col.create_index("token", unique=True)
    # TTL index on expires_at (MongoDB auto-deletes documents after expiry)
    await col.create_index("expires_at", expireAfterSeconds=0)


# --- Cookie helpers ---

def _generate_csrf_token() -> str:
    return secrets.token_hex(32)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str) -> None:
    secure = settings.ENV == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 86400,
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 86400,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.set_cookie(key="access_token", value="", httponly=True, samesite="strict", max_age=0)
    response.set_cookie(key="refresh_token", value="", httponly=True, samesite="strict", max_age=0)
    response.set_cookie(key="csrf_token", value="", httponly=False, samesite="strict", max_age=0)


# --- Schemas ---

class TokenResponse(BaseModel):
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    full_name: str
    locale: Locale
    last_login: datetime | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


# --- Endpoints ---

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, data: RegisterRequest):
    """Register a new user account with role='guest'. Email must be unique."""
    database = db.get_db()
    async with timed_db_op("users", "find_one"):
        existing = await database["users"].find_one({"email": data.email})
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    password_hash = hash_password(data.password)
    now = datetime.now(timezone.utc)
    doc = {
        "email": data.email,
        "password_hash": password_hash,
        "full_name": data.full_name,
        "role": UserRole.GUEST.value,
        "locale": Locale.FR.value,
        "is_active": True,
        "created_at": now,
    }
    async with timed_db_op("users", "insert_one"):
        result = await database["users"].insert_one(doc)
    return UserResponse(
        id=str(result.inserted_id),
        email=doc["email"],
        role=UserRole.GUEST,
        full_name=doc["full_name"],
        locale=Locale.FR,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with email + password, set auth cookies, return slim TokenResponse."""
    database = db.get_db()
    async with timed_db_op("users", "find_one"):
        user_doc = await database["users"].find_one({"email": form_data.username})
    ip = request.client.host if request.client else None

    if user_doc is None or not verify_password(form_data.password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user_doc["_id"])
    access_token = create_access_token(user_id=user_id, role=user_doc["role"])

    # Create and store refresh token
    refresh_token_value = create_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    async with timed_db_op("refresh_tokens", "insert_one"):
        await database["refresh_tokens"].insert_one({
            "token": refresh_token_value,
            "user_id": user_id,
            "expires_at": expires_at,
            "revoked": False,
        })

    # Update last_login
    async with timed_db_op("users", "update_one"):
        await database["users"].update_one(
            {"_id": user_doc["_id"]},
            {"$set": {"last_login": datetime.now(timezone.utc)}},
        )

    await audit_service.log_action(
        user_id=user_id,
        action="login",
        resource="auth",
        ip_address=ip,
    )

    csrf_token = _generate_csrf_token()
    _set_auth_cookies(response, access_token, refresh_token_value, csrf_token)

    return TokenResponse(
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response):
    """
    Validate a refresh token from cookie, rotate it (invalidate old, issue new),
    and set new auth cookies. Returns slim TokenResponse.

    Returns HTTP 401 with "refresh_token_invalid" if token is expired or revoked.
    """
    def _error_401() -> JSONResponse:
        err = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "refresh_token_invalid"},
        )
        _clear_auth_cookies(err)
        return err

    refresh_token_value = request.cookies.get("refresh_token")

    if not refresh_token_value:
        return _error_401()

    database = db.get_db()
    now = datetime.now(timezone.utc)

    async with timed_db_op("refresh_tokens", "find_one"):
        token_doc = await database["refresh_tokens"].find_one({"token": refresh_token_value})

    if (
        token_doc is None
        or token_doc.get("revoked", True)
        or token_doc["expires_at"].replace(tzinfo=timezone.utc) <= now
    ):
        return _error_401()

    # Revoke the old token (rotation)
    async with timed_db_op("refresh_tokens", "update_one"):
        await database["refresh_tokens"].update_one(
            {"token": refresh_token_value},
            {"$set": {"revoked": True}},
        )

    # Issue new tokens
    user_id = token_doc["user_id"]
    try:
        oid = ObjectId(user_id)
    except Exception:
        return _error_401()

    async with timed_db_op("users", "find_one"):
        user_doc = await database["users"].find_one({"_id": oid})
    if user_doc is None:
        return _error_401()

    new_access_token = create_access_token(user_id=user_id, role=user_doc["role"])
    new_refresh_token_value = create_refresh_token()
    new_expires_at = now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)

    async with timed_db_op("refresh_tokens", "insert_one"):
        await database["refresh_tokens"].insert_one({
            "token": new_refresh_token_value,
            "user_id": user_id,
            "expires_at": new_expires_at,
            "revoked": False,
        })

    new_csrf_token = _generate_csrf_token()
    _set_auth_cookies(response, new_access_token, new_refresh_token_value, new_csrf_token)

    return TokenResponse(
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
    """Invalidate session — clear all auth cookies."""
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=str(current_user["_id"]),
        action="logout",
        resource="auth",
        ip_address=ip,
    )
    _clear_auth_cookies(response)
    return {"detail": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    """Return current authenticated user info."""
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        role=current_user["role"],
        full_name=current_user["full_name"],
        locale=current_user.get("locale", Locale.FR),
        last_login=current_user.get("last_login"),
    )
