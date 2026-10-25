# Evaluation material (evaluator-only)

Benchmark definitions and their labels (Phase 7 Baseline §22–§23). This tree is **never** model-reachable:
no prompt bundle, envelope builder, worker or fixture reads it (enforced by `tests/security/test_p7_label_isolation.py`).
Labels are loaded only by the benchmark runner (`tests/pilot/test_p7_benchmark.py`) into the evaluator-only
tables `lfhe.pilot_benchmark_cases` / `lfhe.pilot_benchmark_labels`; exports carry aggregate scores only.

| Benchmark | Material | Cases | Labels |
| --- | --- | --- | --- |
| `p7-bm-01/benchmark.json` (P7-BM-01) | synthetic 'Northland' seeded errors | 18 | 24 |
| `p7-bm-02/benchmark.json` (P7-BM-02) | synthetic 'Northland', PO-approved clean baseline (`docs/specs/PO_Decision_2026-10-25_P7-BM-02_Clean_Baseline.md`; `tests/pilot/bm02_fixture.py`) | 18 | 24 |

P7-BM-01's 'clean' base reused the Phase 4–6 test chain and contains genuine fixture defects (claim attribution vs. report wording,
unsupported judgement); its false-alarm figure is invalid. P7-BM-02 is the valid basis for the false-alarm measurement.
