"""Phase 2 pipeline test support: real M02/M03 bundles registered and
activated through the real (human) path, and scripted fake-model outputs."""
from __future__ import annotations

import json

from claims_support import model_configuration
from conftest import REPO_ROOT, grant_role, new_user
from lfhe_shared.prompts import load_bundle, register

PROMPTS = REPO_ROOT / "packages" / "prompts"
FIDELITY_DIMS = ("actor", "action", "attribution", "uncertainty", "modality", "quantity", "unit", "time",
                 "location", "negation", "conditionality", "source_assessment_language")


def activate_real_prompts(pg, modules=("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER")) -> dict:
    """Register (registrar) and activate (ADMIN human) the real 1.0.0 bundles. Idempotent."""
    admin = new_user(pg)
    grant_role(pg, admin, "ADMIN")
    ids = {}
    for module in modules:
        bundle = load_bundle(PROMPTS / module / "1.0.0", repo_root=REPO_ROOT)
        with pg.registrar() as c:
            ids[module] = register(c, bundle, git_commit=None, git_tree_clean=False)
        with pg.as_user(admin) as h:
            current = h.execute("SELECT lfhe.current_prompt_version(%s) AS id", (module,)).fetchone()["id"]
            if str(current) != ids[module]:
                h.execute("SELECT lfhe.activate_prompt_version(%s, 'Phase 2 pipeline test')", (ids[module],))
    return ids


def check(**changed) -> dict:
    out = {d: "PRESERVED" for d in FIDELITY_DIMS}
    out.update(changed)
    out.setdefault("translation_material_mismatch", False)
    out.setdefault("source_language_interpretation_uncertain", False)
    return out


def m02_claim(text: str, exact: str, *, local="C1", language="en", normalised=None, offsets=True, **kw) -> dict:
    start = text.index(exact) if offsets else None
    c = {"claim_local_id": local, "claim_text_original": exact, "claim_text_normalised": normalised or exact,
         "claim_type": "DELIVERY", "source_statement_status": "FACT_REPORTED_BY_SOURCE", "attribution": None,
         "event_date": None, "event_date_confidence": "UNKNOWN", "entities": [], "locations": [], "quantity": None,
         "unit": None, "evidence_type": "OFFICIAL_STATEMENT", "evidence_directness": "DIRECT",
         "source_uncertainty_preserved": True, "potential_contradiction": False,
         "evidence_span_original": {"exact_text": exact, "start": start,
                                    "end": start + len(exact) if offsets else None, "language": language},
         "normalisation_check": check(), "human_review_required": False}
    c.update(kw)
    return c


def m02_output(envelope: dict, claims: list[dict], status="SUCCESS", **kw) -> str:
    task = envelope["task"]
    out = {"module": "M02_CLAIM_EXTRACTOR", "status": status, "warnings": [], "human_review_required": False,
           "result": {"article_snapshot_id": task["article_snapshot_id"],
                      "text_representation_id": task["text_representation_id"], "claims": claims}}
    out.update(kw)
    return json.dumps(out, ensure_ascii=False)


def m03_output(assignments: list[tuple], status="SUCCESS", confidence="MODERATE") -> str:
    return json.dumps({"module": "M03_CLASSIFIER", "status": status, "warnings": [], "human_review_required": False,
                       "result": {"assignments": [{"taxonomy_type": t, "taxonomy_id": i, "target_object_type": "CLAIM",
                                                   "target_object_id": cid, "confidence": conf}
                                                  for t, i, cid, conf in assignments],
                                  "classification_confidence": confidence}})


def source_text(envelope: dict) -> str:
    return envelope["inputs"][0]["content"]["content_original"]


__all__ = ["activate_real_prompts", "check", "m02_claim", "m02_output", "m03_output", "model_configuration",
           "source_text"]
