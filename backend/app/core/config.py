from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
