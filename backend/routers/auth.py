from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.database import db
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


# --- Schemas ---

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    full_name: str
    locale: Locale
    last_login: datetime | None = None


# --- Endpoints ---

@router.post("/login", response_model=TokenResponse)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with email + password, return JWT."""
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
    token = create_access_token(user_id=user_id, role=user_doc["role"])

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
        access_token=token,
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
