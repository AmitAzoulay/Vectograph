"""Central application configuration.

All values can be overridden with environment variables so the same image
works locally (docker compose) and in any deployment target.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Neo4j connection ---------------------------------------------------
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "vectograph"

    # --- API behaviour ------------------------------------------------------
    # Comma separated list of allowed CORS origins for the browser.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Hard cap on the size of an uploaded zip, in megabytes.
    max_upload_mb: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (read once per process)."""
    return Settings()


settings = get_settings()
