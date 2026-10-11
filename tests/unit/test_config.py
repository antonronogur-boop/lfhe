"""P1-02 — environment separation and fail-closed configuration."""
import pytest

from lfhe_shared.config import ConfigError, Environment, load_settings

DEV_URL = "postgresql://lfhe_worker_login:x@localhost:5432/lfhe_dev"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("LFHE_"):
            monkeypatch.delenv(key, raising=False)


def test_missing_env_fails_closed():
    with pytest.raises(ConfigError):
        load_settings()


def test_valid_dev_settings(monkeypatch):
    monkeypatch.setenv("LFHE_ENV", "DEV")
    monkeypatch.setenv("LFHE_DATABASE_URL", DEV_URL)
    s = load_settings()
    assert s.env is Environment.DEV
    assert "x@" not in repr(s), "secret must not leak through repr"


def test_unknown_environment_rejected(monkeypatch):
    monkeypatch.setenv("LFHE_ENV", "STAGING")
    monkeypatch.setenv("LFHE_DATABASE_URL", DEV_URL)
    with pytest.raises(ConfigError):
        load_settings()


def test_dev_may_not_point_at_prod_database(monkeypatch):
    monkeypatch.setenv("LFHE_ENV", "DEV")
    monkeypatch.setenv("LFHE_DATABASE_URL", "postgresql://u:x@db/lfhe_prod")
    with pytest.raises(ConfigError, match="prod"):
        load_settings()


def test_prod_rejects_local_storage(monkeypatch):
    monkeypatch.setenv("LFHE_ENV", "PROD")
    monkeypatch.setenv("LFHE_DATABASE_URL", "postgresql://u:x@db/lfhe_production")
    monkeypatch.setenv("LFHE_COLLECTOR_USER_AGENT", "LFHE/1.0 (+ops@example.org)")
    with pytest.raises(ConfigError, match="LOCAL"):
        load_settings()


def test_s3_requires_complete_config_and_env_tagged_bucket(monkeypatch):
    monkeypatch.setenv("LFHE_ENV", "TEST")
    monkeypatch.setenv("LFHE_DATABASE_URL", "postgresql://u:x@db/lfhe_test")
    monkeypatch.setenv("LFHE_STORAGE_BACKEND", "S3")
    with pytest.raises(ConfigError, match="missing"):
        load_settings()
    monkeypatch.setenv("LFHE_STORAGE_S3_ENDPOINT", "https://example.invalid/s3")
    monkeypatch.setenv("LFHE_STORAGE_S3_BUCKET", "lfhe-dev-snapshots")
    monkeypatch.setenv("LFHE_STORAGE_S3_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("LFHE_STORAGE_S3_SECRET_ACCESS_KEY", "secret")
    with pytest.raises(ConfigError, match="environment tag 'test'"):
        load_settings()
    monkeypatch.setenv("LFHE_STORAGE_S3_BUCKET", "lfhe-test-snapshots")
    assert load_settings().storage_s3_bucket == "lfhe-test-snapshots"


def test_collector_max_bytes_bounded(monkeypatch):
    monkeypatch.setenv("LFHE_ENV", "DEV")
    monkeypatch.setenv("LFHE_DATABASE_URL", DEV_URL)
    monkeypatch.setenv("LFHE_COLLECTOR_MAX_BYTES", str(10**10))
    with pytest.raises(ConfigError):
        load_settings()
