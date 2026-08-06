from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "FinSentinel AI"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "sqlite+pysqlite:///./finsentinel.db"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    neo4j_uri: str = "bolt://localhost:7687"
    kafka_bootstrap_servers: str = "localhost:19092"

    default_llm_provider: str = "mock"
    jwt_audience: str = "finsentinel-api"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache

def get_settings() -> Settings:
    return Settings()
