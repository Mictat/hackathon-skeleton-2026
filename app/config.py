from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ATLAS_", extra="ignore")

    database_url: str = "postgresql+psycopg://TEMPNAME:TEMPNAME_dev@localhost:5433/TEMPNAME"
    app_name: str = "TEMPNAME — AI Data Discovery"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_cache_dir: str = ".llm_cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
