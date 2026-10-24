"""Phase 7 harness support: provider selection for the benchmark and the real-provider trial.

LFHE_P7_PROVIDER=anthropic selects the real AnthropicProvider (credentials only from the secret-managed
environment, LFHE_ANTHROPIC_API_KEY); LFHE_P7_MODEL names the model explicitly (no default model is
assumed). Anything else selects the deterministic rule-based M10-S stand-in, which is a TEST DOUBLE:
its results are regression evidence only, never evidence of real-provider quality (Baseline §14)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "tests" / "integration", ROOT / "tests" / "acceptance"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from psycopg.types.json import Jsonb  # noqa: E402

from lfhe_orchestrator.providers import AnthropicProvider, FakeProvider, render_messages  # noqa: E402
from m10s_auditor import auditor  # noqa: E402
from pipeline_support import model_configuration  # noqa: E402

_CONFIGS: dict[str, str] = {}


def real_provider_requested() -> bool:
    return os.environ.get("LFHE_P7_PROVIDER") == "anthropic"


def provider_label() -> str:
    return f"anthropic/{os.environ['LFHE_P7_MODEL']}" if real_provider_requested() else "TEST_DOUBLE(rule-based M10-S stand-in)"


class Recorder:
    """Keeps every text actually rendered for the provider (system + messages + envelope)."""

    def __init__(self, inner):
        self.inner, self.texts = inner, []
        self.name = inner.name

    def run_structured_task(self, module, envelope, model_config):
        system, msgs = render_messages(module, envelope)
        self.texts.append(system + json.dumps(envelope, ensure_ascii=False) + "".join(m["content"] for m in msgs))
        return self.inner.run_structured_task(module, envelope, model_config)


def provider_and_config(pg, *, stand_in=None):
    """(provider, model_configuration_id). The real provider gets a registered anthropic configuration with
    explicit max_tokens / timeout and either provider_fixed_sampling (CR7-01, default; for models that reject
    `temperature`) or temperature 0 (LFHE_P7_SAMPLING=temperature_0)."""
    if real_provider_requested():
        model = os.environ["LFHE_P7_MODEL"]
        key = f"anthropic:{model}:{os.environ.get('LFHE_P7_SAMPLING', 'provider_fixed')}"
        if key not in _CONFIGS:
            settings = {"max_tokens": int(os.environ.get("LFHE_P7_MAX_TOKENS", "16000")),
                        "timeout_seconds": int(os.environ.get("LFHE_P7_TIMEOUT_SECONDS", "300"))}
            if os.environ.get("LFHE_P7_SAMPLING", "provider_fixed") == "provider_fixed":
                settings["provider_fixed_sampling"] = True          # CR7-01: model rejects temperature
            else:
                settings["temperature"] = 0
            with pg.registrar() as c:
                _CONFIGS[key] = str(c.execute("SELECT lfhe.register_model_configuration('anthropic', %s, %s::jsonb) id",
                                              (model, Jsonb(settings))).fetchone()["id"])
        return Recorder(AnthropicProvider.from_environment()), _CONFIGS[key]
    return Recorder(FakeProvider(stand_in or auditor())), model_configuration(pg)


def write_json(env_var: str, doc: dict) -> None:
    out = os.environ.get(env_var)
    if out:
        Path(out).write_text(json.dumps(doc, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
