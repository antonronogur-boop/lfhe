<!-- PO decision received 2026-10-25 15:33 (Europe/Budapest). Stored verbatim (SD-12). -->

PRODUCT OWNER DECISION — CR7-02 APPROVED
Date: 2026-10-25
Project: LFHÉ
Change Request: CR7-02 — Registered output schema delivery to real model providers
DECISION
CR7-02 — APPROVED.
The Product Owner authorises the targeted correction implemented on the `cr7-02` branch.
The evidence demonstrates that the real-provider failures were caused by the request-construction path not transmitting the already registered `output_schema.json` to the model.
The correction has been validated with a real `claude-sonnet-5-5` execution:

* M07 — ASSESSMENT_RECORDED
* M08 — CHALLENGE_RECORDED
* human analytical approval completed
* M09 — REPORT_VERSION_RECORDED
* M10-D + M10-S — PASS_WITH_WARNINGS
* 4 / 4 model outputs schema-valid
* 0 schema-repair runs required
* provider/model/configuration/prompt-version/prompt-hash traceability preserved

AUTHORISED SCOPE
The approved correction is limited to:

* transmitting the registered output schema as trusted request context to the model;
* preserving the existing untrusted-data boundary;
* preserving the existing registered prompt bundles;
* preserving prompt version identifiers and prompt hashes where their files are unchanged;
* preserving existing ingestion and schema validation;
* preserving all human authority, provenance, QA and release semantics.

No other Phase 2 behaviour is authorised for modification.
CLOSED-PHASE STATUS
CR7-02 does not reopen:

* CONTROL GATE 2;
* PHASE 2 generally;
* any other closed control gate.

It is an explicitly authorised forward correction discovered during Phase 7 real-provider validation.
Record the exact affected closed behaviour and the correction in the project documentation and Change Request history.
MERGE AUTHORISATION
You are authorised to:

1. merge the tested `cr7-02` change into `main`;
2. run the complete regression suite;
3. run web tests, TypeScript and production build;
4. run prompt-lock, secret scan and gitleaks;
5. push the resulting commit;
6. require green CI;
7. update the CG7 evidence pack and project status.

Do not extend the merge with unrelated refactoring or feature work.
POST-MERGE VALIDATION
After the merge and green CI:

* rerun `pilot-real-provider` from `main`;
* use `scope = trial_and_benchmark`;
* preserve the resulting trial and benchmark artifacts;
* use the 18-case P7-BM-01 result as the empirical evidence for CG7 criterion 19.

A successful trial alone does not establish M10-S quality.
Criterion 19 may become PASS only from the completed real-provider benchmark evidence.
CONTROL GATE STATUS
This approval does not approve CONTROL GATE 7.
CG7 remains open.
The capability verdict remains:
OPERATIONAL VALUE NOT YET VALIDATED
until the remaining Phase 7 evidence has been collected.
FINAL STATUS
CR7-02 — APPROVED FOR MERGE AND VALIDATION.
Proceed with the targeted merge, full regression, green CI, and the real-provider `trial_and_benchmark` run.
Do not begin a later phase.
