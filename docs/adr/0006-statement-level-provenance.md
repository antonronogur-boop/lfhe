# ADR-0006 — Statement-level provenance anchored in original-language snapshots

**Status:** Accepted (foundation in Phase 1, claims from Phase 2)

## Decision
The provenance chain is
SOURCE → ORIGINAL-LANGUAGE ARTICLE_SNAPSHOT → ORIGINAL-LANGUAGE EXACT EVIDENCE
SPAN → CLAIM → ASSESSMENT_STATEMENT → REPORT_ITEM_STATEMENT → CANONICAL REPORT
VERSION + HASH → QA → HUMAN APPROVALS → RELEASE MANIFEST → RELEASED REPORT.

## Phase 1 foundation
- `article_snapshots` are immutable; a content revision creates a new snapshot
  version, the old one is preserved.
- `text_representations` hold the deterministic canonical clean text of the
  **original-language** snapshot, keyed by preprocessor name + version and
  hashed. Evidence-span offsets (Phase 2) are Unicode code-point offsets into
  this immutable text. A new preprocessor version creates a new
  representation; existing offsets never move.
- `lfhe_shared.spans.resolve_span()` implements the QA-D18 resolution rule so
  Phase 2 can ground claims without redesign.
- Translations are never stored as a text representation of the snapshot;
  they are auxiliary objects (Prompt Pack v1.2.2).
