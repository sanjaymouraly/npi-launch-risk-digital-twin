"""Environment-driven application configuration.

All secrets come from environment variables (or a local ``.env`` file that is
git-ignored).  Nothing sensitive is ever logged or returned by the API.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application -----------------------------------------------------
    app_name: str = "NPI Launch Risk Digital Twin"
    version: str = "1.0.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # --- persistence -----------------------------------------------------
    database_url: str = "sqlite:///./npi.db"
    seed_demo_on_startup: bool = True

    # --- security --------------------------------------------------------
    secret_key: str = "dev-only-change-me"
    auth_enabled: bool = False
    access_token_minutes: int = 720
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    # --- job execution ---------------------------------------------------
    job_workers: int = 2
    job_timeout_seconds: int = 900
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # --- simulation / solver defaults ------------------------------------
    simulation_default_iterations: int = 2000
    simulation_max_iterations: int = 50000
    simulation_max_tasks: int = 800
    solver_time_limit_seconds: float = 20.0
    max_upload_bytes: int = 10 * 1024 * 1024

    # --- AI providers (all optional; offline mode is the default) --------
    ai_active_provider: str = "offline"
    ai_request_timeout_seconds: float = 120.0
    ai_max_retries: int = 2
    ai_monthly_budget_usd: float = 25.0
    ai_max_output_tokens: int = 1200

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-4-20250514"

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "anthropic/claude-sonnet-4"

    custom_api_key: str | None = None
    custom_base_url: str | None = None
    custom_model: str | None = None

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:1b"

    # Price table used for *estimates* when a provider does not report cost.
    ai_price_per_mtok_input_usd: float = 0.0
    ai_price_per_mtok_output_usd: float = 0.0

    @field_validator("allowed_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return ",".join(part.strip() for part in value.split(",") if part.strip())

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite_path(cls, value: str) -> str:
        """Resolve relative SQLite paths against the backend package directory.

        Without this, ``sqlite:///./npi.db`` would point at a different file
        depending on the working directory, which silently splits the data
        between the API server and maintenance scripts.
        """
        if not value.startswith("sqlite:///"):
            return value
        path = value[len("sqlite:///") :]
        if not path or path.startswith("/") or path == ":memory:":
            return value
        base = Path(__file__).resolve().parents[2]
        return f"sqlite:///{(base / path).resolve()}"

    @property
    def origins(self) -> list[str]:
        return [o for o in self.allowed_origins.split(",") if o]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
