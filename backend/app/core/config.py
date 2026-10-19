from functools import lru_cache
from pathlib import Path

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
