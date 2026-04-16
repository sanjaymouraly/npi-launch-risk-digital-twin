"""Authentication and user administration."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AuthError, ForbiddenError, ValidationError
from app.core.security import CurrentUser, create_access_token, hash_password, verify_password
from app.db.base import DbSession
from app.models import User
from app.schemas.api import LoginRequest

router = APIRouter()


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "roles": list(user.roles or []),
        "is_active": user.is_active,
    }


@router.post("/login")
def login(payload: LoginRequest, db: DbSession) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise AuthError("Invalid email or password")
    token = create_access_token(
        subject=user.id,
        email=user.email,
        roles=user.roles or ["viewer"],
        projects=["*"],
    )
    return {"access_token": token, "token_type": "bearer", "user": _user_payload(user)}


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "roles": user.roles,
        "projects": user.projects,
        "auth_enabled": settings.auth_enabled,
    }


@router.get("/users")
def list_users(user: CurrentUser, db: DbSession) -> list[dict]:
    if not user.is_admin:
        raise ForbiddenError("Administrator role required")
    users = list(db.scalars(select(User).order_by(User.created_at)))
    return [_user_payload(u) for u in users]


@router.post("/users")
def create_user(
    payload: dict,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    if not user.is_admin:
        raise ForbiddenError("Administrator role required")
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or "@" not in email:
        raise ValidationError("A valid email is required")
    if len(password) < 10:
        raise ValidationError("Password must be at least 10 characters")
    if db.scalar(select(User).where(User.email == email)):
        raise ValidationError("Email already registered")
    record = User(
        email=email,
        display_name=payload.get("display_name") or email.split("@")[0],
        password_hash=hash_password(password),
        roles=list(payload.get("roles") or ["viewer"]),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _user_payload(record)
