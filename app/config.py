from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TEMPNAME_", extra="ignore")

    database_url: str = "postgresql+psycopg://TEMPNAME:TEMPNAME_dev@localhost:5433/TEMPNAME"
    app_name: str = "TEMPNAME — AI Data Discovery"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_cache_dir: str = ".llm_cache"
    scan_pacing_ms: int = 150  # demo day: set 150 → assets visibly stream in
    sample_db_password: str = "bank_dev"  # dev fallback; prod sets real env var
    llm_base_url: str = "https://api.openai.com/v1"  # any OpenAI-compatible provider
    llm_offline: bool = False  # cache-only mode (demo safety)
    llm_timeout_s: int = 45
    enrich_pacing_ms: int = 0  # demo day: 600 → agents visibly tick


@lru_cache
def get_settings() -> Settings:
    return Settings()
