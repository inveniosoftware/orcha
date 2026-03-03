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
    pgdatabase: str = "airdec"

    # Temporal
    temporal_host: str = "localhost:7233"

    # Authentication
    jwt_public_key: str = ""
    jwt_algorithm: str = "RS256"
    auth_disabled: bool = False

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
