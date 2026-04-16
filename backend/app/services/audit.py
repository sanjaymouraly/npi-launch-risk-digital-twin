"""Audit trail helpers."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    project_id: str | None,
    actor: str,
    action: str,
    entity_type: str = "",
    entity_id: str | None = None,
    summary: str = "",
    payload: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        project_id=project_id,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        payload=payload or {},
    )
    db.add(entry)
    return entry
