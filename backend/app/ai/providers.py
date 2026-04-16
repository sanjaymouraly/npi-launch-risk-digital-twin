"""Multi-provider LLM adapters (OpenAI-compatible, Anthropic, Ollama, offline).

Credentials are read from the environment or from encrypted provider records.
They are never returned to clients or written to logs.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ProviderError, ValidationError
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.models import AIProviderConfig

PROVIDERS = ["offline", "ollama", "openai", "anthropic", "openrouter", "custom"]


@dataclass
class ProviderSettings:
    provider: str
    base_url: str
    model: str
    api_key: str | None
    timeout: float
    max_retries: int
    monthly_budget_usd: float
    input_price: float
    output_price: float
    extra: dict

    @property
    def is_openai_compatible(self) -> bool:
        return self.provider in ("openai", "openrouter", "custom", "ollama")

    @property
    def configured(self) -> bool:
        if self.provider == "offline":
            return True
        if self.provider == "ollama":
            return bool(self.base_url and self.model)
        return bool(self.base_url and self.model and self.api_key)


def _env_defaults(provider: str) -> ProviderSettings:
    if provider == "ollama":
        return ProviderSettings(
            provider="ollama",
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            api_key=None,
            timeout=settings.ai_request_timeout_seconds,
            max_retries=settings.ai_max_retries,
            monthly_budget_usd=0.0,
            input_price=0.0,
            output_price=0.0,
            extra={},
        )
    if provider == "openai":
        return ProviderSettings(
            "openai", settings.openai_base_url, settings.openai_model, settings.openai_api_key,
            settings.ai_request_timeout_seconds, settings.ai_max_retries,
            settings.ai_monthly_budget_usd, settings.ai_price_per_mtok_input_usd,
            settings.ai_price_per_mtok_output_usd, {},
        )
    if provider == "anthropic":
        return ProviderSettings(
            "anthropic", settings.anthropic_base_url, settings.anthropic_model, settings.anthropic_api_key,
            settings.ai_request_timeout_seconds, settings.ai_max_retries,
            settings.ai_monthly_budget_usd, settings.ai_price_per_mtok_input_usd,
            settings.ai_price_per_mtok_output_usd, {},
        )
    if provider == "openrouter":
        return ProviderSettings(
            "openrouter", settings.openrouter_base_url, settings.openrouter_model, settings.openrouter_api_key,
            settings.ai_request_timeout_seconds, settings.ai_max_retries,
            settings.ai_monthly_budget_usd, settings.ai_price_per_mtok_input_usd,
            settings.ai_price_per_mtok_output_usd, {},
        )
    if provider == "custom":
        return ProviderSettings(
            "custom",
            settings.custom_base_url or "",
            settings.custom_model or "",
            settings.custom_api_key,
            settings.ai_request_timeout_seconds,
            settings.ai_max_retries,
            settings.ai_monthly_budget_usd,
            settings.ai_price_per_mtok_input_usd,
            settings.ai_price_per_mtok_output_usd,
            {},
        )
    return ProviderSettings("offline", "", "offline-analytics", None, 5, 0, 0, 0, 0, {})


def resolve(db: Session | None, provider: str | None = None) -> ProviderSettings:
    if provider is None and db is not None:
        # A provider explicitly enabled in the UI takes precedence over the
        # environment default. This keeps the settings screen authoritative.
        preferred = db.scalar(select(AIProviderConfig).where(AIProviderConfig.enabled.is_(True)))
        if preferred is not None:
            provider = preferred.provider
    provider = (provider or settings.ai_active_provider or "offline").lower()
    if provider not in PROVIDERS:
        raise ValidationError(f"Unknown AI provider '{provider}'", details={"supported": PROVIDERS})
    base = _env_defaults(provider)
    if db is None:
        return base
    record = db.scalar(select(AIProviderConfig).where(AIProviderConfig.provider == provider))
    if not record:
        return base
    return ProviderSettings(
        provider=provider,
        base_url=record.base_url or base.base_url,
        model=record.model or base.model,
        api_key=decrypt_secret(record.api_key_encrypted) or base.api_key,
        timeout=record.timeout_seconds or base.timeout,
        max_retries=record.max_retries,
        monthly_budget_usd=record.monthly_budget_usd,
        input_price=record.input_price_per_mtok or base.input_price,
        output_price=record.output_price_per_mtok or base.output_price,
        extra=dict(record.extra or {}),
    )


def list_configs(db: Session) -> list[dict]:
    active_provider = resolve(db, None).provider
    out = []
    for provider in PROVIDERS:
        resolved = resolve(db, provider)
        record = db.scalar(select(AIProviderConfig).where(AIProviderConfig.provider == provider))
        out.append(
            {
                "provider": provider,
                "enabled": bool(record.enabled) if record else provider == active_provider,
                "active": provider == active_provider,
                "configured": resolved.configured,
                "base_url": resolved.base_url,
                "model": resolved.model,
                "api_key_masked": mask_secret(resolved.api_key),
                "timeout_seconds": resolved.timeout,
                "max_retries": resolved.max_retries,
                "monthly_budget_usd": resolved.monthly_budget_usd,
                "input_price_per_mtok": resolved.input_price,
                "output_price_per_mtok": resolved.output_price,
                "requires_key": provider not in ("offline", "ollama"),
            }
        )
    return out


def update_config(db: Session, provider: str, patch) -> dict:  # noqa: ANN001
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ValidationError(f"Unknown AI provider '{provider}'")
    record = db.scalar(select(AIProviderConfig).where(AIProviderConfig.provider == provider))
    if not record:
        record = AIProviderConfig(provider=provider)
        db.add(record)
    if patch.enabled is not None:
        record.enabled = patch.enabled
        if patch.enabled:
            # Only one provider can be active at a time.
            for other in db.scalars(
                select(AIProviderConfig).where(AIProviderConfig.provider != provider)
            ):
                other.enabled = False
    if patch.base_url is not None:
        record.base_url = patch.base_url.strip() or None
    if patch.model is not None:
        record.model = patch.model.strip() or None
    if patch.api_key is not None and patch.api_key != "":
        record.api_key_encrypted = encrypt_secret(patch.api_key)
    if patch.timeout_seconds is not None:
        record.timeout_seconds = patch.timeout_seconds
    if patch.max_retries is not None:
        record.max_retries = patch.max_retries
    if patch.monthly_budget_usd is not None:
        record.monthly_budget_usd = patch.monthly_budget_usd
    if patch.input_price_per_mtok is not None:
        record.input_price_per_mtok = patch.input_price_per_mtok
    if patch.output_price_per_mtok is not None:
        record.output_price_per_mtok = patch.output_price_per_mtok
    if patch.extra is not None:
        record.extra = patch.extra
    db.commit()
    return next(c for c in list_configs(db) if c["provider"] == provider)


async def _request_with_retries(
    method: str, url: str, *, headers: dict, json_body: dict, timeout: float, retries: int
) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, headers=headers, json=json_body)
            if response.status_code >= 500 and attempt < retries:
                last_error = ProviderError(f"Provider returned {response.status_code}")
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            if response.status_code >= 400:
                detail = response.text[:600]
                raise ProviderError(
                    f"Provider returned HTTP {response.status_code}",
                    details={"provider_response": detail},
                    status_code=502,
                )
            return response.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            await asyncio.sleep(0.6 * (attempt + 1))
    raise ProviderError(f"AI provider unreachable: {last_error}")


async def test_connection(cfg: ProviderSettings) -> dict:
    if cfg.provider == "offline":
        return {
            "ok": True,
            "provider": "offline",
            "model": "offline-analytics",
            "message": "Offline deterministic analytics active — no external calls.",
        }
    if not cfg.configured:
        return {"ok": False, "provider": cfg.provider, "error": "Provider is not fully configured"}
    if cfg.provider == "anthropic":
        try:
            data = await _request_with_retries(
                "POST",
                cfg.base_url.rstrip("/") + "/v1/messages",
                headers={
                    "x-api-key": cfg.api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json_body={
                    "model": cfg.model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                },
                timeout=min(cfg.timeout, 45),
                retries=cfg.max_retries,
            )
            text = "".join(
                block.get("text", "") for block in data.get("content", []) if isinstance(block, dict)
            )
            return {"ok": True, "provider": cfg.provider, "model": cfg.model, "reply": text[:80]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "provider": cfg.provider, "error": str(exc)[:300]}
    if cfg.provider == "ollama":
        try:
            data = await _request_with_retries(
                "POST",
                cfg.base_url.rstrip("/") + "/api/chat",
                headers={"content-type": "application/json"},
                json_body={
                    "model": cfg.model,
                    "messages": [{"role": "user", "content": "Reply with OK"}],
                    "stream": False,
                    "options": {"num_predict": 8},
                },
                timeout=min(cfg.timeout, 60),
                retries=cfg.max_retries,
            )
            return {
                "ok": True,
                "provider": cfg.provider,
                "model": cfg.model,
                "reply": (data.get("message") or {}).get("content", "")[:80],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "provider": cfg.provider, "error": str(exc)[:300]}
    try:
        data = await _request_with_retries(
            "GET",
            cfg.base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json_body={},
            timeout=min(cfg.timeout, 30),
            retries=cfg.max_retries,
        )
        models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
        return {
            "ok": True,
            "provider": cfg.provider,
            "model": cfg.model,
            "available_models": models[:25],
            "model_present": (cfg.model in models) if models else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "provider": cfg.provider, "error": str(exc)[:300]}


async def list_models(cfg: ProviderSettings) -> list[str]:
    if cfg.provider == "offline":
        return ["offline-analytics"]
    if cfg.provider == "ollama":
        async with httpx.AsyncClient(timeout=min(cfg.timeout, 20)) as client:
            response = await client.get(cfg.base_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
    if cfg.provider == "anthropic":
        return [
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest",
            "claude-3-5-haiku-latest",
        ]
    data = await _request_with_retries(
        "GET",
        cfg.base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        json_body={},
        timeout=min(cfg.timeout, 25),
        retries=0,
    )
    return [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]


async def chat(
    cfg: ProviderSettings,
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.2,
) -> dict:
    """Return {content, tool_calls, usage, model, latency_ms}."""
    started = time.perf_counter()
    max_tokens = max_tokens or settings.ai_max_output_tokens
    if cfg.provider == "anthropic":
        payload: dict = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": next((m["content"] for m in messages if m["role"] == "system"), ""),
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m["role"] in ("user", "assistant") and m.get("content")
            ],
        }
        if tools:
            payload["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]
        data = await _request_with_retries(
            "POST",
            cfg.base_url.rstrip("/") + "/v1/messages",
            headers={
                "x-api-key": cfg.api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json_body=payload,
            timeout=cfg.timeout,
            retries=cfg.max_retries,
        )
        content = ""
        tool_calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )
        usage = data.get("usage", {})
        return {
            "content": content,
            "tool_calls": tool_calls,
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
            "model": data.get("model", cfg.model),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    if cfg.provider == "ollama":
        payload = {
            "model": cfg.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        data = await _request_with_retries(
            "POST",
            cfg.base_url.rstrip("/") + "/api/chat",
            headers={"content-type": "application/json"},
            json_body=payload,
            timeout=cfg.timeout,
            retries=cfg.max_retries,
        )
        message = data.get("message") or {}
        return {
            "content": message.get("content", ""),
            "tool_calls": [],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            "model": data.get("model", cfg.model),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    try:
        data = await _request_with_retries(
            "POST",
            cfg.base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            },
            json_body=payload,
            timeout=cfg.timeout,
            retries=cfg.max_retries,
        )
    except ProviderError:
        if not tools:
            raise
        # Some gateways reject tool schemas; retry without tools (context is pre-injected).
        payload.pop("tools", None)
        payload.pop("tool_choice", None)
        data = await _request_with_retries(
            "POST",
            cfg.base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            },
            json_body=payload,
            timeout=cfg.timeout,
            retries=cfg.max_retries,
        )
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}
    return {
        "content": message.get("content") or "",
        "tool_calls": message.get("tool_calls") or [],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        },
        "model": data.get("model", cfg.model),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def estimate_cost(cfg: ProviderSettings, prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        prompt_tokens / 1_000_000 * cfg.input_price
        + completion_tokens / 1_000_000 * cfg.output_price,
        6,
    )
