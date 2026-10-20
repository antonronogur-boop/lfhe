# PO Decision — Final CG4 Pre-Closure Action (CR4-01 resolve, CR4-02 close)

- Date: 2026-10-20
- Source: Product Owner message in the implementation session; stored verbatim below (SD-12)
- Scope: SD4-01…SD4-18 approved; CR4-01 resolved by migration 3400 (PO-defined likelihood vocabulary); CR4-02 approved / closed; Phase 5 not authorised

---

PRODUCT OWNER DECISION — FINAL CG4 PRE-CLOSURE ACTION

I reviewed the Phase 4 DEV evidence.

The current DEV result is ACCEPTED as valid evidence for migrations
2700–3300:

- migrations applied: 34/34
- DEV smoke: 42/42 PASS
- Phase 4 smoke checks: 10/10 PASS
- audit hash chain: verified, 120 entries
- pg_cron: active
- optional service_role smoke check not run: NON-BLOCKING

Do not invalidate or discard this DEV evidence.

CONTROL GATE 4 is not yet finally closed only because CR4-01 must be
resolved before the Phase 4 likelihood capability is considered complete.

==================================================
SD4 DECISIONS
==================================================

SD4-01 through SD4-18: APPROVED.

No additional SD4 implementation changes are requested.

==================================================
CR4-01 — APPROVED / RESOLVE NOW
==================================================

The repository contains no higher-authority likelihood vocabulary.

Therefore the Product Owner now defines the LFHÉ Phase 4 canonical
likelihood vocabulary as the following CLOSED ordered set:

1. REMOTE_CHANCE
2. HIGHLY_UNLIKELY
3. UNLIKELY
4. ROUGHLY_EVEN_CHANCE
5. LIKELY
6. HIGHLY_LIKELY
7. ALMOST_CERTAIN

Descriptions:

REMOTE_CHANCE:
Possible, but judged exceptionally unlikely.

HIGHLY_UNLIKELY:
Judged very unlikely.

UNLIKELY:
Judged less likely than not.

ROUGHLY_EVEN_CHANCE:
Competing outcomes are judged approximately equally plausible.

LIKELY:
Judged more likely than not.

HIGHLY_LIKELY:
Judged very likely.

ALMOST_CERTAIN:
Judged overwhelmingly likely.

This is an explicit Product Owner decision.
It is NOT claimed to have been recovered from an earlier specification.

Do NOT add numeric probability bands or percentages.

Existing Phase 4 rules remain authoritative:

- likelihood != analytic confidence;
- likelihood is optional;
- if likelihood is not justified, it must remain null;
- likelihood is permitted only on the already-authorised statement types;
- likelihood rationale remains mandatory;
- final_analytic_confidence remains HUMAN_ONLY.

Implement this using ONE new forward-only migration:

20261011003400_p4_likelihood_vocabulary.sql

Do not modify migrations 2700–3300.

Populate the existing lfhe.likelihood_terms table with exactly these
seven rows, ranks 1–7, descriptions above, and a spec_source referring
to this Product Owner decision.

Do not create an UNKNOWN likelihood term.

==================================================
CR4-01 TEST / SMOKE UPDATE
==================================================

Update the tests so they use the real canonical vocabulary and no longer
insert/remove the synthetic TEST_PROBABLE term.

At minimum prove:

1. exactly seven canonical terms exist;
2. their rank order is exactly 1–7 as specified above;
3. an authorised canonical likelihood is accepted on an eligible
   prospective ANALYTIC_JUDGMENT / IMPLICATION;
4. an unknown likelihood term is rejected;
5. likelihood on a non-permitted statement type is rejected;
6. likelihood without rationale is rejected;
7. M07 input receives exactly the seven canonical terms in rank order;
8. likelihood and analytic confidence remain separate;
9. M07 still cannot set final_analytic_confidence.

Update scripts/supabase_dev_smoke.py:

REPLACE the current:

"P4: likelihood vocabulary empty pending CR4-01"

check with a deterministic exact-vocabulary check for the seven rows
above, including rank order.

Do not add an extra smoke check merely to change the count.

Expected final DEV smoke total remains:

42/42 PASS

Expected final migration count becomes:

35

==================================================
CR4-02 — APPROVED / CLOSED
==================================================

CR4-02 is APPROVED AS CURRENTLY IMPLEMENTED.

For the current Phase 4 implementation:

- trend direction remains human-authored free text;
- trend velocity/speed remains human-authored free text;
- the two remain separate fields;
- trend creation remains HUMAN_ONLY.

No Phase 4 code change is required.

Future condition:

Before any AI-generated or automatically generated authoritative trend
state, or any machine logic that compares, sorts, filters, aggregates or
makes decisions from trend direction/velocity, a controlled vocabulary
must first be explicitly approved and versioned.

Record CR4-02 as CLOSED.

==================================================
CG4 DOCUMENTATION
==================================================

Update:

- docs/specs/ with this PO decision;
- docs/SPEC_INDEX.md;
- docs/PROJECT_STATUS.md;
- docs/assessment-design.md where required;
- docs/phase4-test-traceability.md;
- docs/control-gate-4-report.md;
- docs/cg4-acceptance-metrics.json only if a metric is actually affected.

Record:

CR4-01 — RESOLVED by migration 3400.
CR4-02 — APPROVED / CLOSED.

The earlier DEV evidence remains valid evidence for migrations 2700–3300.

==================================================
FINAL VALIDATION
==================================================

Run:

- complete Python suite;
- Phase 1–3 regressions;
- Phase 4 tests;
- web tests;
- prompt-lock;
- secret scan;
- gitleaks;
- normal CI.

Do not perform another architecture audit.
Do not search for additional CG4 issues.
Do not reopen CG1, CG2 or CG3.
Do not begin Phase 5.

After the correction is committed and CI is green, STOP and return only:

1. corrective/final commit IDs;
2. final test counts;
3. CI result;
4. confirmation CR4-01 RESOLVED;
5. confirmation CR4-02 CLOSED;
6. exact two DEV commands:

python scripts/apply_migrations.py
python scripts/supabase_dev_smoke.py

Expected final DEV state:

35 migrations
42/42 PASS

After that final DEV smoke passes, the only remaining action is the
Product Owner CG4 closure decision.

Do not request any further design decision.
Do not begin Phase 5.