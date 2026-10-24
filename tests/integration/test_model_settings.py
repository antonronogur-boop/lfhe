"""P2-01 — database-authoritative model settings allow-list (L-13)."""
import psycopg
import pytest
from psycopg.types.json import Jsonb

from lfhe_orchestrator.model_settings import model_settings_problems

pytestmark = pytest.mark.db
CASES = [
    ("anthropic", "claude-x-1", {"temperature": 0, "max_tokens": 4000, "top_p": 0.9, "timeout_seconds": 120}),
    ("anthropic", "claude-x-1", {"base_url": "https://proxy.example.org"}),
    ("anthropic", "claude-x-1", {"organization": "org-1"}),
    ("anthropic", "claude-x-1", {"temperature": 1.5}),
    ("anthropic", "Claude X", {"temperature": 0}),
    ("fake", "fake-model", {"max_tokens": 0}),
    ("openai", "gpt-x", {}),
    ("anthropic", "claude-sonnet-5-5", {"provider_fixed_sampling": True, "max_tokens": 16000}),      # CR7-01
    ("anthropic", "claude-x-1", {"provider_fixed_sampling": False}),
    ("anthropic", "claude-x-1", {"provider_fixed_sampling": True, "temperature": 0}),
    ("anthropic", "claude-x-1", {"provider_fixed_sampling": "true"}),
    ("fake", "fake-model", {"provider_fixed_sampling": True}),
]
VALID = {0, 7}


def test_database_and_python_allow_lists_agree(pg):
    with pg.admin() as c:
        for provider, model, settings in CASES:
            db = c.execute("SELECT lfhe.model_settings_problems(%s, %s, %s::jsonb) AS p",
                           (provider, model, Jsonb(settings))).fetchone()["p"]
            assert db == model_settings_problems(provider, model, settings), (provider, model, settings)


def test_registration_enforces_allow_list(pg):
    with pg.registrar() as c:
        ok = c.execute("SELECT lfhe.register_model_configuration('anthropic', 'claude-x-1', %s::jsonb) AS id",
                       (Jsonb({"temperature": 0, "max_tokens": 4000}),)).fetchone()["id"]
        assert ok
        assert c.execute("SELECT lfhe.register_model_configuration('anthropic', 'claude-sonnet-5-5', %s::jsonb) AS id",
                         (Jsonb({"provider_fixed_sampling": True, "max_tokens": 16000}),)).fetchone()["id"]
        for i, (provider, model, settings) in enumerate(CASES):
            if i in VALID:
                continue
            with pytest.raises(psycopg.errors.CheckViolation, match="MODEL_SETTINGS_INVALID"):
                c.execute("SELECT lfhe.register_model_configuration(%s, %s, %s::jsonb)",
                          (provider, model, Jsonb(settings)))
