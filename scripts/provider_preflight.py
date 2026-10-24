#!/usr/bin/env python3
"""Phase 7 provider preflight (pilot tooling): one minimal request with the SAME request shape the
AnthropicProvider sends (model, max_tokens, sampling per LFHE_P7_SAMPLING, system, one user message), so a rejected
configuration is diagnosed before any trial run.

    LFHE_ANTHROPIC_API_KEY (secret-managed env) + LFHE_P7_MODEL [+ LFHE_P7_MAX_TOKENS]
    python scripts/provider_preflight.py

Prints only the HTTP status, the provider's error type / message and the request id — never the key,
headers or the request body. Exit 0 = accepted, 1 = rejected / unreachable."""
from __future__ import annotations

import json
import os
import sys

import httpx

URL = "https://api.anthropic.com/v1/messages"


def report(line: str, ok: bool, **fields) -> None:
    print(line)
    out = os.environ.get("LFHE_P7_PREFLIGHT_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"ok": ok, **fields}, fh, indent=1, sort_keys=True)


def main() -> int:
    key, model = os.environ.get("LFHE_ANTHROPIC_API_KEY"), os.environ.get("LFHE_P7_MODEL")
    if not key or not model:
        print("PREFLIGHT: LFHE_ANTHROPIC_API_KEY and LFHE_P7_MODEL must be set")
        return 1
    body = {"model": model, "max_tokens": int(os.environ.get("LFHE_P7_MAX_TOKENS", "16000")),
            "system": "Answer with exactly one JSON object.", "messages": [{"role": "user", "content": "Return {\"ok\": true}."}]}
    sampling = os.environ.get("LFHE_P7_SAMPLING", "provider_fixed")
    if sampling != "provider_fixed":
        body["temperature"] = 0                      # same shape as AnthropicProvider.render_request (CR7-01)
    try:
        r = httpx.post(URL, json=body, timeout=60, headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                                            "content-type": "application/json"})
    except httpx.HTTPError as exc:
        report(f"PREFLIGHT: provider unreachable ({type(exc).__name__})", False, error=type(exc).__name__)
        return 1
    rid = r.headers.get("request-id", "")
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code == 200:
        report(f"PREFLIGHT: OK model={data.get('model')} stop_reason={data.get('stop_reason')} usage={json.dumps(data.get('usage'))} "
               f"request_id={rid} sampling={sampling}", True, http_status=200, model=data.get("model"), request_id=rid, sampling=sampling)
        return 0
    err = data.get("error") or {}
    msg = str(err.get("message", ""))[:400].replace(key, "***")
    report(f"PREFLIGHT: REJECTED HTTP {r.status_code} type={err.get('type')} message={msg!r} request_id={rid} sampling={sampling}", False,
           http_status=r.status_code, error_type=err.get("type"), error_message=msg, request_id=rid, model_requested=model, sampling=sampling)
    return 1


if __name__ == "__main__":
    sys.exit(main())
