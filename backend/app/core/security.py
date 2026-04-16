"""Authentication, authorisation and project-scoped access control."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Iterable

from fastapi import Depends, Header
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import AuthError, ForbiddenError

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except Exception:
        return False


def create_access_token(subject: str, roles: Iterable[str], projects: Iterable[str] = ("*",),
                        expires_minutes: int | None = None, email: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "email": email or "",
        "roles": list(roles),
        "projects": list(projects),
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=expires_minutes or settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


class Principal:
    """Authenticated caller. In demo mode this is a local admin."""

    __slots__ = ("id", "email", "roles", "projects")

    def __init__(self, id: str, email: str, roles: list[str], projects: list[str]):
        self.id = id
        self.email = email
        self.roles = roles
        self.projects = projects

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def can_write(self) -> bool:
        return self.is_admin or bool({"program_manager", "engineer"} & set(self.roles))

    def can_access(self, project_id: str) -> bool:
        return self.is_admin or "*" in self.projects or project_id in self.projects

    def require_write(self) -> None:
        if not self.can_write():
            raise ForbiddenError("Your role is read-only for this workspace")

    def require_project(self, project_id: str) -> None:
        if not self.can_access(project_id):
            raise ForbiddenError("No access to this project")


DEMO_PRINCIPAL = Principal(
    id="demo-user", email="demo@npi.local", roles=["admin", "program_manager", "viewer"], projects=["*"]
)


async def get_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not settings.auth_enabled:
        return DEMO_PRINCIPAL
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthError("Invalid or expired token") from exc
    return Principal(
        id=str(payload.get("sub", "unknown")),
        email=str(payload.get("email", "")),
        roles=list(payload.get("roles", ["viewer"])),
        projects=list(payload.get("projects", ["*"])),
    )


CurrentUser = Annotated[Principal, Depends(get_principal)]


def require_write(user: CurrentUser) -> Principal:
    user.require_write()
    return user


WriterUser = Annotated[Principal, Depends(require_write)]
