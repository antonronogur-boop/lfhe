"""P1-10 — prompt-version source of truth (guardrail 3) and model-run traceability."""
import json
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from conftest import REPO_ROOT, create_database
from lfhe_orchestrator.providers import FakeProvider, ProviderError
from lfhe_orchestrator.runner import NoActivePromptVersion, run_structured_task
from lfhe_shared.envelopes import EnvelopeItem, TaskEnvelope, verify_envelope
from lfhe_shared.prompts import bundle_sha256, load_bundle, register, verify_registered

pytestmark = pytest.mark.db

SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
          "required": ["echo"], "properties": {"echo": {"type": "string"}}, "additionalProperties": False}


def write_bundle(root: Path, module: str, semver: str, system: str = "Synthetic fixture.", fixture=True):
    d = root / module / semver
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({
        "format": "lfhe-prompt-manifest/1", "module_code": module, "semver": semver,
        "module_version": "test-fixture", "test_fixture": fixture}), encoding="utf-8")
    (d / "system.md").write_text(system, encoding="utf-8")
    (d / "task.md").write_text("Echo the envelope text.", encoding="utf-8")
    (d / "output_schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
    prefix = "tests/fixtures/prompts" if fixture else "packages/prompts"
    return load_bundle(d, git_path=f"{prefix}/{module}/{semver}")


def env(text):
    return {"task": {"text": text},
            "inputs": [EnvelopeItem("text_representation", "11111111-1111-4111-8111-111111111111",
                                    {"text": f"Synthetic evidence {text}"})],
            "context": [EnvelopeItem("reference_context", "ctx-synthetic-1", {"note": "synthetic context"})]}


def module_code():
    return "T_" + uuid.uuid4().hex[:10].upper()


@pytest.fixture
def admin_user(make_user):
    return make_user("ADMIN")


def activate(pg, user, pv_id, reason="activate for synthetic test"):
    with pg.as_user(user) as c:
        c.execute("SELECT lfhe.activate_prompt_version(%s, %s)", (pv_id, reason))


def model_config(pg, settings=None):
    with pg.registrar() as c:
        return str(c.execute("SELECT lfhe.register_model_configuration('fake', 'fake-model-1', %s::jsonb) AS id",
                             (Jsonb(settings or {"temperature": 0}),)).fetchone()["id"])


# ---------------------------------------------------------------------------
def test_registration_db_hash_equals_git_hash_and_is_idempotent(pg):
    bundle = load_bundle(REPO_ROOT / "tests/fixtures/prompts/T00_ECHO/1.0.0", repo_root=REPO_ROOT)
    assert bundle.git_path == "tests/fixtures/prompts/T00_ECHO/1.0.0"
    with pg.registrar() as c:
        first = register(c, bundle, git_commit=None, git_tree_clean=False)
        assert register(c, bundle, git_commit=None, git_tree_clean=False) == first
        row = c.execute("SELECT * FROM lfhe.prompt_versions WHERE id=%s", (first,)).fetchone()
    assert row["content_hash"] == bundle.content_hash == bundle_sha256("T00_ECHO", "1.0.0", row["files"])
    assert row["files"] == bundle.files and row["registered_by_role"] == "registrar_test"
    with pg.admin() as c:
        assert verify_registered(c, REPO_ROOT, modules=["T00_ECHO"]) == []


def test_same_semver_with_different_content_is_rejected(pg, tmp_path):
    mod = module_code()
    original = write_bundle(tmp_path / "a", mod, "1.0.0", "Original text.")
    edited = write_bundle(tmp_path / "b", mod, "1.0.0", "Edited text.")
    with pg.registrar() as c:
        register(c, original, git_commit=None, git_tree_clean=False)
        with pytest.raises(psycopg.errors.UniqueViolation, match="PROMPT_VERSION_CONFLICT"):
            register(c, edited, git_commit=None, git_tree_clean=False)
        payload = {"module_code": mod, "semver": "1.0.1", "module_version": "test-fixture",
                   "is_test_fixture": True, "files": edited.files, "git_path": f"tests/fixtures/prompts/{mod}/1.0.1",
                   "git_commit": None, "git_tree_clean": False, "expected_content_hash": "0" * 64}
        with pytest.raises(psycopg.errors.DataException, match="PROMPT_HASH_MISMATCH"):
            c.execute("SELECT lfhe.register_prompt_version(%s::jsonb)", (Jsonb(payload),))
        bad_manifest = dict(payload, files={**edited.files, "manifest.json": edited.files["manifest.json"]},
                            semver="1.0.1")
        bad_manifest["expected_content_hash"] = bundle_sha256(mod, "1.0.1", bad_manifest["files"])
        with pytest.raises(psycopg.errors.CheckViolation, match="prompt_bundle_valid"):
            c.execute("SELECT lfhe.register_prompt_version(%s::jsonb)", (Jsonb(bad_manifest),))


def test_prompt_versions_are_immutable_and_hash_checked(pg, tmp_path):
    mod = module_code()
    b = write_bundle(tmp_path, mod, "1.0.0")
    with pg.registrar() as c:
        pv = register(c, b, git_commit=None, git_tree_clean=False)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO lfhe.prompt_versions (module_code, semver, module_version, is_test_fixture,"
                      " files, content_hash, git_path, git_tree_clean) SELECT module_code, '9.9.9', module_version,"
                      " is_test_fixture, files, content_hash, git_path, false FROM lfhe.prompt_versions WHERE id=%s", (pv,))
    with pg.admin() as c:
        for sql in ("UPDATE lfhe.prompt_versions SET files = files || '{\"system.md\": \"x\"}' WHERE id=%s",
                    "UPDATE lfhe.prompt_versions SET content_hash = content_hash WHERE id=%s",
                    "DELETE FROM lfhe.prompt_versions WHERE id=%s"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
                c.execute(sql, (pv,))
        files = dict(b.files, **{"manifest.json": b.files["manifest.json"].replace('"1.0.0"', '"2.0.0"')})
        with pytest.raises(psycopg.errors.CheckViolation, match="prompt_content_hash_matches"):
            c.execute("INSERT INTO lfhe.prompt_versions (module_code, semver, module_version, is_test_fixture, files,"
                      " content_hash, git_path, git_tree_clean) VALUES (%s, '2.0.0', 'test-fixture', true, %s, %s,"
                      " %s, false)", (mod, Jsonb(files), b.content_hash, f"tests/fixtures/prompts/{mod}/2.0.0"))
        c.execute("INSERT INTO lfhe.prompt_versions (module_code, semver, module_version, is_test_fixture, files,"
                  " content_hash, git_path, git_tree_clean) VALUES (%s, '2.0.0', 'test-fixture', true, %s, %s,"
                  " %s, false)", (mod, Jsonb(files), bundle_sha256(mod, "2.0.0", files),
                                  f"tests/fixtures/prompts/{mod}/2.0.0"))  # control: correct hash accepted


def test_only_registrar_registers_and_only_humans_activate(pg, tmp_path, make_user):
    b = write_bundle(tmp_path, module_code(), "1.0.0")
    for conn in (pg.worker, pg.as_service_role, pg.as_anon, lambda: pg.as_user(make_user("ADMIN"))):
        with conn() as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                register(c, b, git_commit=None, git_tree_clean=False)
    with pg.registrar() as c:
        pv = register(c, b, git_commit=None, git_tree_clean=False)
    for conn in (pg.worker, pg.registrar, pg.as_service_role, pg.as_anon):
        with conn() as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("SELECT lfhe.activate_prompt_version(%s, 'not a human')", (pv,))
    with pg.as_user(make_user("VIEWER")) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="PROMPT_ACTIVATE"):
            c.execute("SELECT lfhe.activate_prompt_version(%s, 'viewer attempt')", (pv,))
    with pg.as_role("authenticated", {"sub": str(uuid.uuid4()), "role": "authenticated"}) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.activate_prompt_version(%s, 'forged user')", (pv,))


def test_activation_lifecycle_is_append_only_and_audited(pg, tmp_path, admin_user):
    mod = module_code()
    v1, v2 = write_bundle(tmp_path, mod, "1.0.0", "One."), write_bundle(tmp_path, mod, "1.1.0", "Two.")
    with pg.registrar() as c:
        id1 = register(c, v1, git_commit=None, git_tree_clean=False)
        id2 = register(c, v2, git_commit=None, git_tree_clean=False)
    with pg.as_user(admin_user) as c:
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            c.execute("SELECT lfhe.activate_prompt_version(%s, '')", (id1,))
        c.execute("SELECT lfhe.activate_prompt_version(%s, 'initial activation')", (id1,))
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            c.execute("SELECT lfhe.activate_prompt_version(%s, 'again')", (id1,))
        c.execute("SELECT lfhe.activate_prompt_version(%s, 'upgrade to 1.1.0')", (id2,))
        active = c.execute("SELECT * FROM lfhe.active_prompt_versions WHERE module_code=%s", (mod,)).fetchone()
        assert (str(active["prompt_version_id"]), active["semver"]) == (id2, "1.1.0")
        c.execute("SELECT lfhe.deactivate_prompt_module(%s, 'withdraw for test')", (mod,))
        assert c.execute("SELECT count(*) AS n FROM lfhe.active_prompt_versions WHERE module_code=%s",
                         (mod,)).fetchone()["n"] == 0
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            c.execute("SELECT lfhe.deactivate_prompt_module(%s, 'nothing active')", (mod,))
    with pg.admin() as c:
        log = c.execute("SELECT action, prompt_version_id, previous_prompt_version_id, environment, actor_user_id "
                        "FROM lfhe.prompt_activations WHERE module_code=%s ORDER BY seq", (mod,)).fetchall()
        assert [(r["action"], str(r["prompt_version_id"]), str(r["previous_prompt_version_id"])) for r in log] == [
            ("ACTIVATE", id1, "None"), ("ACTIVATE", id2, id1), ("DEACTIVATE", "None", id2)]
        assert {r["environment"] for r in log} == {"TEST"} and {r["actor_user_id"] for r in log} == {admin_user}
        audit = c.execute("SELECT event_type, actor_type, actor_user_id FROM lfhe.audit_log "
                          "WHERE object_type='prompt_version' AND object_id IN (%s, %s) ORDER BY seq", (id1, id2)).fetchall()
        assert [a["event_type"] for a in audit] == ["PROMPT_VERSION_CREATED", "PROMPT_VERSION_CREATED",
                                                     "PROMPT_VERSION_ACTIVATED", "PROMPT_VERSION_ACTIVATED",
                                                     "PROMPT_VERSION_DEACTIVATED"]
        assert all(a["actor_type"] == "HUMAN" and a["actor_user_id"] == admin_user for a in audit[2:])
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            c.execute("DELETE FROM lfhe.prompt_activations WHERE module_code=%s", (mod,))


def test_prod_refuses_fixture_or_uncommitted_prompts(pg, tmp_path):
    dbname = "lfhe_prod_guard"
    create_database(pg, dbname, "PROD")
    fixture = write_bundle(tmp_path, module_code(), "1.0.0")
    real = write_bundle(tmp_path / "r", "M99_SYNTHETIC", "1.0.0", fixture=False)
    clean = write_bundle(tmp_path / "s", "M98_SYNTHETIC", "1.0.0", fixture=False)
    uid = uuid.uuid4()
    with psycopg.connect(pg.url("postgres", dbname), autocommit=True) as c:
        c.execute("INSERT INTO auth.users (id, email) VALUES (%s, 'prod-admin@test.invalid')", (uid,))
        c.execute("SELECT lfhe.bootstrap_grant_role(%s, 'ADMIN')", (uid,))
    with pg.registrar(dbname=dbname) as c:
        ids = [register(c, fixture, git_commit=None, git_tree_clean=False),
               register(c, real, git_commit="a" * 40, git_tree_clean=False),
               register(c, clean, git_commit="b" * 40, git_tree_clean=True)]
    conn = psycopg.connect(pg.url("authenticator", dbname), autocommit=True)
    try:
        conn.execute("SET ROLE authenticated")
        conn.execute("SELECT set_config('request.jwt.claims', %s, false)",
                     (json.dumps({"sub": str(uid), "role": "authenticated"}),))
        for pv in ids[:2]:
            with pytest.raises(psycopg.errors.CheckViolation, match="PROD activation"):
                conn.execute("SELECT lfhe.activate_prompt_version(%s, 'prod attempt')", (pv,))
        conn.execute("SELECT lfhe.activate_prompt_version(%s, 'clean committed artifact')", (ids[2],))
    finally:
        conn.close()


def test_model_run_records_exact_prompt_and_model_identity(pg, tmp_path, admin_user):
    mod = module_code()
    with pg.registrar() as c:
        pv = register(c, write_bundle(tmp_path, mod, "1.0.0"), git_commit=None, git_tree_clean=False)
    mc = model_config(pg)
    with pg.worker() as c:
        with pytest.raises(NoActivePromptVersion):
            run_structured_task(c, module_code=mod, **env("x"), model_configuration_id=mc,
                                provider=FakeProvider(lambda m, e: "{}"), worker_id="model-test")
    activate(pg, admin_user, pv)
    provider = FakeProvider(lambda m, e: json.dumps({"echo": e["task"]["text"]}))
    kwargs = env("Пример тексту")
    envelope = TaskEnvelope(mod, kwargs["task"], kwargs["inputs"], kwargs["context"])
    with pg.worker() as c:
        res = run_structured_task(c, module_code=mod, **kwargs, model_configuration_id=mc,
                                  provider=provider, worker_id="model-test")
        row = c.execute("SELECT r.*, pv.content_hash AS pv_hash, m.config_hash FROM lfhe.model_runs r "
                        "JOIN lfhe.prompt_versions pv ON pv.id=r.prompt_version_id "
                        "JOIN lfhe.model_configurations m ON m.id=r.model_configuration_id WHERE r.id=%s",
                        (res.run_id,)).fetchone()
    assert res.status == "SUCCEEDED" and res.parsed_output == {"echo": "Пример тексту"}
    assert str(row["prompt_version_id"]) == pv and row["prompt_semver"] == "1.0.0"
    assert row["prompt_content_hash"] == row["pv_hash"] and row["module_version"] == "test-fixture"
    assert (row["provider"], row["model"], row["model_config_hash"]) == ("fake", "fake-model-1", row["config_hash"])
    assert row["envelope_sha256"] == envelope.envelope_sha256 and row["environment"] == "TEST"
    assert row["input_snapshot_sha256"] == envelope.input_snapshot_sha256
    assert row["context_snapshot_sha256"] == envelope.context_snapshot_sha256
    assert verify_envelope(provider.calls[0][1], row) == []
    assert row["parsed_output"] == {"echo": "Пример тексту"} and row["raw_output_sha256"]
    module_seen = provider.calls[0][0]
    assert module_seen.content_hash == row["pv_hash"] and module_seen.system == "Synthetic fixture."


def test_schema_failures_and_provider_errors_are_recorded_not_repaired(pg, tmp_path, admin_user):
    mod = module_code()
    with pg.registrar() as c:
        pv = register(c, write_bundle(tmp_path, mod, "1.0.0"), git_commit=None, git_tree_clean=False)
    activate(pg, admin_user, pv)
    mc = model_config(pg)
    outputs = iter(['{"echo": 5, "extra": true}', "not json at all"])

    def flaky(m, e):
        raise ProviderError("PROVIDER_TIMEOUT", "synthetic timeout")

    with pg.worker() as c:
        r1 = run_structured_task(c, module_code=mod, **env("a"), model_configuration_id=mc,
                                 provider=FakeProvider(lambda m, e: next(outputs)), worker_id="model-test")
        r2 = run_structured_task(c, module_code=mod, **env("b"), model_configuration_id=mc,
                                 provider=FakeProvider(lambda m, e: next(outputs)), worker_id="model-test")
        r3 = run_structured_task(c, module_code=mod, **env("c"), model_configuration_id=mc,
                                 provider=FakeProvider(flaky), worker_id="model-test")
        rows = {str(r["id"]): r for r in c.execute("SELECT * FROM lfhe.model_runs WHERE id IN (%s,%s,%s)",
                                                     (r1.run_id, r2.run_id, r3.run_id)).fetchall()}
    assert r1.status == r2.status == "SCHEMA_VALIDATION_FAILED"
    assert {e["path"] for e in r1.validation_errors} == {"", "echo"}
    assert rows[r1.run_id]["parsed_output"] is None and rows[r1.run_id]["raw_output"] == '{"echo": 5, "extra": true}'
    assert "not valid JSON" in rows[r2.run_id]["validation_errors"][0]["message"]
    assert r3.status == "PROVIDER_ERROR" and rows[r3.run_id]["error_code"] == "PROVIDER_TIMEOUT"


def test_runs_require_active_version_and_are_immutable_once_finished(pg, tmp_path, admin_user):
    mod = module_code()
    with pg.registrar() as c:
        old = register(c, write_bundle(tmp_path, mod, "1.0.0", "Old."), git_commit=None, git_tree_clean=False)
        new = register(c, write_bundle(tmp_path, mod, "2.0.0", "New."), git_commit=None, git_tree_clean=False)
    mc = model_config(pg)
    activate(pg, admin_user, old)
    with pg.worker() as c:
        done = run_structured_task(c, module_code=mod, **env("x"), model_configuration_id=mc,
                                   provider=FakeProvider(lambda m, e: '{"echo": "x"}'), worker_id="model-test")
    activate(pg, admin_user, new, "upgrade for test")
    with pg.worker() as c:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="not the active version"):
            c.execute("SELECT lfhe.start_model_run(%s, %s, %s, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, 'model-test')",
                      (old, mc, "a" * 64))
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            c.execute("SELECT lfhe.finish_model_run(%s, 'PROVIDER_ERROR', NULL, NULL, NULL, 'X', 'x', '{}')",
                      (done.run_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE lfhe.model_runs SET status='PROVIDER_ERROR' WHERE id=%s", (done.run_id,))
    with pg.admin() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="immutable"):
            c.execute("UPDATE lfhe.model_runs SET parsed_output='{}' WHERE id=%s", (done.run_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="never deleted"):
            c.execute("DELETE FROM lfhe.model_runs WHERE id=%s", (done.run_id,))
        # copied identifiers cannot disagree with the registry (composite FK)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute("INSERT INTO lfhe.model_runs (module_code, prompt_version_id, prompt_semver, prompt_content_hash,"
                      " module_version, model_configuration_id, provider, model, model_config_hash, environment,"
                      " envelope_sha256, task_parameters, input_manifest, input_snapshot_sha256, context_manifest,"
                      " context_snapshot_sha256, worker_id) SELECT module_code, prompt_version_id, prompt_semver, %s,"
                      " module_version, model_configuration_id, provider, model, model_config_hash, environment,"
                      " envelope_sha256, task_parameters, input_manifest, input_snapshot_sha256, context_manifest,"
                      " context_snapshot_sha256, worker_id FROM lfhe.model_runs WHERE id=%s", ("f" * 64, done.run_id))


def test_model_configurations_are_immutable_and_secret_free(pg):
    a = model_config(pg, {"temperature": 0, "max_tokens": 1000})
    assert model_config(pg, {"max_tokens": 1000, "temperature": 0}) == a, "same config → same record"
    assert model_config(pg, {"temperature": 0.2, "max_tokens": 1000}) != a
    with pg.registrar() as c:
        with pytest.raises(psycopg.errors.CheckViolation, match="CREDENTIAL_KEY_REJECTED"):
            c.execute("SELECT lfhe.register_model_configuration('fake', 'm', '{\"api_key\": \"x\"}')")
    with pg.worker() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT lfhe.register_model_configuration('fake', 'm', '{}')")
    with pg.admin() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            c.execute("UPDATE lfhe.model_configurations SET model='other' WHERE id=%s", (a,))
        assert c.execute("SELECT count(*) AS n FROM lfhe.audit_log WHERE event_type='MODEL_CONFIGURATION_REGISTERED' "
                         "AND object_id=%s", (a,)).fetchone()["n"] == 1


def test_database_set_hashes_equal_python_and_reject_bad_manifests(pg, tmp_path, admin_user):
    from lfhe_shared.envelopes import CONTEXT_SET_FORMAT, INPUT_SET_FORMAT, set_sha256
    items = env("x")
    e = TaskEnvelope("T_X", items["task"], items["inputs"] + [EnvelopeItem("text_representation", "z-2", {"t": 2})],
                     items["context"])
    with pg.admin() as c:
        db_in = c.execute("SELECT lfhe.object_set_sha256(%s, %s::jsonb) AS h",
                          (INPUT_SET_FORMAT, Jsonb(e.input_manifest))).fetchone()["h"]
        db_ctx = c.execute("SELECT lfhe.object_set_sha256(%s, %s::jsonb) AS h",
                           (CONTEXT_SET_FORMAT, Jsonb(list(reversed(e.context_manifest))))).fetchone()["h"]
    assert db_in == e.input_snapshot_sha256 == set_sha256(INPUT_SET_FORMAT, list(reversed(e.input_manifest)))
    assert db_ctx == e.context_snapshot_sha256

    mod = module_code()
    with pg.registrar() as c:
        pv = register(c, write_bundle(tmp_path, mod, "1.0.0"), git_commit=None, git_tree_clean=False)
    activate(pg, admin_user, pv)
    mc = model_config(pg)
    dup = [e.input_manifest[0], e.input_manifest[0]]
    with pg.worker() as c:
        for bad in (dup, [{"object_type": "x y", "object_id": "1", "content_sha256": "0" * 64}],
                    [{"object_type": "t1", "object_id": "1"}], {"not": "array"}):
            with pytest.raises(psycopg.errors.InvalidParameterValue):
                c.execute("SELECT lfhe.start_model_run(%s, %s, %s, '{}'::jsonb, %s::jsonb, '[]'::jsonb, 'model-test')",
                          (pv, mc, "a" * 64, Jsonb(bad)))
        rid = c.execute("SELECT lfhe.start_model_run(%s, %s, %s, '{}'::jsonb, %s::jsonb, %s::jsonb, 'model-test') AS id",
                        (pv, mc, e.envelope_sha256, Jsonb(e.input_manifest), Jsonb(e.context_manifest))).fetchone()["id"]
        row = c.execute("SELECT * FROM lfhe.model_runs WHERE id=%s", (rid,)).fetchone()
    assert row["input_snapshot_sha256"] == e.input_snapshot_sha256 and row["context_snapshot_sha256"] == e.context_snapshot_sha256
    with pg.admin() as c:  # a forged set hash cannot be stored, even by the owner
        with pytest.raises(psycopg.errors.CheckViolation, match="model_run_input_set_hash"):
            c.execute("INSERT INTO lfhe.model_runs (module_code, prompt_version_id, prompt_semver, prompt_content_hash,"
                      " module_version, model_configuration_id, provider, model, model_config_hash, environment,"
                      " envelope_sha256, task_parameters, input_manifest, input_snapshot_sha256, context_manifest,"
                      " context_snapshot_sha256, worker_id) SELECT module_code, prompt_version_id, prompt_semver,"
                      " prompt_content_hash, module_version, model_configuration_id, provider, model, model_config_hash,"
                      " environment, envelope_sha256, task_parameters, input_manifest, %s, context_manifest,"
                      " context_snapshot_sha256, worker_id FROM lfhe.model_runs WHERE id=%s", ("e" * 64, rid))
