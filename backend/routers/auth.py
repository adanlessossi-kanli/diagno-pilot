from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.database import db
from backend.core.rate_limit import limiter
from backend.models.common import Locale, UserRole
from backend.services.audit_service import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Security helpers ---

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


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


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except InvalidTokenError:
        raise credentials_exc

    database = db.get_db()
    from bson import ObjectId

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise credentials_exc

    user_doc = await database["users"].find_one({"_id": oid})
    if user_doc is None:
        raise credentials_exc

    return user_doc


async def ensure_refresh_token_indexes() -> None:
    """Create required indexes on the refresh_tokens collection (idempotent)."""
    database = db.get_db()
    col = database["refresh_tokens"]
    # Unique index on token field
    await col.create_index("token", unique=True)
    # TTL index on expires_at (MongoDB auto-deletes documents after expiry)
    await col.create_index("expires_at", expireAfterSeconds=0)


# --- Schemas ---

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    full_name: str
    locale: Locale
    last_login: datetime | None = None


# --- Endpoints ---

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with email + password, return JWT access token + opaque refresh token."""
    database = db.get_db()
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
    await database["refresh_tokens"].insert_one({
        "token": refresh_token_value,
        "user_id": user_id,
        "expires_at": expires_at,
        "revoked": False,
    })

    # Update last_login
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

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """
    Validate a refresh token, rotate it (invalidate old, issue new),
    and return a new JWT access token + new refresh token.

    Returns HTTP 401 with "refresh_token_invalid" if token is expired or revoked.
    """
    database = db.get_db()
    now = datetime.now(timezone.utc)

    token_doc = await database["refresh_tokens"].find_one({"token": body.refresh_token})

    if (
        token_doc is None
        or token_doc.get("revoked", True)
        or token_doc["expires_at"].replace(tzinfo=timezone.utc) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh_token_invalid",
        )

    # Revoke the old token (rotation)
    await database["refresh_tokens"].update_one(
        {"token": body.refresh_token},
        {"$set": {"revoked": True}},
    )

    # Issue new tokens
    user_id = token_doc["user_id"]
    from bson import ObjectId
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh_token_invalid",
        )

    user_doc = await database["users"].find_one({"_id": oid})
    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh_token_invalid",
        )

    new_access_token = create_access_token(user_id=user_id, role=user_doc["role"])
    new_refresh_token_value = create_refresh_token()
    new_expires_at = now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)

    await database["refresh_tokens"].insert_one({
        "token": new_refresh_token_value,
        "user_id": user_id,
        "expires_at": new_expires_at,
        "revoked": False,
    })

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token_value,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, current_user: dict = Depends(get_current_user)):
    """Invalidate session (stateless — client discards the token)."""
    ip = request.client.host if request.client else None
    await audit_service.log_action(
        user_id=str(current_user["_id"]),
        action="logout",
        resource="auth",
        ip_address=ip,
    )
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
