"""Runtime configuration loaded from environment variables.

All settings use the ``RECEPTRA_`` prefix. See repo-root ``.env.example``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Receptra runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RECEPTRA_",
        case_sensitive=False,
        extra="ignore",
    )

    model_dir: str = "/models"
    ollama_host: str = "http://host.docker.internal:11434"
    chroma_host: str = "http://chromadb:8000"
    log_level: str = "INFO"


settings = Settings()
