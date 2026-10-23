# LFHÉ — CONTROL GATE 6 REPORT

## PHASE / GATE

- Fázis: **Phase 6 — QA, Approval & Release** (M10-D determinisztikus QA, M10-S szemantikus QA, kombinált QA-státusz, figyelmeztetés-nyugtázás, emberi tartalmi jóváhagyás, emberi security / kezelési review, release PDF, determinisztikus kiadhatósági ellenőrzés, emberi kiadási döntés, atomikus manifest + RELEASED, javítási út).
- Kapu: **CONTROL GATE 6 — PO-DÖNTÉSRE VÁR.** A CG6-ot csak a Product Owner hagyhatja jóvá; ez a jelentés nem jóváhagyás.
- Alap: `docs/specs/LFHE_Phase6_Authoritative_Baseline_Addendum_v1.0.md` (SPEC_INDEX 22), PO felhatalmazás `docs/specs/PO_Decision_2026-10-23_Authorise_Phase6.md` (SPEC_INDEX 23); mindkettő szó szerint tárolva a P6-00-ban.
- Végrehajtás: P6-00 … P6-10 a megadott sorrendben, köztes engedélykérés nélkül. CG1–CG5 nincs újranyitva; általános architektúra-audit nem történt; a lezárt Phase 1–5 szemantika nem változott.
- Commitok: P6-00 `b1d01a3`; P6-01…03 `44393a3`; P6-04…07 `91e45e4`; P6-08 `904c9a4`; CI Chromium-javítás `47eec80`; P6-09 `5fedf1b`; P6-10 (dokumentáció, smoke, ez a jelentés) a záró commitban.
- **Phase 7 NEM indult el. Az implementáció a P6-10 után MEGÁLLT.**

## IMPLEMENTED

- **P6-01** — perzisztencia és RBAC: `qa_checks` (zárt ellenőrzés-lista, 25 D + 10 S), `qa_requests`, `qa_runs` (D / S), `qa_check_results`, `qa_results` (kombinált), `warning_acknowledgements`, `content_approvals`, `security_reviews`, `release_pdf_artifacts`, `release_decisions`, `release_manifests`, `report_releases` (RELEASED). Mind kompozit FK-val a pontos `(report_version_id, report_version_hash)`-hoz, RLS, közvetlen írás senkinek, immutábilis.
- **P6-02** — M10-D (`lfhe.run_m10d`, `lfhe-m10d/1.0.0`): determinisztikus, fail-closed motor, model_run nélkül; ellenőrzésenként finding vagy PASS-sor.
- **P6-03** — M10-S: `M10_QA_AUDITOR/1.0.0` prompt bundle (prompt-lock), szigorú séma, bemenet-építő (`qa_inputs.py`), ingestion (`lfhe.ingest_qa_semantic`), legfeljebb egy séma-javító futás.
- **P6-04** — kombinált státusz (`lfhe.record_qa_result`), rerun-történet, `QA_RESULT_CHANGED_BY_RERUN`, HUMAN_ONLY nyugtázás (`acknowledge_qa_warning`).
- **P6-05** — HUMAN_ONLY tartalmi döntés (`decide_report_content`) és security review (`decide_security_review`), audit.
- **P6-06** — release PDF (`report_pdf.py`): release HTML → headless Chromium → write-once tároló → `release_pdf_artifacts` (bájtok, SHA-256, kötések).
- **P6-07** — `lfhe.p6_release_checklist` / `release_eligibility`, `decide_release` (RETURN / REJECT), `release_report` (egyetlen út a RELEASED-hez, atomikus), manifest JCS / SHA-256, guard trigger, javítási út (`REPORT_CORRECTION_CREATED`).
- **P6-08** — `/reports/[id]` QA és release nézet + PDF-letöltés.
- **P6-09** — elfogadási korpusz (24 QA + 17 workflow forgatókönyv), RBAC-sweep, prompt-injection, fail-closed, atomicitás, regresszió, CI.
- **P6-10** — DEV smoke Phase 6 ellenőrzések, dokumentáció, ez a jelentés.

Nem implementált (tiltás szerint): Phase 7, éles telepítés, minősített adat, AI-alapú minősítési jelölés, külső terjesztés / e-mail / NATO-integráció, autonóm security- vagy kiadási döntés, M10 hozzáférés Gold Standard anyaghoz.

## FILES CHANGED

`git diff --stat b1d01a3..HEAD`: kb. 40 fájl, ≈ +5 900 sor.

- `database/migrations/20261011003800_p6_qa.sql`, `20261011003900_p6_approval_release.sql` (új, előrefelé).
- `packages/prompts/M10_QA_AUDITOR/1.0.0/{manifest.json,system.md,task.md,output_schema.json}`, `packages/prompts/prompt-lock.json`.
- `services/ai-orchestrator/lfhe_orchestrator/` — új `qa_inputs.py`, `qa_pipeline.py`, `report_pdf.py`; módosítva `report_render.py` (RELEASE változat; a PREVIEW bájtra azonos), `worker.py` (RUN_REPORT_QA, RENDER_RELEASE_PDF), `model_settings.py` (M10 low-variance); `services/shared/lfhe_shared/config.py` (`m10_model_configuration_id`).
- `apps/web/` — `app/reports/[id]/release-panels.tsx`, `app/reports/release-actions.ts`, `app/reports/[id]/pdf/[artifact]/route.ts`, `lib/release.ts`, `lib/auth.ts`, `app/reports/[id]/page.tsx` (két új fül), `tests/release.test.ts`.
- `scripts/supabase_dev_smoke.py` — 11 Phase 6 ellenőrzés.
- `.github/workflows/ci.yml` — Chromium-verzió lépés, `LFHE_CHROMIUM_NO_SANDBOX=1` a tesztlépésben.
- `tests/` — `m10s_auditor.py`, `integration/p6_helpers.py`, `test_p6_m10d.py`, `test_p6_m10s.py`, `test_p6_approvals.py`, `test_p6_release.py`, `test_p6_workspace.py`, `security/test_p6_rbac.py`, `acceptance/test_phase6_acceptance.py`, `fixtures/phase6_acceptance/corpus.json`; `integration/p5_helpers.py` (job-parkolás az új job-típusokra), `security/test_gs_isolation.py` (új bemenet-építő és korpusz).
- `docs/` — `qa-release-design.md`, `phase6-test-traceability.md`, `cg6-acceptance-metrics.json`, `permission-matrix.md`, `audit-catalogue.md`, `runbooks/dev-supabase-smoke.md`, `PROJECT_STATUS.md`, `SPEC_INDEX.md`, `specs/` (baseline + PO döntés).

## DATABASE MIGRATIONS

| Migráció | Tartalom |
| --- | --- |
| `20261011003800_p6_qa.sql` | `qa_checks`, `qa_requests`, `qa_runs`, `qa_check_results`, `qa_results`, `warning_acknowledgements`; segédfüggvények (`p6_autofail_codes`, `p6_recommended_actions`, `p6_prohibited_marking`, `p6_instruction_like`, `p6_current_qa_result`, `p6_unacknowledged_warnings`, …); HUMAN_ONLY `request_report_qa`, `acknowledge_qa_warning`; worker `run_m10d`, `ingest_qa_semantic`, `record_qa_result`; audit-triggerek; RUN_REPORT_QA / RENDER_RELEASE_PDF job-típusok |
| `20261011003900_p6_approval_release.sql` | `content_approvals`, `security_reviews`, `release_pdf_artifacts`, `release_decisions`, `release_manifests`, `report_releases`; guard trigger (`p6_release_guard`); `p6_release_checklist`, `release_eligibility`, `p6_build_manifest`, `p6_manifest_problems`; HUMAN_ONLY `decide_report_content`, `decide_security_review`, `request_release_pdf`, `decide_release`, `release_report`; worker `record_release_pdf`; új-verzió trigger (javítás / érvénytelenítés audit); `report_version_workflow` nézet |

**Új migrációk:** 2 (`20261011003800_p6_qa.sql`, `20261011003900_p6_approval_release.sql`). **Összes migráció: 40.** A 3500–3700 nem módosult. A két új migrációt az első push után, de még bármely telepítés előtt, helyben pontosítottam (SD6-16).

## PHASE 6 STATE MODEL

Származtatott állapot a `report_version_workflow` nézetben (DC6-01: a `report_versions.state` továbbra is csak `DRAFT_VERSION`):
DRAFT_VERSION → QA_RUNNING → QA_FAILED | QA_PASSED | QA_PASSED_WITH_WARNINGS → WARNING_ACKNOWLEDGED → (tartalmi APPROVE) SECURITY_REVIEW_PENDING → SECURITY_APPROVED | SECURITY_RETURNED_FOR_REVISION | SECURITY_REJECTED → RELEASED | RELEASE_RETURNED_FOR_REVISION | RELEASE_REJECTED; továbbá CONTENT_RETURNED_FOR_REVISION, CONTENT_REJECTED, SUPERSEDED (újabb verzió létezik). A „jelenlegi” mindig: a report legújabb verziója → annak legújabb `qa_results` sora → az erre adott tartalmi döntés → ennek legújabb security review-ja.

## QA DATA MODEL

- `qa_runs`: `kind` D / S; D-nél `engine_version`, nincs `model_run_id` / `prompt_version_id` (CHECK); S-nél kötelező `model_run_id`, `prompt_version_id`, `deterministic_qa_run_id`; `status` COMPLETED / INVALID (`invalid_reasons`); `diagnostic_only`; a modell saját `qa_status` / `release_blocked` értéke csak tanácsadó mezőben.
- `qa_check_results`: a Prompt Pack §44 séma (check_id, status, severity, affected_object_id, affected_statement_id, details, evidence_refs, recommended_action) + `finding_code`, `layer`; CHECK: CRITICAL ⇒ FAIL, PASS ⇒ INFO, FAIL ⇒ MAJOR/CRITICAL, WARNING ⇒ WARNING/MAJOR. A `recommended_action` zárt, tanácsadó szótár — semmi nem hajtja végre.
- `qa_results`: a (D, S) pár kombinált státusza, `fail_reasons`, `warning_finding_ids`, számlálók, `release_blocked = (FAIL)`, előző eredmény, `changed_by_rerun`; kompozit FK mindkét futásra ugyanazzal a verzió+hash-sel.

## M10-D RESULTS

Mind a 25 determinisztikus ellenőrzés implementálva (táblázat: `docs/qa-release-design.md` §2). Igazolt fail-closed esetek (D): hiányzó mapping, post-cutoff bizonyíték, szupersedált (nem aktuális) jóváhagyás, bizalom- és likelihood-eltérés, hiányzó pin, nem sikeres M09-futás, megsértett eredeti nyelvű grounding, cutoff utáni baseline és referenciakontextus, hiányzó high-impact validálás, > 3 KJ, hamis függetlenség-szöveg, minősítési jelölés, beágyazott utasítás, elavult verzió. Rossz hash / ismeretlen verzió / idegen kérés: kivétel, semmi nem rögzül. M10-D nem hoz létre model_runt (mért: `m10d_model_runs = 0`).

## M10-S PROMPT / SCHEMA

- `M10_QA_AUDITOR/1.0.0`, module_version `MPP-1.2.2+P6-ADDENDUM-1.0`, low-variance kötelező (temperature ≤ 0,2), prompt-lock OK.
- Kimenet: globális envelope (`module = M10_QA_AUDITOR`), `result` = report / verzió / hash / D-futás azonosítók, tanácsadó `qa_status`, `findings` (zárt S check_id-k, zárt finding-kódok, zárt ajánlott akciók, `evidence_refs` objektum-típus whitelisttel), `errors`, `warnings`, `release_blocked`; minden szinten `additionalProperties: false` — szöveg, bizalom, likelihood, jóváhagyás vagy javított report nem adható vissza.
- A system prompt: csak a kapott anyag; nincs böngészés, külső tudás, benchmark-anyag; nincs javítás, jóváhagyás, kiadás; minden szöveg megbízhatatlan adat.

## SEMANTIC ENTAILMENT RESULTS

QA-01: a támogatott parafrázis PASS (S `test_supported_paraphrase_…`, A Q02); új tény, ok-okozat, szereplőcsere, hindsight FAIL CRITICAL (A Q05–Q07, Q13, Q22). A szemantikus ítéletet a tesztekben egy szabályalapú, csak az envelope-ot olvasó helyettesítő (`tests/m10s_auditor.py`) vagy címkézett, scriptelt modell adja; valós modell minősége nem mérve (lásd KNOWN FAILURES / OPEN ITEMS).

## ATTRIBUTION / EPISTEMIC RESULTS

Attribúció-törlés: S19 + D19 FAIL (A Q09). SOURCE_REPORTED → tény: QA-07 EPISTEMIC_STRENGTH_MISMATCH CRITICAL. Bizonyosság-erősítés: QA-07 MATERIAL_EPISTEMIC_STRENGTH_INCREASE (S és D, A Q08). Ellentmondás-semlegesítés („undisputed”, a Phase 5 validátor átengedi): QA-09 CONTRADICTION_REMOVED (A Q04). Hatókör-bővítés („all 4”, a Phase 5 validátor átengedi): QA-06 QUANTITY_SCOPE_DISTORTION (A Q03). Metrikák: `epistemic_strength_violations_accepted = 0`, `attribution_loss_accepted = 0`.

## SOURCE-INDEPENDENCE RESULTS

D QA-05: független megerősítést állító szöveg a jóváhagyott forrásban nem szereplő megfogalmazással → FAIL CRITICAL; jóváhagyott megfogalmazásnál a validált lineage-nek ≥ 2 csoportot és ismert lineage-et kell mutatnia, különben WARNING. S QA-05 ugyanezt szemantikusan jelzi (A Q10).

## HINDSIGHT / CUTOFF RESULTS

QA-04 (claim és értékelés as-of jogosultság, LIVE / REPLAY szabályok, eseményidő nem kritérium), D21 baseline, D22 referenciakontextus, QA-17 aggregátum — mind fail closed (D `test_m10d_post_cutoff_…`, A Q21). Szemantikus hindsight (később ismertté vált tény) → UNSUPPORTED_FACT (A Q13). `post_cutoff_hindsight_accepted = 0`.

## COMBINED QA RESULTS

D + S tiszta → PASS (A Q01, Q17, Q24); csak figyelmeztetés → PASS_WITH_WARNINGS (A Q16); bármely FAIL / CRITICAL / automatikus fail-kód / érvénytelen S-futás / hiányzó proveniencia / hash-kötési hiba → FAIL. Egy „engedelmes” modell PASS-a nem írhatja felül a determinisztikus CRITICAL-t (A Q15, Q22; S `test_prompt_injection_…`). Rerun: új eredmény, a régiek megmaradnak, státuszváltás auditálva.

## WARNING ACKNOWLEDGEMENT

HUMAN_ONLY, `QA_WARNING_ACKNOWLEDGE` (csak REVIEWER); kötve a pontos verzió+hash-hez, a JELENLEGI `qa_results`-hoz és a konkrét WARNING findinghoz; FAIL / CRITICAL nem nyugtázható (`NOT_ACKNOWLEDGEABLE`); egy rerun új nyugtázást követel (régi nem öröklődik). `critical_findings_acknowledged = 0`.

## CONTENT APPROVAL

HUMAN_ONLY, `REPORT_CONTENT_APPROVE` (csak REVIEWER); APPROVE / RETURN_FOR_REVISION / REJECT a jelenlegi QA-eredményre; FAIL nem hagyható jóvá; PASS_WITH_WARNINGS csak minden figyelmeztetés nyugtázása után; egy QA-eredményre egy döntés; az APPROVE determinisztikusan megnyitja a PENDING security review-t. ANALYST és ADMIN elutasítva. Audit: `REPORT_CONTENT_DECIDED` (új Phase 6 kód).

## SECURITY REVIEW

HUMAN_ONLY, `SECURITY_REVIEW` (csak SECURITY_REVIEWER); csak a jelenlegi tartalmi APPROVE által nyitott PENDING review dönthető el (APPROVED / RETURN_FOR_REVISION / REJECTED), egyszer; tartalmi jóváhagyás előtt nincs eldönthető review; az APPROVED indítja a release PDF jobot. Új verzió után a régi review történeti, nem alkalmazható (`SECURITY_APPROVAL_INVALIDATED`).

## PDF RELEASE ARTIFACT

A release HTML a Phase 5 determinisztikus renderelése ugyanabból a kanonikus JSON-ból, a „draft preview” sáv helyett release-sávval (a preview-nak előbb bájtra azonosan újra kell renderelődnie); headless Chromium offline nyomtat; a bájtok write-once, tartalom-címzett tárolóba (`release-pdf/sha256/…`) és a `release_pdf_artifacts` sorba kerülnek. Rögzítve: verzió+hash, preview render, template verzió / hash, renderer verzió / identitás / hash, tároló-kulcs, MIME, méret, SHA-256. A PDF-metaadat csak cím / producer; nincs titok, útvonal.

## PDF HASH / VERSION BINDING

CHECK-ek: SHA-256 = digest(bájtok), méret, `%PDF-` mágia, tároló-kulcs = hash, a HTML tartalmazza a verzió-hash-t; idegen render / rossz hash / security-jóváhagyás nélküli verzió elutasítva. A CHECK letiltott triggerek mellett is érvényes; a tároló olvasáskor újra-hash-el (`ObjectIntegrityError`). Byte-reprodukálhatóságot nem állítok (DC6-04); minden eltérő bájt-artefaktum saját azonosítót kap.

## RELEASE ELIGIBILITY

`lfhe.p6_release_checklist` (21 ellenőrzés, `docs/qa-release-design.md` §5) — tisztán olvasó, determinisztikus; a UI ugyanezt az adatbázis-eredményt mutatja (`release_eligibility`), sosem számol újra; a `release_report` a tranzakción belül újraértékeli. Bármely hiba → `RELEASE_NOT_ELIGIBLE: <kódok>`.

## RELEASE DECISIONS

`decide_release` csak RETURN_FOR_REVISION / REJECT_RELEASE (APPROVE_FOR_RELEASE itt tiltott), csak érvényes kiadási jelöltre (jelenlegi APPROVED security review), jelöltenként egyszer; nem módosítja a reportot, és a jelölt ezután nem adható ki (`NOT_RETURNED_OR_REJECTED`). APPROVE_FOR_RELEASE kizárólag `release_report`-ban. Audit: `RELEASE_RETURNED_FOR_REVISION`, `REPORT_RELEASE_REJECTED`, `REPORT_RELEASE_APPROVED`.

## RELEASE MANIFEST / MANIFEST HASH

Kanonikus manifest (`lfhe-release-manifest/1`, séma 1.0.0): report (id, kód, cím, ciklus, mód, cutoff), verzió (id, hash, szám, eredet, előd, szerző M09-futás + prompt-hash), kiválasztási készlet (id, hash), analitikai proveniencia (tételenként értékelés- / esemény- / indikátor- / trendverzió + hash + analitikai jóváhagyás id), QA (eredmény, státusz, D-futás + motorverzió, S-futás, M10-S model_run, M10 prompt verzió / semver / hash / modulverzió, modellkonfiguráció-hash), nyugtázás-id-k, tartalmi jóváhagyás, security review, kiadási döntés, kiadó, időbélyeg, renderelés (template verzió / hash, renderer verzió / hash, preview render, forrás-HTML hash), PDF (id, SHA-256, méret, MIME, tároló-kulcs). `manifest_hash = SHA-256(JCS(manifest))` CHECK-kel; SQL = Python = tárolt hash; teljesség-ellenőrzés (`p6_manifest_problems`) a tranzakcióban; kiadás után immutábilis (UPDATE / DELETE / TRUNCATE tiltva).

## RELEASED PROTECTION

RELEASED csak `report_releases` sorként létezik, és csak `lfhe.release_report` írhatja: HUMAN + `RELEASE_DECIDE`, belső újraellenőrzés, verzió- / hash- / PDF-hash-kötés, manifest + hash, döntés + manifest + RELEASED egy tranzakcióban. EXECUTE: csak `authenticated`; worker, ütemező, `service_role`, anon nem. A guard trigger a tranzakció-lokális tokenen kívül minden APPROVE-döntést, manifestet és RELEASED-sort elutasít (a tulajdonos közvetlen INSERT-jét is). ANALYST, REVIEWER, SECURITY_REVIEWER, ADMIN szerepkörrel elutasítva; ADMIN + RELEASE_AUTHORITY (K-06) kiadhat.

## POST-QA EDIT INVALIDATION

Bármely tartalmi változás új immutábilis verzió (Phase 5 út); a korábbi QA, nyugtázás, tartalmi döntés és security review megmarad, de az új verzióra nem érvényes (a „jelenlegi” lánc a legújabb verzióhoz kötött); audit `QA_INVALIDATED_BY_REPORT_CHANGE`, `SECURITY_APPROVAL_INVALIDATED`; az új verzió M10-D-től indul.

## RELEASED CORRECTION PATH

Kiadott verzió javítása = új verzió + `REPORT_CORRECTION_CREATED` (előd verzió / hash, kiadás, manifest-hash); teljes új QA → jóváhagyás → security → PDF → új döntés és új manifest; az előd verzió, PDF és manifest változatlan (hash-ekkel igazolva); a kiadott verzióra új QA-kérés tiltott (`REPORT_VERSION_RELEASED`).

## RBAC RESULTS

`tests/security/test_p6_rbac.py`: 7 HUMAN_ONLY függvény × (worker, service_role, anon, ADMIN, ANALYST, REVIEWER, SECURITY_REVIEWER, RELEASE_AUTHORITY, VIEWER, szerepkör nélküli) — csak a várt szerepkör jut át a jogosultsági kapun; a 4 worker-függvényt ember / service_role / anon nem hívhatja; 12 Phase 6 tábla egyik alkalmazás-szerepkörnek sem írható; a 4 Phase 6 jogosultság pontosan egy-egy szerepkörnél van (ADMIN-nál egyik sem). SECURITY DEFINER keményítés automatikusan lefedi az új függvényeket.

## AUDIT RESULTS

Új / most használt kódok: `REPORT_QA_REQUESTED`, `QA_RUN_CREATED`, `QA_RESULT_RECORDED`, `QA_RESULT_CHANGED_BY_RERUN`, `QA_WARNING_ACKNOWLEDGED`, `REPORT_CONTENT_DECIDED`, `SECURITY_REVIEW_OPENED`, `SECURITY_REVIEW_DECIDED`, `RELEASE_PDF_RECORDED`, `RELEASE_PDF_REQUESTED`, `REPORT_RELEASE_APPROVED`, `REPORT_RELEASE_MANIFEST_CREATED`, `RELEASE_RETURNED_FOR_REVISION`, `REPORT_RELEASE_REJECTED`, `REPORT_CORRECTION_CREATED`, `QA_INVALIDATED_BY_REPORT_CHANGE`, `SECURITY_APPROVAL_INVALIDATED` (`docs/audit-catalogue.md`). A model_run / finding rekordok nem duplikálódnak az auditba (hash / azonosító kerül be). Hash-lánc: a teljes futás végén 1 817 bejegyzés ellenőrizve, hiba 0.

## PROMPT-INJECTION RESULTS

A system prompt bájtra azonos a bundle-fájllal; a megbízhatatlan szöveg csak az escape-elt `<lfhe_task_envelope>` blokkban jelenik meg; jóváhagyott forrásban lévő injekciót az auditor adatként jelöl; a report szövegében lévő injekciót az M10-D determinisztikusan CRITICAL-ként jelzi (`EMBEDDED_INSTRUCTION_IN_CONTENT`, SD6-12), így egy engedelmes modell PASS-a sem menti meg; az ingestion a model_run tárolt kimenetét auditálja, nem a hívó által adott eredményt. `injected_instruction_accepted = 0`.

## MODEL_RUN TRACEABILITY

Minden M10-S hívás immutábilis model_run: modul, modulverzió, prompt verzió / hash, modellkonfiguráció / hash, envelope-hash, input / context manifest (benne a report-verzió), task-paraméterek (verzió, hash, mód, cutoff, D-futás, D-findingok), nyers kimenet, validáció, hibaállapot; a séma-javítás külön futás (`repair_of_model_run_id`). Finding model_run nélkül nem létezhet (CHECK). `m10s_traceability_gaps = 0`.

## WORKSPACE UI

`/reports/[id]?view=qa`: verzió / hash, workflow-állapot, kombinált és D / S státusz, súlyosság szerint csoportosított findingok (érintett állítás, bizonyíték-hivatkozások, tanácsadó akció, blokkolás), QA-történet, QA-kérés, figyelmeztetésenkénti nyugtázás, tartalmi döntés. `?view=release`: security döntés, PDF-artefaktumok, az adatbázis kiadhatósági listája, APPROVE_FOR_RELEASE (begépelt megerősítés), RETURN / REJECT, kiadott nézet (időbélyeg, kiadó, manifest-hash és -JSON, PDF-hash, letöltés a SHA-256 újraellenőrzésével). Minden döntés szerveroldali action → HUMAN_ONLY RPC. Böngészős végigkattintás DEV-en még nem történt (nem blokkoló, mint L-37).

## FAIL-CLOSED RESULTS

A §26 lista minden eleme teszttel lefedve (`docs/phase6-test-traceability.md`): érvénytelen QA-séma, ismeretlen bizonyíték-hivatkozás, rossz verzió / hash, elavult QA, hiányos QA-pár, hiányzó model_run, post-cutoff, nem jóváhagyott értékelés, alátámasztatlan tény, kitalált hivatkozás, hiányzó proveniencia, bizalom- / likelihood-változás, attribúció-erősítés / -törlés, kritikus szemantikus eltérés, nyugtázatlan figyelmeztetés, jogosulatlan nyugtázás / tartalmi / security jóváhagyás, security a tartalmi előtt, PDF-verzió / hash eltérés, hiányos manifest, manifest-hash eltérés, elavult verzió kiadása, hiányzó jóváhagyások / QA, nem emberi és rossz szerepkörű kiadás, közvetlen RELEASED-írás; sikertelen kiadás után nulla részleges sor.

## ACCEPTANCE CORPUS

`tests/fixtures/phase6_acceptance/corpus.json` — szintetikus „Northland” anyag (nem Gold Standard): 24 QA-forgatókönyv (verziómutáció × címkézett M10-S viselkedés: szabályalapú, engedelmes, javítani próbáló, kitalált hivatkozású, provider-hibás) és 17 workflow-forgatókönyv (emberi / nem emberi akciók). Eredmény: 41/41 az elvárásnak megfelelően; 32 QA-eredmény, 33 M10-S futás, 3 kiadás. Metrikák: `docs/cg6-acceptance-metrics.json` — minden kötelező metrika 0.

## TESTS ACTUALLY RUN

- Teljes Python-tesztkészlet (throw-away PostgreSQL 16, `-W error::DeprecationWarning`): lásd TEST RESULTS.
- Phase 6 tesztek: 29 (D 5, S 5, AP 3, R 4, W 2, RB 9, A 1).
- Web: `npx vitest run`, `npx tsc --noEmit`, `npx next build`.
- `scripts/prompt_registry.py check-lock`, `scripts/secret_scan.py`, gitleaks (pinned 8.24.3; `git` mód teljes történeten).
- CI (GitHub Actions: secret-scan, python-tests, web) a záró commiton.

## TEST RESULTS

- Teljes készlet: **561 / 561 PASS** (Phase 6: 29 / 29; Phase 1–5: 532 / 532).
- Web: **35 / 35** (4 fájl), TypeScript PASS, production build PASS.
- Prompt lock: PASS (9 bundle, benne `M10_QA_AUDITOR/1.0.0`). Secret scan: clean. Gitleaks (git-történet): no leaks.
- CI: a záró commit futását a commit után rögzítem (PROJECT_STATUS).

## PHASE 1–5 REGRESSION STATUS

532 / 532 PASS — változatlan Phase 1–5 viselkedés; a Phase 5 PREVIEW renderelés bájtra azonos; a `report_versions.state` továbbra is csak DRAFT_VERSION; DC-01 (egyetlen bizalom-tulajdonos) érvényes — egyetlen Phase 6 tábla sem tartalmaz bizalom-oszlopot.

## CG6 ACCEPTANCE CRITERIA PASS/FAIL

| # | Kritérium | Eredmény |
| --- | --- | --- |
| 1 | verzió / hash QA-kötés megsértése = 0 | PASS (`qa_binding_violations` 0; kompozit FK) |
| 2 | elfogadott alátámasztatlan tény = 0 | PASS |
| 3 | elfogadott episztemikus erősítés = 0 | PASS |
| 4 | elfogadott attribúció-vesztés = 0 | PASS |
| 5 | elfogadott post-cutoff / hindsight = 0 | PASS |
| 6 | elfogadott proveniencia-hiány = 0 | PASS |
| 7 | M10 report-javítás = 0 | PASS |
| 8 | eligibility-be nyugtázott CRITICAL = 0 | PASS |
| 9 | nyugtázatlan figyelmeztetéssel kiadott = 0 | PASS |
| 10 | jogosulatlan tartalmi jóváhagyás = 0 | PASS |
| 11 | jogosulatlan security jóváhagyás = 0 | PASS |
| 12 | nem RELEASE_AUTHORITY kiadás = 0 | PASS |
| 13 | érvényes QA nélküli kiadás = 0 | PASS |
| 14 | tartalmi jóváhagyás nélküli kiadás = 0 | PASS |
| 15 | security jóváhagyás nélküli kiadás = 0 | PASS |
| 16 | elavult verzió kiadása = 0 | PASS |
| 17 | PDF / verzió / hash eltéréssel kiadott = 0 | PASS |
| 18 | manifest teljesség / hash hibával kiadott = 0 | PASS |
| 19 | részleges / nem atomikus RELEASED = 0 | PASS |
| 20 | kiadott report / verzió / PDF / manifest módosítása = 0 | PASS |
| 21 | M10-S model_run nyomonkövetési hiány = 0 | PASS |
| 22 | GS answer-key szivárgás = 0 | PASS (statikus + 33 elküldött envelope) |
| 23 | audit hash-lánc hiba = 0 | PASS (1 817 bejegyzés) |
| 24 | Phase 1–5 regresszió = 0 | PASS (532 / 532) |
| 25 | minden Phase 6 elfogadási viselkedés PASS | PASS (100 / 100, nyomonkövetés: `docs/phase6-test-traceability.md`) |
| 26 | prompt lock PASS | PASS |
| 27 | secret scan / gitleaks clean | PASS |
| 28 | web typecheck / teszt / build PASS | PASS |
| 29 | DEV smoke PASS | **PO-ra vár** (a migrációk DEV-alkalmazása és a smoke futtatása a PO lépése; várt 61 / 61) |
| 30 | Phase 7 NEM indult | PASS |

Összesítve: 29 / 30 PASS; a 29. kritérium a PO DEV-futtatására vár. **CG6 ajánlás: APPROVED, ha a DEV smoke 61 / 61 PASS** — a döntés a PO-é.

## DEV SMOKE STATUS

Még nem futott DEV-en. A PO teendője (a repó gyökeréből, `C:\Users\bdatA\lfhe`, a már ismert környezeti változókkal):

```powershell
git pull
python scripts/apply_migrations.py $env:LFHE_DEV_DB_URL
python scripts/supabase_dev_smoke.py | Out-File -Encoding utf8 dev-smoke-phase6.json
```

Várt eredmény: **40 migráció** (új: `20261011003800_p6_qa.sql`, `20261011003900_p6_approval_release.sql`), **smoke 61 / 61 PASS** (50 korábbi + 11 Phase 6; a service-role ellenőrzés továbbra is opcionális). A smoke nem futtat QA-t és nem ad ki reportot. Jelszó, token vagy kulcs nem kell; csak a JSON-kimenet.

## KNOWN FAILURES

Nincs ismert hibás teszt. Megjegyzések:
- A `next build` első futásra egy Next.js biztonsági figyelmeztetéssel („known security vulnerability”, frissítési javaslat) megállt; újrafuttatva hiba nélkül lefutott, és a CI `web` jobja sikeres. A Next.js-frissítés nem része a Phase 6-nak (függőségváltozás) — PO-döntésre bízott nyitott tétel.
- Az első Phase 6 CI-futás (`91e45e4`) a CI-runner Chromium-sandboxa miatt bukott (Ubuntu 24.04 user-namespace korlátozás); javítva (`47eec80`, SD6-17).

## SECURITY NOTES

- Nincs titok kódban, Gitben, promptban, fixture-ben, manifestben, logban vagy PDF-metaadatban; a release-PDF tároló-kulcs tartalom-címzett hash. A provider-kulcs továbbra is csak a környezetből.
- Chromium offline, eldobható profillal; `--no-sandbox` csak root-konténerben / user-namespace nélküli CI-runneren (`LFHE_CHROMIUM_NO_SANDBOX`), mert a bemenet saját, escape-elt, script nélküli HTML.
- A guard-trigger tokenjét elvileg a DB-tulajdonos (DBA) kézzel beállíthatná; az alkalmazás-szerepkörök nem. Ez DBA-szintű bizalmi határ, mint a többi tulajdonosi művelet.
- M10 nem fér hozzá benchmark-anyaghoz; a GS-izoláció statikus és futásidejű ellenőrzése 0.

## ANALYTICAL-INTEGRITY NOTES

- M10 nem analitikai autoritás és nem javít; a kombinált státuszt az adatbázis számolja; az emberi felelősség (nyugtázás, tartalmi döntés, security, kiadás) M10-en kívül van.
- A determinisztikus réteg a Phase 5 validátort újrafuttatja a tárolt verzión, így a szemantikus réteg elmaradása sem enged át olyan hibát, amit a determinisztikus szabályok elkapnak; a szemantikus-only esetek (hatókör-bővítés, ellentmondás-semlegesítés) igazoltan az M10-S-en buknak el — valós modellnél ez a modell minőségén múlik (nem mérve).
- REPLAY: a jóváhagyás időpontja nem ismeret; egy később jóváhagyott, de a cutoffkor nyilvános bizonyítékon alapuló értékelés jogosult (lezárt Phase 3–4 szemantika). Ezt az elfogadási korpusz pontosította (Q21: cutoff a bizonyíték nyilvánossá válása elé).

## SPECIFICATION DEVIATIONS

Egyik sem önjóváhagyott; PO-döntésre bízva.

- **SD6-01** — Szabály: a baseline nem rögzíti, ki indítja a QA-t. Megvalósítás: HUMAN_ONLY `request_report_qa`, `REPORT_EDIT` vagy `REPORT_CONTENT_APPROVE` (új jogosultság nélkül), csak a legújabb, hossz-felülvizsgálat nélküli, nem kiadott verzióra. Indok: a QA legyen tudatos emberi beküldés, és ne fusson elavult / függő draftokon.
- **SD6-02** — Szabály: tartalmi döntés APPROVE / RETURN_FOR_REVISION / REJECT; magasabb szótár, ha van. Megvalósítás: zárt text-szótár (a `review_decision` enumban nincs RETURN_FOR_REVISION), új audit-kód `REPORT_CONTENT_DECIDED`. Indok: nincs pontos egyenértékű kód; a baseline megengedi a minimális új kódot.
- **SD6-03** — Szabály: security PENDING → döntés. Megvalósítás: a PENDING sort a tartalmi APPROVE nyitja (rendszer), a döntés egy második, a PENDING-re hivatkozó immutábilis sor. Indok: append-only történet állapot-UPDATE helyett.
- **SD6-04** — Szabály: RELEASED + manifest atomikusan; a report-verzió immutábilis. Megvalósítás: RELEASED külön `report_releases` sor; guard-trigger tranzakció-lokális tokennel. Indok: DC6-01 + a közvetlen írás tiltása a tulajdonosra is.
- **SD6-05** — Szabály: meglévő tároló-absztrakció; hash ellenőrzése kiadás előtt. Megvalósítás: a PDF-bájtok a write-once tárolóba ÉS a DB-sorba (`bytea`) is kerülnek. Indok: a release-tranzakció az adatbázisban újraszámolja a SHA-256-ot a tárolt bájtokon.
- **SD6-06** — Szabály: renderer verzió + hash. Megvalósítás: `renderer_hash = SHA-256(JCS(identitás))`, identitás = PDF-renderer verzió, HTML-renderer verzió + forrás-hash, PDF-modul forrás-hash, Chromium-verzió, template verzió / hash; a Chromium-bináris nincs hash-elve. Indok: hordozható, újraszámolható azonosság.
- **SD6-07** — Szabály: a PDF nem tartalmazhat a kanonikus / determinisztikus forrásban nem szereplő tartalmat. Megvalósítás: RELEASE-változat = ugyanaz a renderelés, csak a „draft preview, not released” sáv / cím helyett release-sáv. Indok: a kiadott PDF nem állíthatja magáról, hogy nem kiadott.
- **SD6-08** — Szabály: a lánc szerint a PDF a security review után. Megvalósítás: a PDF-job az APPROVED security review-ra indul; a security reviewer az azonos törzsű determinisztikus preview-t nézi; `request_release_pdf` (RELEASE_DECIDE) újrarenderelésre. Indok: a lánc sorrendje; a PDF a kiadási jelölt artefaktuma.
- **SD6-09** — Szabály: „minden nyugtázást igénylő figyelmeztetés”. Megvalósítás: minden WARNING finding nyugtázást igényel; nyugtázás sosem öröklődik QA-eredmények között. Indok: a baseline „default safest” iránya.
- **SD6-10** — Szabály: a magasabb rendű manifest-specifikáció (Prompt Pack v1.2.1 11. pont, CG0 E.19) mezőit meg kell őrizni. Megvalósítás: a v1.2.1 11. pont szövege nincs a repóban; a manifest a §23 listát + K-09 + analitikai pineket (jóváhagyás-id-kkal) + a szerző M09-futást tartalmazza. Indok: amit a tárolt specifikáció előír, az mind benne van; ha a v1.2.1 11. pont további kötelező mezőt tartalmaz, előrefelé bővíthető (kérem a PO megerősítését).
- **SD6-11** — Szabály: M10-S szemantikus ellenőrzések. Megvalósítás: a tesztek a valós bundle-t, bemenet-építőt és ingestiont használják, de a modell helyén szabályalapú helyettesítő / címkézett scriptelt viselkedés áll. Indok: valós provider-próba nem blokkoló; a szerződés teljesen tesztelt, a modell detektálási minősége nem.
- **SD6-12** — Szabály: M10-D ellenőrzési lista. Megvalósítás: plusz determinisztikus ellenőrzés: utasításszerű szöveg a reportban → CRITICAL (`STRUCTURE / EMBEDDED_INSTRUCTION_IN_CONTENT`). Indok: §27 (a jóváhagyott forrásból átvett injekció a szemantikus réteget is megkerülhetné).
- **SD6-13** — Szabály: QA-14 OSINT-határ, kétes esetben ember. Megvalósítás: minősítési / kezelési jelölések regex-listája → CRITICAL; forrás `access_restrictions` → WARNING (emberi kezelés). Indok: a sémában nincs „tiltott” forráskategória (minden regisztrált forrás nyilvános OSINT-típus).
- **SD6-14** — Szabály: QA-03 strukturált dátum-kapcsolatok. Megvalósítás: jóváhagyás az értékelés után és a report-verzió előtt; a bizonyíték a report-verzió előtt letöltve. Indok: eseményidő nem kritérium; a claim-dátumokat a Phase 2–4 már ellenőrzi.
- **SD6-15** — Szabály: M10-S ingestion. Megvalósítás: a tárolt `parsed_output` az auditált eredmény; eltérő hívói eredmény → `RESULT_NOT_FROM_MODEL_RUN`. Indok: a worker ne adhasson be mást, mint amit a modell adott.
- **SD6-16** — Szabály: előrefelé migrációk. Megvalósítás: a 3800 / 3900 az első push után, de minden telepítés előtt helyben pontosítva (ingestion-forrás, utasítás-ellenőrzés, checklist-tétel, guard-trigger). Indok: mint SD5-20; DEV-en még egyik sem futott.
- **SD6-17** — Szabály: headless Chromium. Megvalósítás: `--no-sandbox` root-konténerben vagy `LFHE_CHROMIUM_NO_SANDBOX=1` esetén (CI). Indok: Ubuntu 24.04 runneren a Chrome-sandbox nem indul; a bemenet saját, offline HTML.
- **SD6-18** — Szabály: kiadási döntések. Megvalósítás: `decide_release` csak érvényes jelöltre, jelöltenként egyszer; RETURN / REJECT után a jelölt nem adható ki. Indok: egy visszaküldött jelölt kiadása csak új verzióval / új láncon.
- **SD6-19** — Szabály: workflow-állapotok. Megvalósítás: a baseline állapotain túl származtatott CONTENT_RETURNED_FOR_REVISION, CONTENT_REJECTED, SECURITY_*, RELEASE_*, SUPERSEDED. Indok: a nézet minden emberi döntést megkülönböztet; nem tárolt állapot.

## CHANGE REQUESTS

Nincs (CR6: —). Nem találtam olyan valódi ellentmondást, amely bármely részt blokkolna; az SD6-10 egy megerősítést kér.

## OPEN ITEMS

Nem blokkoló (a PO eddigi döntése szerint):
- DEV: a 3800 / 3900 alkalmazása és a smoke (61 / 61) — PO.
- `/reports` (most már QA / release nézetekkel) böngészős végigkattintása DEV-en.
- K-11 / GS-001 Patriot-csapda tesztcsatorna.
- Valós provider-próba (M07–M10), benne az M10-S detektálási minősége.
- Phase 4 review UI.
- Opcionális service-role smoke-ellenőrzés.
- Next.js biztonsági frissítés (a build-eszköz jelzése alapján) — külön PO-döntés.
- SD6-10: a v1.2.1 11. pont manifest-mezőinek megerősítése.

## RECOMMENDED NEXT ACTION

1. A PO alkalmazza a két új migrációt DEV-en, futtassa a smoke-ot, és küldje vissza a JSON-t (várt: 40 migráció, 61 / 61 PASS).
2. A PO döntsön az SD6-01 … SD6-19 eltérésekről és a CONTROL GATE 6-ról.
3. Phase 7 csak egy verziózott Phase 7 baseline és kifejezett PO-felhatalmazás után indulhat (SD-12).

**STOP — Control Gate 6, PO-döntésre vár.**
