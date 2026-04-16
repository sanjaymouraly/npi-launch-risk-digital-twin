"""AI provider configuration, connection testing and model discovery.

API keys are encrypted at rest, masked in responses and never logged.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.ai import providers
from app.core.security import CurrentUser, WriterUser
from app.db.base import DbSession
from app.schemas.api import ProviderPatch

router = APIRouter()


@router.get("/providers")
def list_providers(
    user: CurrentUser,
    db: DbSession,
) -> dict:
    return {
        "providers": providers.list_configs(db),
        "note": (
            "Keys are encrypted with a Fernet key derived from SECRET_KEY and are never returned. "
            "Set SECRET_KEY in production before storing provider credentials."
        ),
    }


@router.patch("/providers/{provider}")
def update_provider(
    provider: str,
    payload: ProviderPatch,
    user: WriterUser,
    db: DbSession,
) -> dict:
    return providers.update_config(db, provider, payload)


@router.post("/providers/{provider}/test")
async def test_provider(
    provider: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    cfg = providers.resolve(db, provider)
    return await providers.test_connection(cfg)


@router.get("/providers/{provider}/models")
async def provider_models(
    provider: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    cfg = providers.resolve(db, provider)
    try:
        models = await providers.list_models(cfg)
        return {"provider": provider, "models": models}
    except Exception as exc:  # noqa: BLE001
        return {"provider": provider, "models": [], "error": str(exc)[:300]}
