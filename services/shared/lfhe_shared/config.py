"""Environment configuration (P1-02).

Configuration comes only from environment variables (or a git-ignored .env
file in local development). Secrets are held as ``SecretStr`` so they never
appear in logs or reprs. Startup fails closed on invalid or unsafe settings.

Environment separation is enforced twice:
1. here, statically (e.g. PROD may not use local storage), and
2. at connect time, by comparing ``LFHE_ENV`` with the environment recorded
   inside the database itself (``lfhe.deployment_environment``) — see
   ``lfhe_shared.db.connect``.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEV = "DEV"
    TEST = "TEST"
    PROD = "PROD"


class StorageBackend(str, Enum):
    LOCAL = "LOCAL"
    S3 = "S3"


class ConfigError(ValueError):
    """Raised when configuration is missing, invalid or unsafe."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LFHE_", env_file=None, extra="ignore")

    env: Environment
    database_url: SecretStr

    storage_backend: StorageBackend = StorageBackend.LOCAL
    storage_local_root: Path = Path("./.local/storage")
    storage_s3_endpoint: str | None = None
    storage_s3_bucket: str | None = None
    storage_s3_region: str | None = None
    storage_s3_access_key_id: SecretStr | None = None
    storage_s3_secret_access_key: SecretStr | None = None

    collector_user_agent: str = "LFHE-OSINT-Collector/0.1 (+contact: set-me)"
    collector_min_interval_seconds: float = Field(default=5.0, ge=0)
    collector_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    collector_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    collector_respect_robots_txt: bool = True

    # Claim pipeline (Phase 2). Model configurations are registered, immutable,
    # allow-listed rows (lfhe.model_configurations); only their ids are configured
    # here. Provider credentials are NOT settings: the provider adapter reads them
    # from the secret-managed environment at call time (docs/providers.md).
    ai_provider: str = Field(default="anthropic", pattern=r"^(anthropic)$")
    m02_model_configuration_id: str | None = None
    m03_model_configuration_id: str | None = None
    m04_model_configuration_id: str | None = None
    m05_model_configuration_id: str | None = None

    @model_validator(mode="after")
    def _safety_rules(self) -> "Settings":
        url = self.database_url.get_secret_value()
        if not url.startswith(("postgresql://", "postgres://")):
            raise ValueError("LFHE_DATABASE_URL must be a postgresql:// URL")
        lowered = url.lower()
        if self.env is not Environment.PROD and "prod" in lowered:
            raise ValueError(f"{self.env.value} configuration points at a database URL containing 'prod'")
        if self.env is Environment.PROD:
            if self.storage_backend is StorageBackend.LOCAL:
                raise ValueError("PROD must not use LOCAL object storage")
            if any(tag in lowered for tag in ("_dev", "_test", "/dev", "/test")):
                raise ValueError("PROD configuration points at a DEV/TEST-looking database")
            if "set-me" in self.collector_user_agent:
                raise ValueError("PROD requires a collector user agent with a real contact")
        if self.storage_backend is StorageBackend.S3:
            missing = [
                name for name, value in (
                    ("storage_s3_endpoint", self.storage_s3_endpoint),
                    ("storage_s3_bucket", self.storage_s3_bucket),
                    ("storage_s3_access_key_id", self.storage_s3_access_key_id),
                    ("storage_s3_secret_access_key", self.storage_s3_secret_access_key),
                ) if not value
            ]
            if missing:
                raise ValueError(f"S3 storage selected but missing: {', '.join(missing)}")
            env_tag = self.env.value.lower()
            if env_tag not in (self.storage_s3_bucket or "").lower():
                raise ValueError(f"S3 bucket name must contain the environment tag '{env_tag}'")
        return self


def load_settings(**overrides) -> Settings:
    """Load settings from the environment; raise ``ConfigError`` on any problem."""
    try:
        return Settings(**overrides)
    except Exception as exc:  # pydantic ValidationError and others
        raise ConfigError(f"invalid LFHÉ configuration: {exc}") from exc
