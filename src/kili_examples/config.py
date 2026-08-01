"""Project settings, loaded from the environment and from `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from kili_examples.paths import PROJECT_ROOT


class Settings(BaseSettings):
    """Load environment variables as settings."""

    # Define environment variables of the project here

    # ENVIRONMENT
    environment: Literal["local", "test", "dev", "preprod", "prod"] = "local"

    # LOG_LEVEL
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        "INFO"
    )

    # RANDOM_SEED
    random_seed: int = 42

    # KILI_API_KEY — jeton d'API de l'instance Kili.
    # Pas de valeur par défaut : l'absence de clé doit échouer bruyamment
    # plutôt que de laisser croire à une configuration valide.
    kili_api_key: str | None = None

    # KILI_API_ENDPOINT — endpoint GraphQL de l'instance on-premise.
    # Sur une instance auto-hébergée, l'URL se termine généralement par
    # /api/label/v2/graphql
    kili_api_endpoint: str | None = None

    # Load dotenv from the project root, so it also works from notebooks/
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", extra="ignore"
    )


# Avoid loading at every import
@lru_cache
def get_settings() -> Settings:
    """Return settings"""
    return Settings()


settings = get_settings()
