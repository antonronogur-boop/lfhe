"""Phase 7 pilot metrics export (P7-07, P7-09; Baseline §25 tests 18–19).

The export contains measurements and aggregate benchmark scores only:

* no credential, token, key or connection string (checked against the repository secret patterns
  and a forbidden-key list before anything is written);
* no benchmark label content — per-label expected checks / codes / notes never leave the
  evaluator-only tables; only TP / FP / FN counts per layer are exported;
* no model raw output, envelope or prompt text.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

from .capacity import Comparison, CostAssumption, capacity, claim_problems
from .metrics import cycle_metrics

FORBIDDEN_KEYS = re.compile(r"(api[_-]?key|secret|password|passwd|token(?!s)|authorization|credential|db_url|conninfo|"
                            r"expected_check|expected_finding|label_note|raw_output|envelope|system_prompt)", re.IGNORECASE)
SCHEMA = "lfhe-pilot-export/1"


def _patterns():
    path = Path(__file__).resolve().parents[3] / "scripts" / "secret_scan.py"
    spec = importlib.util.spec_from_file_location("lfhe_secret_scan_patterns", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, mod)
    spec.loader.exec_module(mod)
    return mod.PATTERNS


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k
            yield from _walk_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


class ExportRejected(ValueError):
    pass


def export_problems(doc: dict) -> list[str]:
    out = [f"FORBIDDEN_KEY:{p}" for p, k in _walk_keys(doc) if FORBIDDEN_KEYS.search(str(k))]
    text = json.dumps(doc, default=str)
    out += [f"SECRET_PATTERN:{name}" for name, rx in _patterns().items() if rx.search(text)]
    return out


def _jsonable(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, set):
        return sorted(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def benchmark_scores(conn, benchmark_code: str) -> dict:
    """Aggregate TP / FP / FN per layer (D, S separately) + precision / recall; no label content."""
    b = conn.execute("SELECT id FROM lfhe.pilot_benchmarks WHERE code=%s", (benchmark_code,)).fetchone()
    if b is None:
        raise LookupError(benchmark_code)
    rows = conn.execute("SELECT * FROM lfhe.pilot_benchmark_outcomes(%s)", (b["id"],)).fetchall()
    n_cases = conn.execute("SELECT count(*) n FROM lfhe.pilot_benchmark_cases WHERE benchmark_id=%s", (b["id"],)).fetchone()["n"]
    out = {"benchmark": benchmark_code, "cases": n_cases,
           "cases_without_qa_result": len({r["case_code"] for r in rows if r["kind"] == "QA_RESULT_MISSING"})}
    labelled = {r["case_code"] for r in rows if r["kind"] in ("TRUE_POSITIVE", "FALSE_NEGATIVE")}
    out["clean_cases"] = n_cases - len(labelled)
    out["fp_note"] = ("unlabelled findings on seeded cases count as false positives (conservative); "
                      "false_positives_on_clean_cases is the false-alarm rate on unseeded versions")
    for layer in ("D", "S"):
        lr = [r for r in rows if r["layer"] == layer]
        tp = sum(r["kind"] == "TRUE_POSITIVE" for r in lr)
        fn = sum(r["kind"] == "FALSE_NEGATIVE" for r in lr)
        fp = sum(r["kind"] == "FALSE_POSITIVE" for r in lr)
        out[layer] = {"labels": tp + fn, "true_positives": tp, "false_negatives": fn, "false_positives": fp,
                      "findings_produced": tp + fp,
                      "precision": round(tp / (tp + fp), 4) if tp + fp else None,
                      "recall": round(tp / (tp + fn), 4) if tp + fn else None,
                      "critical_misses": sum(r["kind"] == "FALSE_NEGATIVE" and r["critical"] for r in lr),
                      "false_positives_on_clean_cases": sum(r["kind"] == "FALSE_POSITIVE" and r["case_code"] not in labelled
                                                            for r in lr)}
    return out


def cycle_capacity(m: dict, assumption: CostAssumption | None, *, cycles_per_week=None) -> dict | None:
    comp, eff = m.get("comparator"), m["effort"]
    if not comp or comp["method"] == "NONE" or not comp.get("baseline_analyst_seconds") or eff["analyst_active_seconds"] is None:
        return {"computed": False, "reason": "no timed comparator baseline or no analyst timing"}
    c = Comparison(comp["method"], comp["baseline_basis"], comp["comparable_scope"])
    quality_ok = bool(m.get("qa")) and m["qa"]["final_status"] in ("PASS", "PASS_WITH_WARNINGS")
    problems = claim_problems(c, timing_complete=eff["timing_complete"], human_controls_intact=True,
                              quality_not_degraded=quality_ok, prohibited_data_used=False)
    r = capacity(Decimal(comp["baseline_analyst_seconds"]) / 3600, Decimal(str(eff["analyst_active_seconds"])) / 3600, c,
                 assumption, cycles_per_week=cycles_per_week, claim_problem_list=problems)
    return {"computed": True, **{k: _jsonable(v) if isinstance(v, Decimal) else v for k, v in r.__dict__.items()}}


def build_export(conn, *, cycle_codes: list[str] | None = None, benchmark_codes: list[str] | None = None,
                 cost_assumption_code: str | None = None, cycles_per_week=None, generated_at: str) -> dict:
    where = "WHERE code = ANY(%s)" if cycle_codes else ""
    cycles = conn.execute(f"SELECT id, code FROM lfhe.pilot_cycles {where} ORDER BY code",
                          (cycle_codes,) if cycle_codes else ()).fetchall()
    assumption = None
    if cost_assumption_code:
        a = conn.execute("SELECT * FROM lfhe.pilot_cost_assumptions WHERE code=%s", (cost_assumption_code,)).fetchone()
        if a is None:
            raise LookupError(cost_assumption_code)
        assumption = CostAssumption(a["code"], a["currency"], Decimal(a["loaded_hourly_cost"]), Decimal(a["weekly_work_hours"]),
                                    Decimal(a["working_weeks_per_year"]))
    doc = {"schema": SCHEMA, "generated_at": generated_at,
           "cost_assumption": None if assumption is None else {k: _jsonable(v) for k, v in assumption.__dict__.items()},
           "cycles_per_week_assumption": cycles_per_week, "cycles": [], "benchmarks": [],
           "note": "measurement export; capacity value is not cash saving; quality figures are as detected by QA"}
    for c in cycles:
        m = cycle_metrics(conn, str(c["id"]))
        m["capacity"] = cycle_capacity(m, assumption, cycles_per_week=cycles_per_week)
        doc["cycles"].append(m)
    for code in benchmark_codes or []:
        doc["benchmarks"].append(benchmark_scores(conn, code))
    doc = json.loads(json.dumps(doc, default=_jsonable))
    problems = export_problems(doc)
    if problems:
        raise ExportRejected(", ".join(problems))
    return doc
