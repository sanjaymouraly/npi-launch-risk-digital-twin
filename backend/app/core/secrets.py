"""Symmetric encryption for provider credentials at rest."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256((settings.secret_key + ":ai-secrets").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mask_secret(value: str | None) -> str | None:
    """Return a display-safe hint (never the full key)."""
    if not value:
        return None
    if len(value) <= 8:
        return "••••"
    return f"{value[:3]}…{value[-4:]}"
