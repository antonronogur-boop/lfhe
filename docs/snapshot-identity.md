# Snapshot identity semantics (CG1-02)

Two identities are kept apart:

| | What it identifies | Where | Used for |
| --- | --- | --- | --- |
| **A. Source snapshot identity** | the provenance-relevant state of a fetched document | `article_snapshots.source_state` + `source_state_sha256` | duplicate control / versioning |
| **B. Text identity** | the exact original-language text a span can point into | `text_representations.text_sha256` (+ `content_identity_sha256` on the snapshot) | evidence-span stability |

## A. `lfhe-snapshot-state/1`

`source_state_sha256 = SHA-256( RFC 8785 canonical JSON of source_state )`, where
`source_state` contains exactly:

| Field | Meaning |
| --- | --- |
| `final_url` | URL the content was actually served from (after redirects) |
| `media_type` | response media type |
| `content.sha256` / `content.basis` | clean-text SHA-256 (`clean_text`) or raw SHA-256 when no text is extractable (`raw`) |
| `title_original` | title as stated by the document (or the feed if the page has none) |
| `language`, `language_method` | deterministic language assignment |
| `stated_publication[]` | every source-stated publication timestamp: value, field, basis (page and feed/API) |
| `source_updated` | source-stated modification time and its field |
| `discovery` | stable discovery identifiers: `guid`, feed/API `title`, `author` |
| `retention_mode` | representation actually retained |

A **new snapshot version** is created when any of these differs from the latest
version of the article. Earlier versions are never modified.

Deliberately **excluded** (would only create uncontrolled versions): raw bytes
when clean text was extracted (markup, scripts, tracking tokens, whitespace),
response headers (`Date`, `ETag`, …), redirect hops, system retrieval time,
and *derived* values (public availability, date status): those are a
deterministic function of the stated timestamps plus retrieval time, so any
change in a stated input already produces a new version, while the mere
passage of time does not.

`source_state` is stored verbatim, so A can be recomputed independently
(`lfhe_shared.integrity.verify_snapshot_states`, `scripts/object_store_reconcile.py`).
The database does not compute RFC 8785 itself; it enforces presence/format and
takes the duplicate decision under a per-article row lock.

## B. Text identity and evidence spans

Each snapshot version has its own immutable `text_representations` row. When a
new version differs only in provenance (e.g. corrected title or publication
time) the text row has the **same `text_sha256`**, so spans created against
either version resolve to identical text; spans always reference one specific,
immutable representation.

## Object-store ordering

1. Build `source_state`, hash it.
2. `lfhe.snapshot_state_is_current()` (read-only): if the latest version has the
   same state → `DUPLICATE`, **nothing is written** (no object, no row).
3. Otherwise write raw bytes (FULL retention only; write-once, content-addressed).
4. `lfhe.record_snapshot()` re-checks under the article row lock and inserts.

An unreferenced object can therefore only arise from a crash between steps 3
and 4, or two workers racing on the same new state with *different* raw bytes.
Such objects are harmless (hash-named, never overwritten) and are reported by
`scripts/object_store_reconcile.py` (report-only; deletion is an operator
decision).

## Rows created before CG1-02

Snapshots created by the Phase 1 code (if any exist outside test databases)
have no `source_state`; they are not rewritten (immutability). The next
collection of such an article creates a new version carrying a state.
