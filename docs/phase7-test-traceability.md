# Phase 7 — test traceability (Baseline §25, §26, §30)

Automated tests prove the instrumentation; they are **not** pilot evidence. Real-provider quality, browser
usability and the pilot cycles are evidenced only by the DEV / pilot runs (CG7 report).

## §25 minimum automated tests

| # | Requirement | Test |
| --- | --- | --- |
| 1 | pilot records cannot alter authoritative analytical state | `tests/integration/test_p7_pilot.py::test_pilot_cycle_end_to_end_…` (md5 fingerprint of every non-pilot table before / after pilot timing, UX, workload, comparator writes); pilot functions write only `pilot_*` (migration review) |
| 2 | pilot records bind to valid referenced objects | same test (report binding, exact chain model runs = `pilot_report_chain_model_runs`, unknown TRIAL run refused `PILOT_MODEL_RUN_UNKNOWN`); FK on every reference; benchmark cases FK to (version id, hash) |
| 3 | REPLAY cutoff preserved | `test_mode_and_cutoff_must_match_the_report_and_timing_is_ordered` (`PILOT_MODE_OR_CUTOFF_MISMATCH`); benchmark REPLAY-early case BM01-Q21 (QA-04 / QA-17 POST_CUTOFF_EVIDENCE) |
| 4 | LIVE / REPLAY clearly distinguished | same test (mode mismatch refused; LIVE + replay material refused by CHECK); metrics carry `cycle.mode`; web `pilot.test.ts` |
| 5 | timing records valid and ordered | same test (server clock; `ended_at ≥ started_at`; stage switch closes the open segment) |
| 6 | negative durations impossible | same test (CHECK violation on a negative segment; a closed segment cannot be rewritten; no pilot function takes a duration / interval argument) |
| 7 | missing required pilot metrics detected | `test_pilot_cycle_end_to_end_…` (`pilot_cycle_missing_metrics`; COMPLETED refused `PILOT_MEASUREMENT_INCOMPLETE`; complete → `missing == []`) |
| 8 | provider metrics bind to exact model_run | same test (bound M07 / M08 / M09 / M10-S runs equal the chain; M09 run = the version's `created_by_model_run_id`; prompt hash, config hash, latency present; no price → cost NULL); `tests/pilot/test_p7_provider_trial.py` |
| 9 | benchmark labels do not enter model input | `tests/pilot/test_p7_benchmark.py` (every rendered system + message + envelope text recorded; no label note, case code or benchmark code in it; labels invisible to analyst and worker); `tests/security/test_p7_label_isolation.py` (model path never references pilot data / evaluation tree; label notes absent from every model-reachable file) |
| 10 | model output cannot become benchmark truth | `test_p7_benchmark.py` (`PILOT_LABEL_KIND_NOT_TRUTH` for MODEL_FINDING / DETERMINISTIC_FINDING; `PILOT_LABEL_FROM_FINDING`; label kinds restricted by CHECK) |
| 11 | loaded hourly cost is explicit configuration | `test_explicit_cost_assumptions_and_separated_cash_semantics` (nothing seeded; analyst cannot record; zero refused; immutable; `MissingAssumption` without an assumption); web `CostAssumptionSchema` |
| 12 | capacity value calculation deterministic | same test (exact Decimal results, repeated equality); `test_export_is_reproducible_and_clean` (two exports identical); `cycle_metrics` repeated equality |
| 13 | cash-saving and capacity-value semantics separated | same test (`cash_saving is None` without evidence; cash summed only from evidence records; semantics string) |
| 14 | pilot comparison method recorded | `test_pilot_cycle_end_to_end_…` (comparator in metrics; missing comparator blocks COMPLETED); observational vs controlled classification test; web `ComparatorSchema` |
| 15 | Phase 1–6 regression unchanged | full suite (`python -m pytest`) — every Phase 1–6 test unchanged and green |
| 16 | human-only controls unchanged | `test_pilot_rbac_and_human_only_controls_unchanged` (Phase 6 authority set identical; PILOT_LEAD has no analytical / QA / approval / security / release permission; 16 pilot functions HUMAN_ONLY; worker / service_role / anon refused); `tests/security/test_p6_rbac.py` unchanged |
| 17 | audit integrity preserved | `test_pilot_cycle_end_to_end_…` (`verify_chain` after pilot activity); DEV smoke hash-chain check |
| 18 | no secrets in pilot exports | `test_export_is_reproducible_and_clean` (`export_problems` = repository secret patterns + forbidden keys; injected key refused `ExportRejected`); workflow secret-scans its results |
| 19 | pilot exports contain no prohibited benchmark answer material | `benchmark_scores` exports aggregate counts only (`export_problems(scores) == []`); forbidden keys include label fields |
| 20 | new migrations are forward-only | `tests/unit/test_migration_lock.py` (41 locked SHA-256 unchanged; every new file sorts after the lock); DEV smoke "applied migrations match the lock" |

## §26 real-provider acceptance

| Requirement | Mechanism |
| --- | --- |
| genuine provider call; exact model id / configuration; prompt version / hash traceable; model_run exists; normal ingestion path; repair separately recorded; failure not converted | `lfhe_pilot.provider_trial.run_checks`; regression `test_provider_trial_checks_reject_test_doubles` (test double → `TEST_DOUBLE_PROVIDER`, `NO_PROVIDER_RESPONSE_ID`; real adapter with stubbed HTTP → admissible structure, tokens, latency) and `tests/pilot/test_p7_trial_flow.py` (full M07 → M10-S flow incl. repair link) |
| reproducible record in the controlled environment | `.github/workflows/pilot-real-provider.yml` (manual; repository secret; artifact) and DEV worker runs bound to pilot cycles |

## Web (vitest)

`apps/web/tests/pilot.test.ts`: vocabularies mirror the migration enums; timer contract has no duration /
timestamp; LIVE cannot claim replay material; comparator rules; cost / price inputs explicit; UX finding
parsing; timing aggregation; completeness labels; disposition history.
