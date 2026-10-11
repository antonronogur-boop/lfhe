"""Deterministic M01 input building for the claim pipeline (Addendum v1.0 §4).

M01 does not analyse: it reads the immutable original-language snapshot and
text representation and packages them, unchanged, as the M02 envelope input.
It never translates, never generates claims and never infers significance.
The same database state always yields the same envelope (and therefore the
same envelope / input-set hashes).

M03 inputs are the claims (effective, human-reviewed wording where a
MODIFY_AND_APPROVE review exists) plus the closed taxonomy, read from the
database, as a context object identified by its taxonomy version.
"""
from __future__ import annotations

from dataclasses import dataclass

from lfhe_shared.envelopes import EnvelopeItem

M02_MODULE = "M02_CLAIM_EXTRACTOR"
M03_MODULE = "M03_CLASSIFIER"
TAXONOMY_VERSION = "LFHE-TAX-1.2"
PIR_IDS = tuple(f"PIR_0{i}" for i in range(1, 9))


class InputBuildError(ValueError):
    """The requested object cannot be packaged (fail closed; code is stable)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class TaskInputs:
    task: dict
    inputs: list[EnvelopeItem]
    context: list[EnvelopeItem]


def _iso(value):
    return value.isoformat() if value is not None else None


def build_m02_inputs(conn, text_representation_id: str, *, high_impact_context: dict | None = None,
                     report_mode: str = "LIVE") -> TaskInputs:
    row = conn.execute(
        """
        SELECT t.id AS rep_id, t.snapshot_id, t.language AS rep_language, t.is_original_language,
               t.text_content, t.text_sha256, t.char_length, t.representation_type,
               t.preprocessor_name, t.preprocessor_version,
               s.article_id, s.title_original, s.retention_mode_applied, s.publication_datetime,
               s.public_availability_datetime, s.public_availability_basis, s.system_retrieval_datetime,
               s.snapshot_version, a.source_id, a.canonical_url,
               src.name AS source_name, src.canonical_domain, src.source_type::text AS source_type
        FROM lfhe.text_representations t
        JOIN lfhe.article_snapshots s ON s.id = t.snapshot_id
        JOIN lfhe.articles a ON a.id = s.article_id
        JOIN lfhe.sources src ON src.id = a.source_id
        WHERE t.id = %s
        """, (text_representation_id,)).fetchone()
    if row is None:
        raise InputBuildError("TEXT_REPRESENTATION_NOT_FOUND", str(text_representation_id))
    if not row["is_original_language"]:
        raise InputBuildError("NOT_ORIGINAL_LANGUAGE", "only original-language text can be evidence")
    if row["retention_mode_applied"] == "METADATA_ONLY":
        raise InputBuildError("METADATA_ONLY_SNAPSHOT", "metadata-only sources cannot ground claims (K-04)")
    if not row["rep_language"]:
        raise InputBuildError("ORIGINAL_LANGUAGE_UNKNOWN",
                              "the original language is unknown; claims could not be grounded")
    hic = high_impact_context or {"high_impact": False, "high_impact_reasons": []}
    content = {
        "article_id": str(row["article_id"]),
        "article_snapshot_id": str(row["snapshot_id"]),
        "text_representation_id": str(row["rep_id"]),
        "source_id": str(row["source_id"]),
        "title": row["title_original"],
        "language_original": row["rep_language"],
        "content_original": row["text_content"],
        "content_working_translation": None,
        "content_original_sha256": row["text_sha256"],
        "content_original_code_points": row["char_length"],
        "offset_unit": "UNICODE_CODE_POINT",
        "representation_type": row["representation_type"],
        "preprocessor": f"{row['preprocessor_name']}/{row['preprocessor_version']}",
        "publication_datetime": _iso(row["publication_datetime"]),
        "public_availability_datetime": _iso(row["public_availability_datetime"]),
        "public_availability_basis": row["public_availability_basis"],
        "system_retrieval_datetime": _iso(row["system_retrieval_datetime"]),
        "source_metadata": {"name": row["source_name"], "canonical_domain": row["canonical_domain"],
                            "source_type": row["source_type"], "canonical_url": row["canonical_url"],
                            "snapshot_version": row["snapshot_version"]},
    }
    task = {"article_snapshot_id": str(row["snapshot_id"]), "text_representation_id": str(row["rep_id"]),
            "report_mode": report_mode, "high_impact_context": hic}
    return TaskInputs(task, [EnvelopeItem("text_representation", str(row["rep_id"]), content)], [])


def taxonomy_context(conn, version: str = TAXONOMY_VERSION) -> EnvelopeItem:
    items = conn.execute(
        "SELECT id, taxonomy_type::text AS taxonomy_type, label, description FROM lfhe.taxonomy_items "
        "WHERE taxonomy_version = %s ORDER BY taxonomy_type, id COLLATE \"C\"", (version,)).fetchall()
    if not items:
        raise InputBuildError("TAXONOMY_NOT_FOUND", version)
    return EnvelopeItem("taxonomy", version, {"taxonomy_version": version,
                                             "items": [dict(i) for i in items]})


def build_m03_inputs(conn, claim_ids: list[str], *, version: str = TAXONOMY_VERSION) -> TaskInputs:
    if not claim_ids:
        raise InputBuildError("NO_CLAIMS", "nothing to classify")
    rows = conn.execute(
        """
        SELECT c.id, c.claim_text_original, c.language_original, c.attribution, c.event_date,
               c.location_mentions, st.effective_claim_text_normalised, st.effective_claim_type::text AS claim_type,
               st.effective_attribution, st.review_state,
               coalesce((SELECT jsonb_agg(m.mention_text_original ORDER BY m.mention_index)
                         FROM lfhe.entity_mentions m WHERE m.claim_id = c.id), '[]'::jsonb) AS mentions
        FROM lfhe.claims c JOIN lfhe.claim_state st ON st.claim_id = c.id
        WHERE c.id = ANY(%s::uuid[])
        """, (list(claim_ids),)).fetchall()
    found = {str(r["id"]) for r in rows}
    missing = [i for i in claim_ids if str(i) not in found]
    if missing:
        raise InputBuildError("CLAIM_NOT_FOUND", ", ".join(map(str, missing)))
    inputs = []
    for r in rows:
        if r["review_state"] in ("REJECTED", "REPROCESSING_REQUESTED"):
            raise InputBuildError("CLAIM_NOT_CLASSIFIABLE", f"{r['id']} review state {r['review_state']}")
        inputs.append(EnvelopeItem("claim", str(r["id"]), {
            "claim_id": str(r["id"]), "claim_text_normalised": r["effective_claim_text_normalised"],
            "claim_text_original": r["claim_text_original"], "language_original": r["language_original"],
            "claim_type": r["claim_type"], "attribution": r["effective_attribution"],
            "entity_mentions": r["mentions"], "locations": r["location_mentions"], "event_date": r["event_date"]}))
    task = {"taxonomy_version": version, "intelligence_requirements": list(PIR_IDS)}
    return TaskInputs(task, inputs, [taxonomy_context(conn, version)])
