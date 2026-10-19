from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://calibr:calibr@localhost:5432/calibr"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_embedding_model: str = ""
    embedding_dim: int = 1536
    # live | record | replay | fake
    llm_mode: str = "fake"
    llm_redact_pii: bool = False
    raw_samples: int = 3
    fixtures_dir: Path = Path(__file__).resolve().parents[3] / "data" / "fixtures"
    raw_data_dir: Path = Path(__file__).resolve().parents[3] / "data" / "raw"
    upload_dir: Path = Path(__file__).resolve().parents[3] / "uploads"
    max_upload_mb: int = 15
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    # Hard cap on cumulative live LLM spend (sum of llm_calls.cost_usd).
    llm_budget_usd: float = 5.0
    # Optional JSON override of the PRICES table: {"model": {"input": .., "cached": .., "output": ..}}
    llm_prices_json: str = ""
    # Reasoning effort sent to reasoning models (e.g. none/low); empty = omit the parameter.
    llm_reasoning_effort: str = ""
    llm_timeout_s: int = 120
    agent_max_steps: int = 12
    agent_max_ops_per_turn: int = 25
    agent_confirm_delta_pct: float = 30.0
    agent_history_token_budget: int = 6000
    agent_recent_edit_minutes: int = 30
    agent_run_lock_stale_s: int = 300
    # --- deployment / accounts ---
    app_env: str = "development"  # development | test | production
    session_secret: str = ""
    session_days: int = 7
    cookie_secure: bool | None = None  # default: True in production
    admin_email: str = ""
    admin_password: str = ""
    signup_mode: str = "invite"  # open | invite | closed
    # password = normal accounts; quick = members just enter a name (no password); admins still use a password
    auth_mode: str = "password"
    invite_code: str = ""
    public_app_url: str = "http://localhost:3000"
    robots_index: bool = False
    # --- cost protection ---
    user_daily_usd_cap: float = 0.50
    user_hourly_requests: int = 60
    max_concurrent_runs_per_user: int = 2
    max_request_tokens: int = 60_000

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres (Render, Heroku-style) hands out postgres:// or postgresql:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
