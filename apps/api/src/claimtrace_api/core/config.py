"""Application configuration.

All settings are read from environment variables (or a local ``.env`` file) so that
no credential is ever hardcoded in the source tree. See ``.env.example`` at the
repository root for the full list of supported variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
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

    # --- Local LLM provider (Phase 4A-1) ------------------------------------
    # "fake" is the default so that `docker compose up` works with no model
    # server running and no weights downloaded: the LLM is optional
    # infrastructure at this phase, and nothing outside the diagnostics
    # endpoints depends on it. Switching to a real provider is one variable.
    llm_provider: Literal["fake", "ollama", "openai_compatible"] = "fake"

    # Reaches an Ollama running on the *host* from inside the API container,
    # which is the documented default: it reuses models already pulled on the
    # machine instead of downloading a second copy into a container volume.
    # Use http://ollama:11434 with the optional "llm" compose profile instead.
    llm_ollama_base_url: str = "http://host.docker.internal:11434"
    # Small, multilingual (Korean included), instruction-tuned, and practical on
    # CPU. Chosen for validating the boundary, not for analysis quality: see the
    # Phase 4A-1 notes in docs/ARCHITECTURE.md. Reasoning-mode models are avoided
    # here because their thinking preamble is expensive on CPU and interacts
    # badly with schema-constrained decoding.
    llm_ollama_model: str = "qwen2.5:1.5b"

    # A local OpenAI-compatible server (vLLM, llama.cpp, LM Studio). The base URL
    # includes the version prefix the server exposes, normally /v1.
    llm_openai_compatible_base_url: str = "http://localhost:8000/v1"
    llm_openai_compatible_model: str = "local-model"
    # SecretStr: excluded from repr, from model_dump(), and from every log line.
    # Optional because a local server usually has no auth at all.
    llm_openai_compatible_api_key: SecretStr | None = None

    # How strongly the OpenAI-compatible server can constrain JSON. Declared
    # rather than probed: a server that accepts response_format and ignores it is
    # indistinguishable from one that honours it until the output is validated,
    # so claiming schema enforcement is a deployment's assertion to make.
    # Ollama's mode is fixed by its adapter, which enforces a schema natively.
    llm_structured_output_mode: Literal[
        "native_json_schema", "native_json_object", "prompt_constrained_json", "unsupported"
    ] = "native_json_schema"

    # Short: a wrong port should fail immediately rather than hang.
    llm_connect_timeout_seconds: float = 5.0
    # Generous: a small model on CPU genuinely takes this long to answer.
    llm_read_timeout_seconds: float = 120.0
    # The ceiling for one whole call, retries included. A per-request timeout may
    # lower this; nothing may raise it.
    llm_max_timeout_seconds: float = 180.0

    # Two attempts, not five. See claimtrace_api.llm.retry for the reasoning:
    # only failures that never reached the server are replayed.
    llm_retry_max_attempts: int = 2
    llm_retry_initial_backoff_seconds: float = 0.25
    llm_retry_max_backoff_seconds: float = 4.0
    llm_retry_max_total_delay_seconds: float = 8.0

    # Request bounds enforced before a provider is contacted.
    llm_max_prompt_characters: int = 8000
    llm_max_output_tokens: int = 1024

    # The diagnostics endpoints generate text on demand, so they are development
    # tooling rather than product surface. None means "follow the environment",
    # which resolves to enabled in development and disabled everywhere else;
    # an explicit true or false overrides that.
    llm_diagnostics_enabled: bool | None = None

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

    @field_validator("llm_diagnostics_enabled", "llm_openai_compatible_api_key", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Treat an empty environment variable as absent.

        ``LLM_DIAGNOSTICS_ENABLED=`` in a ``.env`` file arrives as ``""``, which
        pydantic would reject as an invalid boolean rather than read as "not
        set". Since leaving these blank is exactly what ``.env.example``
        documents - blank means "follow the environment", and a blank API key
        means "this local server has no auth" - the empty string has to mean
        None here or the documented configuration fails to start.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

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

    @property
    def llm_diagnostics_active(self) -> bool:
        """Whether the LLM diagnostics endpoints are served.

        Resolves the tri-state setting: an explicit value wins, and the default
        follows the environment so that a staging or production deployment does
        not expose an on-demand generation endpoint just because nobody
        remembered to turn it off.
        """
        if self.llm_diagnostics_enabled is not None:
            return self.llm_diagnostics_enabled
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
