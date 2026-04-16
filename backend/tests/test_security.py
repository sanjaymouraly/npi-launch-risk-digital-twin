"""Security primitives: hashing, tokens, project ACL and secret encryption."""
from __future__ import annotations

import pytest
from app.core.errors import ForbiddenError
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.core.security import Principal, create_access_token, hash_password, verify_password


def test_password_hashing_uses_argon2_and_salts():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first.startswith("$argon2")
    assert first != second  # salted
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong", first)


def test_access_token_round_trip():
    from app.core.config import settings
    from jose import jwt

    token = create_access_token(
        subject="user-1", email="user@example.com", roles=["viewer"], projects=["p1"]
    )
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    assert payload["sub"] == "user-1"
    assert payload["email"] == "user@example.com"
    assert payload["roles"] == ["viewer"]
    assert payload["projects"] == ["p1"]
    assert payload["exp"] > payload["iat"]


def test_principal_access_control():
    principal = Principal(id="u", email="u@example.com", roles=["viewer"], projects=["p1"])
    assert principal.can_access("p1")
    assert not principal.can_access("p2")
    assert not principal.can_write()
    with pytest.raises(ForbiddenError):
        principal.require_project("p2")

    admin = Principal(id="a", email="a@example.com", roles=["admin"], projects=[])
    assert admin.can_write()
    assert admin.can_access("anything")


def test_secret_encryption_is_reversible_and_masked():
    secret = "sk-super-secret-value"
    encrypted = encrypt_secret(secret)
    assert secret not in encrypted
    assert decrypt_secret(encrypted) == secret
    masked = mask_secret(secret)
    assert secret not in masked
    assert masked.startswith("sk-")
    assert "…" in masked
    assert len(masked) < len(secret)


def test_mask_secret_handles_none():
    assert mask_secret(None) in (None, "")


def test_logging_redacts_credentials():
    from app.core.logging import JsonFormatter, redact

    secret = "sk-leak-me-0123456789"
    assert secret not in redact(f"calling provider with {secret}")
    assert secret not in redact('{"api_key": "%s"}' % secret)
    assert "***REDACTED***" in redact(f"token {secret}")

    import logging

    record = logging.LogRecord(
        name="npi", level=logging.INFO, pathname=__file__, lineno=1,
        msg="provider call sk-leak-me-0123456789", args=None, exc_info=None,
    )
    payload = JsonFormatter().format(record)
    assert "sk-leak-me-0123456789" not in payload
    assert "REDACTED" in payload


def test_auth_disabled_uses_the_demo_principal(client, project_id):
    assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_auth_enabled_requires_a_token(client, project_id, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True)
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 401
    body = response.json()
    assert body["code"]
    assert "token" in body["message"].lower()


def test_login_flow(client, db, monkeypatch):
    from app.core.config import settings
    from app.models import User

    user = db.query(User).filter(User.email == "demo@npi.local").first()
    assert user is not None
    monkeypatch.setattr(settings, "auth_enabled", True)
    response = client.post(
        "/api/auth/login", json={"email": "demo@npi.local", "password": "npi-demo-2026!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "demo@npi.local"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "demo@npi.local"

    unauthorised = client.get(f"/api/projects/{user.id}/audit")
    assert unauthorised.status_code == 401  # auth is enabled for this test
