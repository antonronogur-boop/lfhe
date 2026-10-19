<!-- PO decision received 2026-10-19 (Control Gate 3 targeted corrective pass). Stored verbatim (SD-12). -->

CONTROL GATE 3 — TARGETED CORRECTIVE PASS

The Product Owner has reviewed the delivered Phase 3 archive.

SD3-01 through SD3-11 are APPROVED.

However, Control Gate 3 is NOT YET APPROVED because three material
implementation defects were found against the already-approved
Phase 3 baseline.

These are the ONLY issues to address in this corrective pass.

Do not perform another general architecture review.
Do not reopen CG2.
Do not begin Phase 4.
Do not apply the current Phase 3 migrations to DEV yet.
Do not modify already committed migrations 1800–2200.
Use forward-only corrective migrations.

==================================================
CG3-01 — REPLAY / CUTOFF AS-OF CONTEXT LEAKAGE
==================================================

The current Phase 3 implementation is not sufficiently as-of aware.

Observed problem:

1. event_inputs._claims uses the CURRENT result of
   lfhe.claim_independence_group(claim_id).

2. _lineage_context reads CURRENT active_claim_lineage without an
   information-cutoff / knowledge-as-of filter.

3. candidate_events uses CURRENT event_heads:
   - current head version;
   - current title / description;
   - current event dates / locations;
   - current event state;
   - current merge/supersede successor state.

It only filters the claims inside that current event version by cutoff.

Therefore a historical REPLAY can receive event or lineage state that
was established using later information.

This violates the existing Phase 3 baseline rule:

"No post-cutoff evidence may be silently used to resolve lineage,
event identity or contradiction."

CORRECTION REQUIRED:

Introduce explicit as-of / knowledge-bound handling for authoritative
lineage and event context.

The implementation design is yours, but the following behaviours are
mandatory:

A. REPLAY lineage context

For a REPLAY with information_cutoff T, M04/M05 may only receive
validated lineage that is provably based on evidence eligible at T.

A current lineage decision must not automatically become historical
knowledge merely because it exists in the database today.

Human-recorded lineage without a provable knowledge/evidence bound
must not be silently used in REPLAY.

Do NOT use created_at <= cutoff as the sole rule, because processing
and human validation are explicitly allowed after the information
cutoff when operating on eligible evidence.

B. REPLAY independence groups

The independence group supplied to M05 must be computed from the
lineage set eligible for that run/cutoff, not from the unrestricted
current active lineage graph.

C. REPLAY event context

For a REPLAY at cutoff T, M05 must not receive the current event head
if that head contains knowledge introduced after T.

It must receive a cutoff-eligible/as-of event representation, or no
event context if no such representation can be proven.

A later event version must not leak later:

- title;
- description;
- event date;
- location;
- claim membership;
- lifecycle state;
- merge/split/supersede outcome

into an earlier replay.

D. Human actions

Where a human lineage/event decision may be reused in historical
processing, it must have a reproducible knowledge/evidence bound.

If that bound cannot be established, fail closed for REPLAY rather
than treating the current decision as historical knowledge.

Add regression tests proving at minimum:

1. v1 exists from pre-cutoff evidence.
2. v2 later adds a post-cutoff claim and changes title/description/location.
3. REPLAY between v1 and v2 sees v1-equivalent context only, never v2 fields.
4. A later CONFIRMED/REJECTED state does not leak backwards.
5. A later MERGE or SUPERSEDE does not alter the earlier replay context.
6. A lineage relationship established using later evidence does not enter
   an earlier replay independence calculation/context.
7. Processing timestamp after cutoff is still allowed when the evidence
   itself is cutoff-eligible.

==================================================
CG3-02 — SPLIT PARENT REMAINS OPEN WITHOUT RETAINED EVENT
==================================================

Current split_event behaviour allows:

- all claims to be redistributed into child events;
- retained = null;

while the original parent still remains an open event with its previous
head and previous complete claim set.

event_is_open does not treat SPLIT_INTO as terminal.

This can leave duplicate current representations after a completed split.

CORRECTION REQUIRED:

Define and enforce these semantics:

1. SPLIT WITH RETAINED:
   - parent receives the retained new version;
   - parent may remain open as the retained remainder;
   - child events receive the redistributed claims.

2. FULL SPLIT WITHOUT RETAINED:
   - parent ID and all historical versions remain preserved;
   - parent -> children SPLIT_INTO lineage remains preserved;
   - parent is no longer considered an open/current event for future M05
     candidate selection or normal update operations;
   - no old claim membership is presented as current after the full split.

Do not delete or rewrite the old parent versions.

A one-to-many split does not need to make resolve_event(parent) return
one arbitrary child. Historical resolution may remain relationship-based.

Add tests proving:

- a full split parent is no longer an M05 candidate;
- update_event on a fully split parent is rejected;
- retained split parent remains valid/current only with the retained
  claim set;
- historical parent versions and SPLIT_INTO relations remain intact;
- no claim is lost and no old pre-split membership is presented as
  current state.

==================================================
CG3-03 — EXTERNAL ORIGIN NAME-ONLY AUTO-COLLAPSE
==================================================

Migration 2200 currently reuses the earliest external_origin solely by:

normalise_entity_name(name)

This can silently collapse two genuinely different external origins with
the same normalised name.

That is not acceptable for a system whose core rule is that dependence
must not be inferred without evidence.

CORRECTION REQUIRED:

Remove automatic name-only identity collapse.

Safe behaviour:

- If an already-existing external_origin_id is explicitly selected by the
  human reviewer, reuse that exact origin.
- If a canonical URL is present, automatic reuse may occur only when the
  identity evidence is unambiguous, including a matching canonical URL.
- A matching normalised name alone is NOT sufficient evidence that two
  external origins are the same.
- When identity is ambiguous, preserve the distinction / require explicit
  human selection rather than automatically collapsing independence.

The L3 acceptance case with a common named origin and no URL must still be
supported, but the common identity must be established explicitly by the
human reviewer rather than inferred only by equal names.

Add tests for:

1. same name + same explicit origin selected by human -> one group;
2. same name + different URLs -> remain distinct;
3. same name + no URL + no explicit human reuse -> no automatic collapse;
4. ambiguous identity -> no false dependence;
5. existing L3 common-origin behaviour remains possible through explicit
   human validation.

==================================================
CONTROL / DELIVERY
==================================================

Implement these corrections as forward-only migrations and minimal code
changes.

Update:

- Phase 3 tests;
- phase3-test-traceability;
- lineage-events documentation;
- CG3 acceptance metrics where affected;
- control-gate-3-report.md;
- PROJECT_STATUS.

Run:

- complete Python suite;
- web suite;
- prompt-lock;
- secret scan / gitleaks;
- Phase 1 + Phase 2 regressions.

Do NOT perform the DEV migration/smoke yet.

Return:

1. TARGETED CG3 CORRECTIVE REPORT;
2. updated final CG3 report;
3. delivery archive + SHA-256;
4. exact commits and CI result.

The report must explicitly state whether CG3-01, CG3-02 and CG3-03 are
RESOLVED.

Then STOP.

Do not begin Phase 4.