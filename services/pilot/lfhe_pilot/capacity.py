"""Phase 7 capacity / economic calculations (Baseline §11, §12; P7-07).

Deterministic Decimal arithmetic over measured inputs. Rules:

* capacity released and cash saved are different quantities; ``capacity_value`` is computed from
  analyst hours and an explicit cost assumption, ``cash_saving`` only ever from documented cash
  evidence records — it is never derived from capacity value;
* every monetary input (loaded hourly cost, work week, working weeks) is an explicit
  ``CostAssumption`` supplied by the caller; there is no default;
* a productivity improvement is claimable only under the §12 rule; otherwise the result carries
  the reasons it is not, and an observational comparison is never labelled controlled (§9).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal

CONTROLLED_METHODS = frozenset({"MATCHED_MANUAL_CONTROL", "CONTROLLED_ANALYST_BENCHMARK", "EQUIVALENT_TASK_WITHOUT_LFHE"})
COMPARATOR_METHODS = frozenset({"PRIOR_DOCUMENTED_MANUAL_WORKFLOW", "MATCHED_HISTORICAL_CYCLE", "NONE"}) | CONTROLLED_METHODS
CASH_CATEGORIES = ("AVOIDED_OVERTIME", "AVOIDED_CONTRACTOR_EXPENDITURE", "AVOIDED_FUTURE_HIRING",
                   "REDUCED_EXTERNAL_RESEARCH_COST", "ACTUAL_CASH_SAVING")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


class MissingAssumption(ValueError):
    """An economic value was requested without an explicit cost assumption."""


@dataclass(frozen=True)
class CostAssumption:
    code: str
    currency: str
    loaded_hourly_cost: Decimal
    weekly_work_hours: Decimal
    working_weeks_per_year: Decimal

    def __post_init__(self):
        for name in ("loaded_hourly_cost", "weekly_work_hours", "working_weeks_per_year"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or value <= 0:
                raise MissingAssumption(f"{name} must be an explicit positive Decimal")


@dataclass(frozen=True)
class Comparison:
    method: str
    baseline_basis: str | None
    comparable_scope: bool

    def __post_init__(self):
        if self.method not in COMPARATOR_METHODS:
            raise ValueError(f"unknown comparator method {self.method!r}")


def evidence_class(c: Comparison) -> str:
    """CONTROLLED only for a controlled method with a timed baseline on a comparable scope (§9)."""
    if c.method == "NONE":
        return "NO_COMPARATOR"
    if c.method in CONTROLLED_METHODS and c.baseline_basis == "TIMED_MEASUREMENT" and c.comparable_scope:
        return "CONTROLLED"
    return "OBSERVATIONAL"


def claim_problems(c: Comparison, *, timing_complete: bool, human_controls_intact: bool, quality_not_degraded: bool,
                   prohibited_data_used: bool) -> list[str]:
    """§12 productivity claim rule; empty list = a measured improvement may be claimed."""
    out = []
    if c.method == "NONE":
        out.append("COMPARISON_METHOD_NOT_DOCUMENTED")
    if not c.comparable_scope:
        out.append("WORKLOAD_SCOPE_NOT_COMPARABLE")
    if not timing_complete:
        out.append("TIMING_DATA_INCOMPLETE")
    if not human_controls_intact:
        out.append("HUMAN_QUALITY_CONTROLS_REMOVED")
    if not quality_not_degraded:
        out.append("OUTPUT_QUALITY_DEGRADED")
    if prohibited_data_used:
        out.append("PROHIBITED_DATA_USED")
    return out


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        raise TypeError("use Decimal or int, not float")
    return Decimal(x)


@dataclass(frozen=True)
class CapacityResult:
    baseline_analyst_hours: Decimal
    lfhe_analyst_hours: Decimal
    analyst_hours_saved: Decimal
    capacity_release_percent: Decimal | None
    weekly_fte_equivalent: Decimal | None
    capacity_value: Decimal | None
    annual_capacity_value: Decimal | None
    currency: str | None
    cost_assumption_code: str | None
    evidence_class: str
    claimable: bool
    claim_problems: list[str] = field(default_factory=list)
    cash_saving: dict | None = None
    semantics: str = "capacity released for higher-value work; not a cash saving and not a headcount reduction"


def capacity(baseline_hours, lfhe_hours, comparison: Comparison, assumption: CostAssumption | None = None, *,
             cycles_per_week=None, claim_problem_list: list[str] | None = None,
             cash_evidence: list[dict] | None = None) -> CapacityResult:
    """§11 core calculations. ``cycles_per_week`` (explicit) is needed for the weekly FTE figure;
    annualisation is produced only for a CONTROLLED, claimable weekly figure."""
    base, lfhe = _d(baseline_hours), _d(lfhe_hours)
    if base <= 0 or lfhe < 0:
        raise ValueError("baseline hours must be > 0 and LFHÉ hours >= 0")
    saved = base - lfhe
    pct = (saved / base * 100).quantize(Q2, ROUND_HALF_EVEN)
    problems = list(claim_problem_list or [])
    cls = evidence_class(comparison)
    claimable = not problems and cls != "NO_COMPARATOR"
    fte = value = annual = None
    if assumption is not None:
        value = (saved * assumption.loaded_hourly_cost).quantize(Q2, ROUND_HALF_EVEN)
        if cycles_per_week is not None:
            weekly_saved = saved * _d(cycles_per_week)
            fte = (weekly_saved / assumption.weekly_work_hours).quantize(Q4, ROUND_HALF_EVEN)
            if cls == "CONTROLLED" and claimable:
                annual = (weekly_saved * assumption.loaded_hourly_cost * assumption.working_weeks_per_year).quantize(
                    Q2, ROUND_HALF_EVEN)
    return CapacityResult(base, lfhe, saved, pct, fte, value, annual, assumption.currency if assumption else None,
                          assumption.code if assumption else None, cls, claimable, problems,
                          cash_saving(cash_evidence) if cash_evidence is not None else None)


def capacity_value(hours_saved, assumption: CostAssumption | None) -> Decimal:
    if assumption is None:
        raise MissingAssumption("capacity value requires an explicit cost assumption")
    return (_d(hours_saved) * assumption.loaded_hourly_cost).quantize(Q2, ROUND_HALF_EVEN)


def cash_saving(evidence: list[dict]) -> dict:
    """Sum of documented cash evidence per category and currency; nothing is estimated."""
    out: dict[str, dict[str, Decimal]] = {}
    for e in evidence:
        if e["category"] not in CASH_CATEGORIES:
            raise ValueError(f"unknown cash category {e['category']!r}")
        cur = out.setdefault(e["currency"], {k: Decimal("0.00") for k in CASH_CATEGORIES})
        cur[e["category"]] += _d(e["amount"]).quantize(Q2)
    return out
