<!-- PO decision received 2026-10-23 17:30 (Europe/Budapest). Stored verbatim (SD-12). -->

PRODUCT OWNER DECISION — CONTROL GATE 6 TARGETED CORRECTION

The DEV Phase 6 deployment is successful:

- migrations: 40/40
- DEV smoke: 61/61 PASS
- Phase 6 DEV checks: 11/11 PASS
- audit hash chain: PASS, 136 entries
- pg_cron: active
- optional service-role smoke remains NON-BLOCKING

The Product Owner has reviewed SD6-01 through SD6-19.

DECISION:

- SD6-01 … SD6-09: APPROVED
- SD6-10: NOT APPROVED AS CURRENTLY IMPLEMENTED — one targeted correction is required
- SD6-11 … SD6-19: APPROVED

No other Phase 6 deviation requires corrective work.

CONTROL GATE 6 is placed on HOLD for this single targeted correction only.

Do NOT reopen Phase 6 generally.
Do NOT perform another architecture audit.
Do NOT reopen CG1–CG5.
Do NOT introduce additional CG6 criteria.
Do NOT modify already-applied migrations 3800 or 3900.
Do NOT begin Phase 7.

==================================================
CR6-01 — RELEASE MANIFEST BASELINE VERSION IDS
==================================================

The previously approved Module Prompt Pack delta-audit PG-07 explicitly requires:

`baseline_version_ids` in the release manifest.

This requirement predates Phase 6 and is not a new Product Owner requirement.

The current Phase 6 manifest implementation, as documented in SD6-10, does not explicitly preserve `baseline_version_ids`.

Therefore CR6-01 is opened.

Required correction:

1. Add the exact baseline version ID(s) actually used by the released analytical chain to the canonical release manifest.

Use the explicit manifest field:

`baseline_version_ids`

2. The field must be derived from the exact approved analytical objects used by the report.

Do not infer or fabricate baseline IDs.

3. The manifest must preserve all distinct baseline versions actually contributing to the released report.

4. Ordering must be deterministic.

5. Manifest JCS and SHA-256 must include this field.

6. Release manifest completeness validation must fail closed if a baseline version is required by an included analytical object but is missing from `baseline_version_ids`.

7. Release eligibility / manifest validation must ensure that the referenced baseline versions:

- exist;
- are the exact versions referenced by the analytical chain;
- satisfy the already-implemented cutoff eligibility rules.

8. Do not introduce new baseline semantics.

This correction is manifest provenance only.

9. Do not add additional speculative manifest fields solely because Prompt Pack v1.2.1 §11 is unavailable.

The only additional higher-authority manifest requirement currently recovered and proven is `baseline_version_ids`.

==================================================
MIGRATION RULE
==================================================

Migrations 3800 and 3900 have already been applied to DEV.

They are immutable.

Implement CR6-01 using a NEW forward-only migration after 3900.

Do not edit 3800 or 3900.

==================================================
TESTS
==================================================

Add focused tests proving at minimum:

1. manifest contains `baseline_version_ids`;
2. the IDs correspond exactly to baselines used by the released analytical provenance;
3. multiple contributing baselines are deduplicated and deterministically ordered;
4. missing required baseline ID blocks manifest/release;
5. unknown baseline ID blocks release;
6. post-cutoff/ineligible baseline remains blocked under the existing M10-D semantics;
7. manifest hash changes if `baseline_version_ids` changes;
8. SQL/Python JCS/hash parity remains valid;
9. released manifest remains immutable;
10. all existing Phase 1–6 regression tests remain green.

Extend DEV smoke only as necessary to prove the manifest requirement.

==================================================
CG6
==================================================

After implementing CR6-01:

- rerun the complete Python test suite;
- rerun web tests / TypeScript / production build;
- rerun prompt lock;
- rerun secret scan;
- rerun gitleaks;
- obtain green CI;
- update `docs/phase6-test-traceability.md`;
- update `docs/qa-release-design.md`;
- update `docs/control-gate-6-report.md`;
- update `docs/PROJECT_STATUS.md`;
- record CR6-01 as RESOLVED.

Report:

- new migration filename;
- resulting migration count;
- updated test totals;
- updated expected DEV smoke total;
- exact DEV commands.

Then STOP.

Do not declare CG6 approved.

The Product Owner will run the new DEV migration/smoke and make the final CONTROL GATE 6 decision.

Phase 7 remains NOT AUTHORISED.