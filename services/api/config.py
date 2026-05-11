from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    # DB / Supabase
    database_url: str | None = None
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    # LLM
    anthropic_api_key: str | None = None
    anthropic_synthesis_model: str = "claude-opus-4-7"
    anthropic_agent_model: str = "claude-sonnet-4-6"
    anthropic_fast_model: str = "claude-haiku-4-5-20251001"

    # Embeddings
    embedding_provider: str = "voyage"
    voyage_api_key: str | None = None
    voyage_embedding_model: str = "voyage-finance-2"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    # Data APIs
    news_api_key: str | None = None
    fred_api_key: str | None = None
    fmp_api_key: str | None = None
    companies_house_api_key: str | None = None

    # SEC
    sec_user_agent: str = "AI-quant research prototype contact@example.com"

    # Feature flags
    enable_live_news: bool = True
    enable_live_macro: bool = True
    enable_live_sec: bool = True
    enable_live_uk_disclosures: bool = True
    enable_companies_house: bool = False
    enable_fmp_transcripts: bool = False
    enable_demo_mode: bool = True

    # CORS — comma-separated string in env, parsed to list.
    cors_origins: str = Field(default="http://localhost:3000")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
