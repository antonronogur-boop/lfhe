"""Canonical JSON (RFC 8785 / JCS) serialisation — ADR-0003.

* object members sorted by their UTF-16 code-unit sequence;
* no insignificant whitespace; strings escaped as in ECMAScript JSON.stringify
  (only ", \\, control characters; non-ASCII emitted as UTF-8);
* numbers serialised as ECMAScript Number.prototype.toString (integers
  beyond ±2^53 and non-finite numbers are rejected).
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
_MAX_SAFE = 2 ** 53


class CanonicalJsonError(ValueError):
    pass


def _string(s: str) -> str:
    out = []
    for ch in s:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _number(n: int | float) -> str:
    if isinstance(n, bool):
        raise CanonicalJsonError("bool is not a number")
    if isinstance(n, int):
        if abs(n) > _MAX_SAFE:
            raise CanonicalJsonError("integer outside IEEE-754 safe range")
        return str(n)
    if not math.isfinite(n):
        raise CanonicalJsonError("non-finite number")
    if n == 0:
        return "0"
    if n.is_integer() and abs(n) < 1e21:
        return str(int(n))
    r = repr(n)  # shortest round-trip digits
    mantissa, _, exp = r.partition("e")
    digits = mantissa.replace("-", "").replace(".", "").lstrip("0") or "0"
    # decimal exponent of the leading digit
    m_int, _, m_frac = mantissa.lstrip("-").partition(".")
    if m_int.strip("0"):
        point = len(m_int.lstrip("0"))
    else:
        point = -(len(m_frac) - len(m_frac.lstrip("0")))
    e = point + (int(exp) if exp else 0)          # value = 0.d1d2… × 10^e
    digits = digits.rstrip("0") or "0"
    k = len(digits)
    sign = "-" if n < 0 else ""
    if k <= e <= 21:
        return sign + digits + "0" * (e - k)
    if 0 < e <= 21:
        return sign + digits[:e] + "." + digits[e:]
    if -6 < e <= 0:
        return sign + "0." + "0" * (-e) + digits
    exp_s = e - 1
    body = digits[0] + ("." + digits[1:] if k > 1 else "")
    return f"{sign}{body}e{'+' if exp_s > 0 else '-'}{abs(exp_s)}"


def canonical_dumps(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_dumps(v) for v in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise CanonicalJsonError("object keys must be strings")
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(_string(k) + ":" + canonical_dumps(value[k]) for k in keys) + "}"
    raise CanonicalJsonError(f"unsupported type {type(value).__name__}")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()
