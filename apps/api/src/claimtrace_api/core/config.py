"""Application configuration.

All settings are read from environment variables (or a local ``.env`` file) so that
no credential is ever hardcoded in the source tree. See ``.env.example`` at the
repository root for the full list of supported variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    """Runtime configuration for the ClaimTrace API."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------
    app_name: str = "ClaimTrace API"
    app_version: str = "0.1.0"
    environment: Environment = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- Logging -----------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "text"

    # --- CORS --------------------------------------------------------------
    # NoDecode keeps pydantic-settings from JSON-decoding the env value, so the
    # variable can be written as a plain comma-separated list.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    cors_allow_credentials: bool = False

    # --- PostgreSQL --------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "claimtrace"
    postgres_db: str = "claimtrace"
    # No default: a password belongs in the environment, never in the source tree.
    # Leaving it empty fails the connection loudly instead of silently using a
    # value someone might mistake for a safe one.
    postgres_password: str = ""

    # Optional full DSN override. When set it wins over the discrete fields above.
    database_url: str | None = None

    # Fail readiness fast instead of hanging on an unreachable database.
    db_connect_timeout_seconds: int = 5

    # --- Document ingestion ------------------------------------------------
    # Where uploaded originals are written. Must live outside the source tree.
    storage_root: Path = Path("/data/uploads")

    # Hard ceiling on an accepted upload. Enforced while streaming, so an
    # oversized body is rejected without being buffered in full.
    upload_max_bytes: int = 20 * 1024 * 1024

    upload_allowed_content_types: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["application/pdf"]
    )
    upload_allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [".pdf"]
    )

    # A digital PDF yielding fewer than this many characters in total is treated
    # as scanned or image-only. This phase does not do OCR, so such a document is
    # recorded as failed rather than silently ingested as empty.
    min_extracted_characters: int = 32

    # --- Claim indexing: embeddings ----------------------------------------
    # "sentence-transformers" loads the real local model; "fake" is the
    # deterministic hashing provider used by tests and by any environment that
    # must not download weights. Both satisfy the same protocol.
    embedding_provider: Literal["sentence-transformers", "fake"] = "sentence-transformers"

    embedding_model: str = "intfloat/multilingual-e5-small"

    # Where model weights are cached. A container volume by default, so weights
    # are downloaded once and never enter the image or the Git tree.
    embedding_cache_dir: Path = Path("/models")

    # "cpu" is the only value this deployment is validated on. The setting exists
    # so a GPU host does not need a code change.
    embedding_device: str = "cpu"

    embedding_batch_size: int = 16

    # The dimension the database column was migrated with. The provider's own
    # dimension is checked against this before anything is written, because a
    # mismatch would otherwise surface as an opaque pgvector error mid-insert.
    embedding_dimension: int = 384

    # Bumped when the normalised search representation changes in a way that
    # makes old records incomparable. Part of the index profile identity.
    normalization_version: str = "nfkc-v1"

    # --- Claim retrieval ----------------------------------------------------
    dense_candidate_count: int = 30
    lexical_candidate_count: int = 30

    # Reciprocal Rank Fusion constant. 60 is the value from the original RRF
    # paper and the common default; it flattens the contribution of deep ranks.
    rrf_k: int = 60

    search_top_k_default: int = 10
    search_top_k_max: int = 50
    search_candidate_count_max: int = 200
    search_query_max_length: int = 512

    @field_validator(
        "cors_allow_origins",
        "upload_allowed_content_types",
        "upload_allowed_extensions",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept a comma-separated string so each list maps to a single env var."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("upload_allowed_extensions")
    @classmethod
    def _normalise_extensions(cls, value: list[str]) -> list[str]:
        """Compare extensions case-insensitively and always with a leading dot."""
        return [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in value]

    @field_validator("upload_allowed_content_types")
    @classmethod
    def _normalise_content_types(cls, value: list[str]) -> list[str]:
        return [item.lower() for item in value]

    @property
    def sqlalchemy_database_uri(self) -> str:
        """SQLAlchemy URL using the psycopg (v3) driver.

        The same URL is used by the async application engine and by the synchronous
        Alembic engine; SQLAlchemy selects the driver mode from the engine factory.
        """
        if self.database_url:
            return self.database_url
        dsn = PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )
        return str(dsn)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
