# Phase 7 — pilot instrumentation, measurement and analysis design

Baseline: `docs/specs/LFHE_Phase7_Authoritative_Baseline_v1.0.md` (SPEC_INDEX 26); PO authorisation SPEC_INDEX 27.
Operator steps: `docs/runbooks/phase7-pilot.md`. Tests: `docs/phase7-test-traceability.md`.

## Principle

The closed Phase 1–6 core is frozen (§4). Phase 7 adds **measurement around it** and never changes it:
migration `20261011004100_p7_pilot_instrumentation.sql` creates new `pilot_*` tables, views and functions
only; no Phase 1–6 object is altered. Pilot functions write only `pilot_*` tables (plus the hash-chained
audit log for low-volume pilot decisions); analytical, QA, approval, security and release records are
only read. A test fingerprints every non-pilot table before and after pilot activity
(`tests/integration/test_p7_pilot.py`). Applied migrations 1–41 are locked by SHA-256
(`database/migrations.lock.json`; `tests/unit/test_migration_lock.py`; DEV smoke check).

## Data model (P7-01)

| Object | Purpose | Notes |
| --- | --- | --- |
| `pilot_cycles` | one end-to-end cycle: code, mode, cutoff, data boundary, input scope, analyst, provider setup, bound report, status / terminal state | mode + cutoff must equal the bound report's (`pilot_bind_report`); LIVE cannot claim replay material; closed cycles immutable |
| `pilot_cycle_model_runs` | exact model runs measured by the cycle | `REPORT_CHAIN` = derived by `pilot_report_chain_model_runs` (M09 versions, pinned / cited M07 versions, their M08 runs, M10-S runs, failed originals of repairs); `TRIAL` = named runs |
| `pilot_model_run_metrics` (view) | provider, model, configuration hash + settings, prompt semver / hash, status, error, latency, tokens, repair link, cost | cost only with an explicit price (`pilot_provider_prices`); otherwise NULL = unknown |
| `pilot_comparators` | comparison method, baseline analyst seconds, basis (timed / documented), comparable scope, reference | one per cycle; method `NONE` allowed but never claimable |
| `pilot_timing_segments` / `pilot_cycle_timing` | active time per user and stage | server clock only (`clock_timestamp()`); one open segment per user; `ended_at ≥ started_at`; segments close once and are never edited |
| `pilot_workload_ratings` | raw NASA-TLX, six dimensions 0–100 | one per user per cycle |
| `pilot_ux_findings` + `pilot_ux_finding_dispositions` | area, severity (BLOCKING / MAJOR / MINOR / ENHANCEMENT), class (§4 eight categories), route; append-only dispositions | an open BLOCKING finding blocks COMPLETED |
| `pilot_cost_assumptions` | currency, loaded hourly cost, weekly hours, working weeks, basis | explicit, immutable, none seeded |
| `pilot_provider_prices` | per-million-token input / output price, effective from, source | explicit, immutable, none seeded |
| `pilot_cash_evidence` | documented cash effects by category (avoided overtime / contractor / hiring, reduced external research, actual cash saving) | never derived from capacity value |
| `pilot_benchmarks` / `_cases` / `_labels` | benchmark → cases bound to exact report version + hash → human-authored labels | labels evaluator-only (PILOT_EVALUATE / `lfhe_evaluator`); kinds limited to truth kinds; a label cannot be derived from a recorded finding |

Completeness: `pilot_cycle_missing_metrics(cycle)` lists what is absent (report not bound / not at a
terminal state, no closed analyst timing, open timer, no comparator, no analyst workload, model runs not
bound or chain runs missing, open BLOCKING UX finding). `pilot_close_cycle(…, 'COMPLETED', …)` fails
closed while the list is non-empty; `STOPPED` keeps the collected evidence with its reason (§8, §27).
Terminal pilot states: latest report version `RELEASED`, `RELEASE_REJECTED`, `SECURITY_REJECTED` or
`CONTENT_REJECTED` (a human gate decided).

RBAC: new role `PILOT_LEAD` (`PILOT_READ`, `PILOT_PARTICIPATE`, `PILOT_MANAGE`, `PILOT_EVALUATE`, plus read
permissions); ANALYST / REVIEWER / SECURITY_REVIEWER / RELEASE_AUTHORITY get `PILOT_READ` +
`PILOT_PARTICIPATE`; ADMIN gets `PILOT_READ` only. No pilot permission confers analytical, QA, approval,
security or release authority; the Phase 6 authority assignment is unchanged (tested). All 16 pilot write
functions are HUMAN_ONLY; the worker can neither call them nor read pilot tables.

## Workspace (P7-02)

`/pilot` (cycle list, completed-cycle count vs. the 6-cycle target, new cycle, cost assumptions, provider
prices) and `/pilot/<id>` (cycle facts, completeness list, analyst time by stage with start / switch /
stop, comparator, report binding, chain-run binding and per-run provider metrics, UX findings and
dispositions, workload, close). No form carries a duration or timestamp for timing.

## Metrics and analysis (P7-07) — `services/pilot/lfhe_pilot`

* `metrics.cycle_metrics` recomputes per cycle: effort (analyst active seconds total / by stage; all
  participants; timing completeness; audited human interactions in the window), throughput (sources,
  articles, claims, events, assessments, candidates, final items in the bound report's chain; per analyst
  hour), report performance (versions, human versions, QA-induced revisions, cutoff → first draft / →
  release, cycle start → release, length, section counts), QA (final status; D and S findings separately),
  quality rates *as detected by QA*, provenance (released manifest re-validated by
  `p6_manifest_problems`), corrections / overrides (modify-and-approve, non-approve gate decisions,
  human report edits), provider metrics per module, UX and workload. Missing values stay `None`.
* `capacity` implements §11 exactly: `analyst_hours_saved`, `capacity_release_percent`,
  `weekly_fte_equivalent` (needs explicit cycles per week), `capacity_value` (needs an explicit cost
  assumption), `annual_capacity_value` (only for a CONTROLLED, claimable weekly figure). Evidence class:
  CONTROLLED only for a controlled method with a timed baseline on comparable scope; otherwise
  OBSERVATIONAL / NO_COMPARATOR. §12 claim rule → `claim_problems`. `cash_saving` only sums documented
  cash evidence. Decimal arithmetic, deterministic.
* `export.build_export` → `scripts/pilot_export.py` (read-only session): cycles, capacity, aggregate
  benchmark scores; refused if any credential pattern or forbidden key (labels, raw output, envelopes,
  credentials) would be exported.
* `provider_trial.run_checks` — §26 admissibility of a run as real-provider evidence (non-test provider,
  provider response id, prompt and configuration traceable to the registry, normal ingestion path, repair
  linked to a failed original, failures not turned into success).

## Benchmark (P7-05)

`evaluation/p7-bm-01/benchmark.json` — 18 synthetic 'Northland' cases (15 seeded errors across
unsupported fact, epistemic strength, attribution, independence, confidence / likelihood, hindsight /
cutoff, OSINT marking, provenance, duplication; 3 clean), 24 human-authored labels (layer, check,
finding code, critical). Built from the Phase 6 acceptance mutations; model-behaviour scripts are
excluded so every case is audited by the configured M10-S. Runner: `tests/pilot/test_p7_benchmark.py`
(throw-away harness). Scores per layer: labels, TP, FN, FP, precision, recall, critical misses, false
positives on clean cases. Unlabelled findings on seeded cases count as FP (conservative). With the
rule-based stand-in the run is regression of the measurement path only; the real M10-S figures come from
the `pilot-real-provider` workflow (or a local run with `LFHE_P7_PROVIDER=anthropic`).

## Benchmark P7-BM-02 (2026-10-25, PO authorisation)

`evaluation/p7-bm-02/benchmark.json` — the same 18 cases / error classes on an internally consistent base
(`tests/pilot/bm02_fixture.py`): claim attributions match the report wording; the key judgement (ROUGHLY_EVEN_CHANCE, LOW)
follows from the two conflicting official statements and cites both; the denial is preserved as a caveat (a contested
judgement cannot be a key judgement under the closed Phase 5 rule). With the test doubles every expected status holds and
neither layer flags the clean cases. Runner: `tests/pilot/test_p7_benchmark.py::test_p7_bm_02`; workflow scope
`benchmark_02_only`. The base must be confirmed error-free by a human evaluator (`docs/p7-bm-02-base-review.md`) before the
real-provider false-alarm figure is used as CG7 evidence.

## Specification deviations (SD7)

| ID | Deviation / interpretation | Reason |
| --- | --- | --- |
| SD7-01 | Pilot objects live in schema `lfhe` with the `pilot_` prefix, a `PILOT MEASUREMENT` comment and their own permissions, not a separate schema | the web client is bound to the exposed `lfhe` schema; distinguishability (§19) is by name, comment, RLS and permission; the worker cannot read them |
| SD7-02 | New role `PILOT_LEAD` for pilot management and benchmark evaluation; ADMIN gets read only | measurement authority separated from analytical / release authority and from technical administration |
| SD7-03 | Analyst time is captured only by server-clock timers; no manual entry or correction | PO: no retrospective inference of active time; a forgotten timer over-counts and must be noted as a measurement UX finding (or the cycle STOPPED) |
| SD7-04 | "Human interactions" = audited human decisions by the cycle analyst in the cycle window; clicks / navigation are captured only as structured UX findings | §21: no high-volume telemetry in the analytical audit trail |
| SD7-05 | Throughput counts are the objects of the bound report's analytical chain, not everything collected in the window | exact, traceable and reproducible; window-wide collection counts are not tied to the cycle |
| SD7-06 | Per-cycle quality rates are "as detected by the final QA result"; ground-truth error rates exist only for the benchmark | §22: model or deterministic findings are never ground truth |
| SD7-07 | The seeded benchmark runs in the throw-away harness (manual workflow / local), never on DEV | seeded corrupt report versions must not enter the DEV analytical tables (§27 stop condition) |
| SD7-08 | Real-provider evidence can come from DEV pilot cycles (worker) and from the manual `pilot-real-provider` workflow (synthetic chain); genuineness is shown by provider, response id and the recorded run context, not cryptographically | §26 allows a controlled DEV / pilot environment; secrets stay in the PO's secret stores |
| SD7-09 | Terminal pilot states: RELEASED, RELEASE_REJECTED, SECURITY_REJECTED, CONTENT_REJECTED | §8 "defined terminal pilot state": a human gate has decided |
| SD7-10 | Workload instrument: raw NASA-TLX (unweighted) | standard, quick, no pairwise weighting session |
| SD7-11 | Annual capacity value only for a CONTROLLED, claimable weekly figure | §9, §11, §12: an observational result is never annualised into a value claim |
| SD7-12 | The cycle cutoff is copied from and must equal the report's cutoff; no separate pilot cutoff rule | §7 / test 3: closed REPLAY / LIVE cutoff semantics are reused, not redefined |
