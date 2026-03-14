"""Centralized application settings using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Database
    pguser: str = "postgres"
    pgpassword: str = "postgres"
    pghost: str = "localhost"
    pgport: str = "5433"
    pgdatabase: str = "orcha"

    # Temporal
    temporal_host: str = "localhost:7233"

    # Authentication
    jwt_algorithm: str = "RS256"
    auth_disabled: bool = False
    tenants_config_path: str = "tenants.json"

    # Security
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # LLM
    # TODO Currently we have only a single workflow, so single LLM configuration
    # is fine. We can parameterize it or make it configurable per workflow later.
    llm: str = "ollama/qwen3:4b"
    litellm_api_base: str = "<litellm-endpoint>"
    litellm_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str | None = None

    @property
    def database_url(self) -> str:
        """Build the PostgreSQL connection string."""
        return (
            f"postgresql+psycopg://{self.pguser}:{self.pgpassword}"
            f"@{self.pghost}:{self.pgport}/{self.pgdatabase}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
