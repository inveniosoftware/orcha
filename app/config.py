from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-specific configuration settings."""

    CLIENT_PUBLIC_KEY: str
    JWT_ALGORITHM: str = "RS256"
    JWT_AUDIENCE: str = "ai-workflow"
    JWT_ISSUER: str = "zenodo"
    DISABLE_AUTH: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
