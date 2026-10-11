# ADR-0007 — Gold-standard answer-key isolation

**Status:** Accepted (enforcement grows with Phase 4)

## Decision
- GS-001 answer-key material (expected claims/events/assessments/report,
  scoring notes and the benchmark document itself) is stored **outside** this
  repository's pipeline-readable tree — in a separate evaluator-only private
  repository or bucket.
- Only materialised raw input (original-language snapshots with availability
  evidence) and approved, cutoff-eligible baseline / reference-context objects
  may enter a TEST run.
- `/tests/gold-standard` is excluded from worker images.
- No GS-001-specific content may appear in prompts, few-shot examples or test
  fixtures (Handoff §53 P). Phase 1 fixtures are synthetic and topic-neutral.
- GS-001 is a regression HISTORICAL REPLAY benchmark, not a blind evaluation.
