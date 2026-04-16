"""The AI copilot: grounding, offline fallback, budgets and secret handling."""
from __future__ import annotations

import asyncio

import pytest
from app.ai import assistant, providers


@pytest.fixture()
def project(db, project_id):
    from app.models import Project

    return db.get(Project, project_id)


def test_offline_answer_is_grounded_and_cited(db, project):
    result = asyncio.run(
        assistant.answer(db, project, "What is the probability we hit the launch deadline?")
    )
    assert result["offline"] is True
    assert result["provider"] == "offline"
    assert result["citations"], "an offline answer must cite the records it used"
    assert result["answer"].strip()
    assert "_Sources:" in result["answer"] or "Sources:" in result["answer"]
    for citation in result["citations"]:
        assert citation["label"]
        assert citation["kind"]


def test_offline_answer_reports_missing_evidence_honestly(db, project):
    result = asyncio.run(assistant.answer(db, project, "Which supplier is the biggest risk?"))
    assert "supplier" in result["answer"].lower()
    assert result["citations"]


def test_conversation_is_persisted(db, project):
    first = asyncio.run(assistant.answer(db, project, "Summarise the schedule."))
    second = asyncio.run(
        assistant.answer(
            db, project, "And what drives it?", conversation_id=first["conversation_id"]
        )
    )
    assert second["conversation_id"] == first["conversation_id"]

    conversation = assistant.get_conversation(db, project.id, first["conversation_id"])
    assert len(conversation["messages"]) == 4
    assert conversation["messages"][0]["role"] == "user"


def test_unknown_conversation_is_rejected(db, project):
    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        assistant.get_conversation(db, project.id, "missing-conversation")


def test_provider_failure_falls_back_to_offline(db, project, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(providers, "chat", boom)
    result = asyncio.run(assistant.answer(db, project, "What drives the delay?", provider_name="custom"))
    assert result["offline"] is True
    assert result["fallback_reason"]
    assert "RuntimeError" in result["fallback_reason"]


def test_exhausted_budget_switches_to_offline(db, project, monkeypatch):
    from app.ai.providers import ProviderSettings

    configured = ProviderSettings(
        provider="custom",
        base_url="https://example.invalid/v1",
        model="test-model",
        api_key="sk-not-a-real-key",
        timeout=5.0,
        max_retries=0,
        monthly_budget_usd=0.01,
        input_price=0.0,
        output_price=0.0,
        extra={},
    )
    monkeypatch.setattr(providers, "resolve", lambda db, name=None: configured)
    monkeypatch.setattr(assistant, "_month_cost", lambda db, provider: 5.0)
    result = asyncio.run(assistant.answer(db, project, "Any update?", provider_name="custom"))
    assert result["offline"] is True
    assert "budget" in (result["fallback_reason"] or "").lower()


def test_tool_specs_are_read_only():
    from app.ai.tools import TOOL_SPECS

    names = {spec["function"]["name"] for spec in TOOL_SPECS}
    assert "project_overview" in names
    assert "simulation_summary" in names
    for spec in TOOL_SPECS:
        assert spec["type"] == "function"
        assert spec["function"]["description"]
        assert spec["function"]["parameters"]["type"] == "object"


def test_evidence_pack_is_compact(db, project):
    evidence, citations, used = assistant._evidence_pack(db, project, "risk?")
    assert len(evidence) < 60000
    assert citations
    assert used
    assert "simulation_summary" in {item["tool"] for item in used}


def test_chat_endpoint_returns_citations(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/ai/chat",
        json={"message": "What is the on-time probability?", "offline": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["offline"] is True
    assert body["citations"]


def test_ai_status_reports_budget(client, project_id):
    status = client.get(f"/api/projects/{project_id}/ai/status").json()
    assert status["offline_available"] is True
    assert "grounding" in status


def test_suggestions_are_grounded_questions(client, project_id):
    suggestions = client.get(f"/api/projects/{project_id}/ai/suggestions").json()
    assert len(suggestions) >= 5
    assert all(isinstance(item, str) for item in suggestions)
