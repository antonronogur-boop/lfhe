"""P2-03 — M02/M03 prompt bundles, output schemas and deterministic M01 inputs."""
import json

import pytest
from jsonschema import Draft202012Validator

from claims_support import candidate, extraction_run, ingest, make_text_snapshot
from conftest import REPO_ROOT
from lfhe_orchestrator.claim_inputs import (InputBuildError, TAXONOMY_VERSION, build_m02_inputs, build_m03_inputs,
                                            taxonomy_context)
from lfhe_shared.envelopes import TaskEnvelope
from lfhe_shared.prompts import load_bundle

pytestmark = pytest.mark.db
PROMPTS = REPO_ROOT / "packages" / "prompts"


def bundle(module):
    return load_bundle(PROMPTS / module / "1.0.0", repo_root=REPO_ROOT)


def db_enum(pg, name):
    with pg.admin() as c:
        return [r["e"] for r in c.execute(f"SELECT unnest(enum_range(NULL::lfhe.{name}))::text AS e").fetchall()]


def test_bundles_are_valid_locked_and_not_fixtures():
    for module in ("M02_CLAIM_EXTRACTOR", "M03_CLASSIFIER"):
        b = bundle(module)
        assert not b.is_test_fixture and b.module_version == "MPP-1.2.2+P2-ADDENDUM-1.0"
        Draft202012Validator.check_schema(b.output_schema)
        lock = json.loads((PROMPTS / "prompt-lock.json").read_text())
        assert lock["bundles"][f"{module}/1.0.0"] == b.content_hash
        assert "untrusted" in b.files["system.md"].lower()


def test_m02_schema_enums_match_database_vocabularies(pg):
    claim = bundle("M02_CLAIM_EXTRACTOR").output_schema["properties"]["result"]["properties"]["claims"]["items"]["properties"]
    assert claim["claim_type"]["enum"] == db_enum(pg, "claim_type")
    assert claim["source_statement_status"]["enum"] == db_enum(pg, "source_statement_status")
    assert claim["evidence_type"]["enum"] == db_enum(pg, "evidence_type")
    assert claim["evidence_directness"]["enum"] == db_enum(pg, "evidence_directness")
    assert claim["entities"]["items"]["properties"]["entity_type"]["enum"] == db_enum(pg, "entity_type") + [None]


def test_m03_schema_taxonomy_matches_database(pg):
    a = bundle("M03_CLASSIFIER").output_schema["properties"]["result"]["properties"]["assignments"]["items"]["properties"]
    with pg.admin() as c:
        ids = {r["id"] for r in c.execute("SELECT id FROM lfhe.taxonomy_items WHERE taxonomy_version=%s",
                                          (TAXONOMY_VERSION,)).fetchall()}
    assert set(a["taxonomy_id"]["enum"]) == ids and len(ids) == 62
    assert a["target_object_type"] == {"const": "CLAIM"}


@pytest.mark.parametrize("bad", [
    {"claim_type": "RUMOUR"}, {"source_statement_status": "TRUE"}, {"evidence_directness": "SECOND_HAND"},
    {"claim_local_id": "X1"}, {"event_date": "3 October"}, {"extra_field": 1},
])
def test_m02_schema_rejects_out_of_contract_claims(bad):
    schema = bundle("M02_CLAIM_EXTRACTOR").output_schema
    text = "The ministry said 12 drones were delivered."
    c = candidate(text, "12 drones were delivered")
    c["normalisation_check"] = {d: "PRESERVED" for d in (
        "actor", "action", "attribution", "uncertainty", "modality", "quantity", "unit", "time", "location",
        "negation", "conditionality", "source_assessment_language")} | {
        "translation_material_mismatch": False, "source_language_interpretation_uncertain": False}
    c.pop("review_flags")
    c["evidence_span_original"].pop("locator_type")
    out = {"module": "M02_CLAIM_EXTRACTOR", "status": "SUCCESS", "warnings": [], "human_review_required": False,
           "result": {"article_snapshot_id": "a", "text_representation_id": "t", "claims": [c]}}
    assert list(Draft202012Validator(schema).iter_errors(out)) == []
    c.update(bad)
    assert list(Draft202012Validator(schema).iter_errors(out)) != []


def test_m02_inputs_are_deterministic_and_original_language(pg):
    text = "Міністерство оборони повідомило про постачання 12 дронів."
    snap = make_text_snapshot(pg, text, language="uk")
    with pg.worker() as c:
        a = build_m02_inputs(c, snap["rep_id"])
        b = build_m02_inputs(c, snap["rep_id"])
    ea, eb = (TaskEnvelope("M02_CLAIM_EXTRACTOR", x.task, x.inputs, x.context) for x in (a, b))
    assert ea.envelope_sha256 == eb.envelope_sha256 and ea.input_manifest == eb.input_manifest
    [item] = a.inputs
    assert (item.object_type, item.object_id) == ("text_representation", snap["rep_id"])
    assert item.content["content_original"] == text and item.content["language_original"] == "uk"
    assert item.content["content_working_translation"] is None
    assert item.content["article_snapshot_id"] == snap["snapshot_id"]


def test_m02_inputs_fail_closed(pg):
    unknown = make_text_snapshot(pg, "Text in an undetermined language.", language=None)
    with pg.worker() as c:
        with pytest.raises(InputBuildError) as e:
            build_m02_inputs(c, unknown["rep_id"])
        assert e.value.code == "ORIGINAL_LANGUAGE_UNKNOWN"
        with pytest.raises(InputBuildError) as e:
            build_m02_inputs(c, "00000000-0000-4000-8000-000000000000")
        assert e.value.code == "TEXT_REPRESENTATION_NOT_FOUND"


def test_m03_inputs_use_claim_ids_and_full_closed_taxonomy(pg):
    text = "The air force said 12 drones were delivered to the brigade."
    snap = make_text_snapshot(pg, text)
    run = extraction_run(pg, snap)
    out = ingest(pg, snap, run, [candidate(text, "12 drones were delivered to the brigade")])
    [cid] = out["claim_ids"]
    with pg.worker() as c:
        ti = build_m03_inputs(c, [cid])
        tax = taxonomy_context(c)
    assert [(i.object_type, i.object_id) for i in ti.inputs] == [("claim", cid)]
    assert ti.task == {"taxonomy_version": "LFHE-TAX-1.2",
                       "intelligence_requirements": [f"PIR_0{i}" for i in range(1, 9)]}
    assert [(x.object_type, x.object_id) for x in ti.context] == [("taxonomy", "LFHE-TAX-1.2")]
    assert len(tax.content["items"]) == 62 and tax.content_sha256 == ti.context[0].content_sha256
