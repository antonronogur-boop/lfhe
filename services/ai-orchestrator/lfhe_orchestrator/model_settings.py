"""Provider-specific allow-listed, non-secret model settings (L-13).

Mirror of lfhe.model_settings_problems (the database is authoritative).
Credentials are never part of a model configuration: adapters read them from
the environment populated by the platform secret manager (docs/providers.md).
"""
from __future__ import annotations

import re

_MODEL = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,99}$")
_RULES = {
    "fake": {"temperature": (0, 1, False), "max_tokens": (1, 64000, True)},
    "anthropic": {"temperature": (0, 1, False), "max_tokens": (1, 64000, True),
                  "top_p": (0, 1, False), "timeout_seconds": (1, 600, False)},
}
# Low-variance requirement for extraction / classification modules (addendum §14).
LOW_VARIANCE_MAX_TEMPERATURE = 0.2
LOW_VARIANCE_MODULES = ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER", "M04_LINEAGE", "M05_EVENT_BUILDER")


def model_settings_problems(provider: str, model: str, settings) -> list[str]:
    rules = _RULES.get(provider)
    if rules is None:
        return ["provider (PROVIDER_NOT_ALLOWED)"]
    out = [] if isinstance(model, str) and _MODEL.match(model) else ["model (INVALID_MODEL_IDENTIFIER)"]
    if not isinstance(settings, dict):
        return out + ["$ (NOT_AN_OBJECT)"]
    for key in sorted(settings, key=lambda k: k.encode()):
        value = settings[key]
        if key not in rules:
            out.append(f"$.{key} (SETTING_NOT_ALLOWED_FOR_PROVIDER)")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            out.append(f"$.{key} (NOT_A_NUMBER)")
            continue
        lo, hi, integer = rules[key]
        bad = not (lo <= value <= hi) or (integer and value != int(value))
        if key == "top_p":
            bad = not (0 < value <= 1)
        if bad:
            out.append(f"$.{key} (OUT_OF_RANGE)")
    return out


def low_variance_problem(module_code: str, settings: dict) -> str | None:
    """M02/M03 must run with low-variance settings (temperature ≤ 0.2, explicit)."""
    if module_code not in LOW_VARIANCE_MODULES:
        return None
    temperature = settings.get("temperature")
    if temperature is None or temperature > LOW_VARIANCE_MAX_TEMPERATURE:
        return (f"{module_code} requires an explicit temperature ≤ {LOW_VARIANCE_MAX_TEMPERATURE} "
                f"(got {temperature!r})")
    return None
