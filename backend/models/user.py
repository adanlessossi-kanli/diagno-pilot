from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from .common import Locale, UserRole


class User(BaseModel):
    id: str | None = None
    email: EmailStr
    password_hash: str
    role: UserRole
    full_name: str
    locale: Locale = Locale.FR
    created_at: datetime
    last_login: datetime | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole
    full_name: str
    locale: Locale = Locale.FR
