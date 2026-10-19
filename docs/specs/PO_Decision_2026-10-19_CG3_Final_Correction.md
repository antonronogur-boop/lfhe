<!-- PO decision received 2026-10-19 (final CG3 correction: knowledge-bound lineage retractions). Stored verbatim (SD-12). -->

PRODUCT OWNER DECISION — FINAL CG3 CORRECTION

I reviewed the corrective Phase 3 delivery.

CG3-02: RESOLVED / ACCEPTED.
CG3-03: RESOLVED / ACCEPTED.

CG3-01 is accepted except for one remaining narrow as-of issue:
the semantics introduced as SD3-13.

==================================================
SD3-12
==================================================

SD3-12: APPROVED.

For human-created event versions and event-state decisions, the
authoritative knowledge bound is the stored evidence set:

- member claims;
- consumed/predecessor event versions;
- other explicitly stored evidence dependencies.

Human-authored title/description are treated as analyst summaries of
that bounded evidence set.

No additional semantic-proof mechanism or analyst attestation is
required for Phase 3.

==================================================
SD3-13
==================================================

SD3-13 AS CURRENTLY IMPLEMENTED: NOT APPROVED.

A lineage retraction must NOT automatically apply retroactively to
every historical REPLAY merely because the retraction exists today.

The current unconditional logic equivalent to:

EXISTS(claim_lineage_retraction) -> lineage unusable

creates hindsight leakage.

A retraction can remove a dependence and therefore increase the
apparent number of independent evidentiary groups. A retraction based
on evidence obtained after historical cutoff T must not change what
was knowable at T.

This is a direct application of the already-approved CG3-01 rule:

"No post-cutoff evidence may be silently used to resolve lineage,
event identity or contradiction."

==================================================
REQUIRED CORRECTION — ONLY THIS ISSUE
==================================================

Make lineage retractions knowledge-bound / as-of aware.

Use one new forward-only migration. Do not modify migrations 1800–2500.

Required semantics:

1. A lineage itself remains usable at cutoff T when its own evidence
   basis is eligible at T, unless a retraction is also eligible at T.

2. A retraction affects a historical REPLAY only when the evidence
   basis supporting that retraction is itself cutoff-eligible for T.

3. A retraction decision may be recorded after T and still apply to
   REPLAY(T) when it relies exclusively on evidence already eligible
   at T.

4. A retraction based on evidence that became eligible only after T
   must NOT affect REPLAY(T).

5. A human retraction without a reproducible evidence basis must NOT
   retroactively alter REPLAY.

6. Do not use retraction created_at alone as the historical knowledge
   criterion.

Implement an append-only evidence binding for lineage retractions
(e.g. claim/article evidence objects), or an equivalent design that
satisfies the above rules.

Update lineage_usable() so it evaluates whether the retraction itself
is usable for the requested report_mode/information_cutoff.

==================================================
MANDATORY REGRESSION TESTS
==================================================

Add only the tests required for this correction:

A. lineage valid from cutoff-eligible evidence;
   retraction based on post-cutoff evidence;
   REPLAY before that evidence -> lineage remains usable.

B. same case after the later evidence becomes cutoff-eligible
   -> retraction applies.

C. retraction recorded after cutoff but based entirely on
   cutoff-eligible evidence
   -> retraction applies to that REPLAY.

D. retraction without evidence basis
   -> does not retroactively alter REPLAY.

E. independence-group calculation follows the same as-of behaviour
   and does not gain false historical independence from a later
   retraction.

Run the complete existing regression suite afterward.

==================================================
SCOPE CONTROL
==================================================

Do NOT:

- perform another general Phase 3 audit;
- search for additional CG3 changes;
- reopen CG2;
- modify CG3-02 or CG3-03;
- introduce another Phase 3 requirement;
- begin Phase 4.

This is the final targeted Phase 3 code correction.

Update:

- the migration;
- affected tests;
- phase3-test-traceability;
- CG3 acceptance metrics;
- corrective report;
- final CG3 report;
- PROJECT_STATUS.

If the correction passes the complete suite, report SD3-13 as replaced
by the following approved semantics:

"Lineage retractions are themselves knowledge-bound. A retraction
affects a historical run only when its supporting evidence is eligible
for that run's cutoff."

After the correction is complete and CI is green, STOP and provide the
final delivery archive/hash plus the exact DEV migration + smoke
commands.

Do not request another Product Owner design decision.
Do not begin Phase 4.