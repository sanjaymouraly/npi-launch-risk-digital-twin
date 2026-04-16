"""Grounded AI copilot endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import assistant, providers
from app.core.errors import NotFoundError
from app.core.security import CurrentUser, WriterUser
from app.db.base import DbSession
from app.models import AIConversation, AIMessage, Project
from app.schemas.api import ChatRequest

router = APIRouter()


def _project(db: Session, user, project_id: str) -> Project:  # noqa: ANN001
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    user.require_project(project.id)
    return project


@router.get("/projects/{project_id}/ai/status")
def ai_status(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    _project(db, user, project_id)
    cfg = providers.resolve(db, None)
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = float(
        db.scalar(
            select(func.coalesce(func.sum(AIMessage.cost_usd), 0.0)).where(
                AIMessage.provider == cfg.provider, AIMessage.created_at >= start
            )
        )
        or 0.0
    )
    return {
        "active_provider": cfg.provider,
        "model": cfg.model,
        "configured": cfg.configured,
        "offline_available": True,
        "monthly_budget_usd": cfg.monthly_budget_usd,
        "month_spend_usd": round(spent, 4),
        "budget_remaining_usd": round(max(0.0, cfg.monthly_budget_usd - spent), 4)
        if cfg.monthly_budget_usd > 0
        else None,
        "grounding": "Read-only project tools; answers cite simulation and schedule records.",
    }


@router.post("/projects/{project_id}/ai/chat")
async def chat(
    project_id: str,
    payload: ChatRequest,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    return await assistant.answer(
        db,
        project,
        payload.message,
        conversation_id=payload.conversation_id,
        provider_name=payload.provider,
        offline=payload.offline,
        actor=user.email,
    )


@router.get("/projects/{project_id}/ai/conversations")
def conversations(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[dict]:
    project = _project(db, user, project_id)
    return assistant.list_conversations(db, project.id, limit=limit)


@router.get("/projects/{project_id}/ai/conversations/{conversation_id}")
def conversation(
    project_id: str,
    conversation_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    return assistant.get_conversation(db, project.id, conversation_id)


@router.delete("/projects/{project_id}/ai/conversations/{conversation_id}")
def delete_conversation(
    project_id: str,
    conversation_id: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    row = db.get(AIConversation, conversation_id)
    if not row or row.project_id != project.id:
        raise NotFoundError("Conversation not found")
    db.delete(row)
    db.commit()
    return {"deleted": conversation_id}


@router.get("/projects/{project_id}/ai/suggestions")
def suggestions(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> list[str]:
    _project(db, user, project_id)
    return [
        "What is the probability we hit the launch deadline, and what drives it?",
        "Explain the difference between the critical path and the resource-constrained schedule.",
        "Which supplier poses the biggest risk to the launch?",
        "Which milestones are most at risk, and by how much?",
        "How should we spend the intervention budget to improve on-time probability?",
        "What does the P90 mean and how stable is the estimate?",
        "Summarise the top empirical risk drivers and whether they are causal.",
    ]
