# LFHÉ — CONTROL GATE 7 REPORT (EVIDENCE PACK)

## PHASE / GATE

- Fázis: **Phase 7 — Controlled Operational Pilot & Validation** (`docs/specs/LFHE_Phase7_Authoritative_Baseline_v1.0.md`,
  SPEC_INDEX 26; PO felhatalmazás `docs/specs/PO_Decision_2026-10-23_Authorise_Phase7.md`, SPEC_INDEX 27).
- Kapu: **CONTROL GATE 7 — OPEN; a bizonyítékcsomag még NEM teljes** (0 / 6 valós ciklus; verdikt: OPERATIONAL VALUE
  NOT YET VALIDATED). A P7-00 … P7-09 munkacsomagok
  implementációs része kész; a pilot-bizonyíték (valós provider, böngészős használat, 6 ciklus) a PO DEV / pilot
  futtatásaitól függ. A PO-döntés szerint a kapu nyitva marad, amíg elegendő bizonyíték nincs, vagy a PO kifejezetten
  el nem fogad egy dokumentált korai-leállítási készletet. Ez a jelentés nem jóváhagyás.
- CG1–CG6 nincs újranyitva; korábbi PO-döntés nincs újraértelmezve; a lezárt Phase 1–6 szemantika nem változott.
- **Későbbi fázis nem indult. Az implementáció a P7-09 után MEGÁLLT.**

## IMPLEMENTATION SUMMARY

- **P7-00** — baseline és PO-felhatalmazás szó szerint tárolva; SPEC_INDEX 26–27; PROJECT_STATUS „Phase 7 —
  AUTHORISED / IN PROGRESS”; CG1–CG6 CLOSED megerősítve; a 41 alkalmazott migráció SHA-256 zárolva
  (`database/migrations.lock.json`, `tests/unit/test_migration_lock.py`); munka a `main` ágon.
- **P7-01** — pilot adatmodell és instrumentáció (migráció `20261011004100`): ciklusok (mód, cutoff = a kötött reporté),
  pontos model_run-kötés (report-lánc vagy próba), szerveróra szerinti időszegmensek, comparator, NASA-TLX terhelés,
  UX-megállapítások + diszpozíciók, explicit költség-feltevés és provider-ár, dokumentált pénzbeli bizonyíték,
  értékelői benchmark (eset → pontos verzió / hash → emberi címke); hiányzó-mérés lista és fail-closed lezárás;
  PILOT_LEAD szerep; 16 HUMAN_ONLY pilot-függvény. Részletek: `docs/pilot-design.md`.
- **P7-02** — pilot munkafelület: `/pilot`, `/pilot/[id]` (ciklus, teljesség, idő szakaszonként start / váltás / stop,
  comparator, report- és futáskötés, provider-metrikák, UX, terhelés, lezárás, költség-feltevés, provider-ár).
- **P7-03** — valós-provider próba: DEV worker (pilot-ciklusokhoz kötve) és a kézi `pilot-real-provider` GitHub
  workflow (szintetikus lánc valós M07 → M08 → emberi jóváhagyás → M09 → M10-D + M10-S); §26 ellenőrzés
  (`lfhe_pilot.provider_trial`). Valós hívások: a `pilot-real-provider` workflow futásai (lásd REAL-PROVIDER TRIAL
  RESULT és BENCHMARK RESULT); DEV-pilot-ciklushoz kötött valós futás még nincs.
- **P7-04** — böngészős E2E: ellenőrzőlista és UX-rögzítés kész (`docs/runbooks/phase7-pilot.md` 5.); a technikai,
  automatizált böngészős E2E (CR7-03) PASS a helyi tesztveremben; **a humán P7-04 végigjárás a PO feladata: NOT YET
  EVIDENCED.**
- **P7-05** — kontrollált benchmark P7-BM-01 (`evaluation/p7-bm-01/benchmark.json`): 18 szintetikus eset (15 seedelt
  hiba, 3 tiszta), 24 emberi címke; futtató `tests/pilot/test_p7_benchmark.py`; D és S külön.
- **P7-06** — pilot-ciklusok: instrumentáció és munkamenet kész; **0 / 6 ciklus** (valós naptári idő és PO-működtetés kell).
- **P7-07** — reprodukálható metrikák és kapacitásszámítás (`services/pilot/lfhe_pilot`), export
  (`scripts/pilot_export.py`, csak olvasó, titok- és címke-szűrt).
- **P7-08** — előzetes findings / capability assessment: `docs/phase7-pilot-findings.md`.
- **P7-09** — ez a jelentés; teszt-nyomonkövetés `docs/phase7-test-traceability.md`; metrika-export minta
  `docs/cg7-benchmark-test-double.json`.
- **CR7-03 (PO-jóváhagyás 2026-10-30, SPEC_INDEX 31; `docs/cr7-03.md`; ág `cr7-03-pilot-operational-path`)** — a pilotot
  blokkoló rés megszüntetése: HUMAN_ONLY, auditált, idempotens kérés-út a meglévő M02 / M04 / M05 / M06 / M07 / M08
  jobokhoz (migráció `20261011004300`), webes munkafelület a claim → esemény → relevancia → értékelés → emberi review
  láncra (`/claims`, `/events`, `/assessments`, `/jobs`, döntési sorok), szerepkör-érzékeny alkalmazás-keret és
  dashboard, pilot-összesítő; böngészős E2E helyi tesztveremmel. Lezárt Phase 1–6 szemantika nem változott.

## FILES CHANGED / MIGRATIONS ADDED

- Migráció (új, előrefelé): `database/migrations/20261011004100_p7_pilot_instrumentation.sql` (pre-CR7-01 / CR7-03
  állapotban 42 volt; **aktuális összes: 44**, lásd 4200 CR7-01 és 4300 CR7-03).
  A 3800 / 3900 / 4000 és minden korábbi fájl változatlan (zárolás + teszt + DEV-ellenőrzés).
- Új: `database/migrations.lock.json`; `services/pilot/lfhe_pilot/{capacity,metrics,export,provider_trial}.py`;
  `scripts/pilot_export.py`; `evaluation/` (benchmark, README); `.github/workflows/pilot-real-provider.yml`;
  `apps/web/app/pilot/**`, `apps/web/lib/pilot.ts`, `apps/web/tests/pilot.test.ts`; tesztek:
  `tests/unit/test_migration_lock.py`, `tests/integration/test_p7_pilot.py`, `tests/pilot/*`,
  `tests/security/test_p7_label_isolation.py`; dokumentumok: `docs/pilot-design.md`, `docs/phase7-test-traceability.md`,
  `docs/phase7-pilot-findings.md`, `docs/runbooks/phase7-pilot.md`, ez a jelentés.
- Módosított: `pyproject.toml` (services/pilot), `scripts/supabase_dev_smoke.py` (+6 Phase 7 ellenőrzés),
  `apps/web/lib/auth.ts` (PILOT_* jogok), `apps/web/app/layout.tsx` (Pilot link), `docs/permission-matrix.md`,
  `docs/runbooks/dev-supabase-smoke.md`, `docs/SPEC_INDEX.md`, `docs/PROJECT_STATUS.md`.
- **CR7-03:** új migráció `database/migrations/20261011004300_cr7_03_workflow_job_requests.sql` (**összes: 44**; a
  lezárt 1–41 változatlan); `apps/web/{app,components,lib}/**` (új oldalak és design-rendszer); `tests/integration/
  test_cr7_03_requests.py`; `tests/e2e/**`; `apps/web/tests/workflow.test.ts`; `.github/workflows/ci.yml` (`e2e` job);
  `scripts/supabase_dev_smoke.py` (+3 CR7-03 ellenőrzés); dokumentumok: `docs/cr7-03.md`, runbook 3a, permission matrix.

## AUTOMATED TEST RESULTS

**Aktuális eredmény (2026-10-30, CR7-03 ág `cr7-03-pilot-operational-path`):**

- Teljes Python készlet: **592 passed, 1 skipped** (a skipped = a valós-provider próba, amely csak
  `LFHE_P7_PROVIDER=anthropic` mellett fut). Ebben: CR7-03 integráció **7 / 7**, technikai böngészős E2E **2 / 2**, a
  változatlan Phase 1–6 regresszió és a Phase 7 tesztek.
- Web: vitest **54 / 54** (6 fájl), TypeScript PASS, production build PASS.
- Prompt lock: PASS. Secret scan: clean. Gitleaks (git-előzmény): clean.
- CI (PR #1; secret-scan, python-tests, web, e2e — mind zöld):
  - CR7-03 implementációs CI (`5c37a02`): run 41025798079;
  - **pre-merge cleanup verification CI** a `fe4b29f` dokumentációs cleanup commit után: **run 41039249220** — ez a
    merge előtti ellenőrzési bizonyíték. (Az ezt követő, csak dokumentációs commitok CI-futásai nem kerülnek ide.)

*Történeti, pre-CR7-03 eredmény (2026-10-23, nem aktuális):* 576 passed / 1 skipped, web 44 / 44, CI run 40009048791
(`cba45d1`).

## DEV SMOKE RESULT

*Történeti, pre-CR7-03 DEV-állapot.* **PASS** (PO, 2026-10-23): 42 migráció, smoke **68 / 68 PASS**, ebből a 6 Phase 7 ellenőrzés 6 / 6 (pilot-táblák RLS-sel 13 / 13;
nincs közvetlen írás, a worker nem olvas pilot-adatot; 16 HUMAN_ONLY pilot-függvény, 0 kitett; viewer és ADMIN nem hozhat
létre ciklust; PILOT_LEAD-nek nincs analitikai / QA / jóváhagyási / biztonsági / kiadási joga; a 41 lezárt migráció megegyezik a
zárolással). Audit hash-lánc: PASS, 161 bejegyzés; pg_cron aktív. `docs/dev-smoke-20261023-phase7.json`.

**Aktuális:** a repóban (a CR7-03 ág beolvasztása után a `main`-en) **44 migráció** van (új: 4200 CR7-01, 4300 CR7-03). A
CR7-03 **még nincs a DEV-re alkalmazva**: a DEV frissítése, a 4300-as migráció és az ezt követő smoke (+3 CR7-03
ellenőrzés) a PO-ra vár; addig nincs a 44-es állapotra vonatkozó DEV smoke-bizonyíték.

## REAL-PROVIDER TRIAL RESULT / PROVIDER COST & LATENCY

**NOT YET EVIDENCED — 1. kísérlet: a provider minden hívást elutasított** (PO, 2026-10-24, GitHub run 40102872833,
`anthropic/claude-sonnet-5-5`; `docs/cg7-real-provider-attempt1-trial.json`, `…-benchmark.json`).

- Próba: az M07 hívás `PROVIDER_ERROR` / `PROVIDER_REQUEST_REJECTED` (HTTP 400, 479 ms, token nélkül); a lánc ott
  megállt. Benchmark: mind a 18 M10-S hívás eredménytelen (0 finding), minden eset FAIL.
- Értelmezés: **konfigurációs probléma (CONFIGURATION_PROBLEM), nem modellminőség.** A 2. futás preflightja szerint az ok:
  `temperature` is deprecated for this model (HTTP 400 `invalid_request_error`) → CR7-01 (PROPOSED).
- Pozitív biztonsági bizonyíték: a provider-hiba hibaként maradt (§26), a QA fail closed lett (egyetlen hibás modell-kimenet
  sem lett PASS), a futás §26 szerint nyomon követhető (provider, modell, konfiguráció-hash, prompt-hash, ingestion).
- Javítás a pilot-eszközökben (nem zárt kód): `scripts/provider_preflight.py` — a workflow a próba előtt egyetlen, az
  adapterrel azonos alakú kérést küld, és kiírja a HTTP-státuszt, a provider hibatípusát és -üzenetét (kulcs nélkül;
  `p7-preflight.json` az artifactban). A benchmark-kimenet esetenként rögzíti az M10-S futás státuszát, és sikertelen
  futásoknál `REAL_PROVIDER_RUNS_FAILED` evidencia-osztályt ad.

**2. kísérlet (CR7-01 után, 2026-10-24, run 40105881022, `claude-sonnet-5-5`, `provider_fixed_sampling`;
`docs/cg7-real-provider-attempt2-*.json`):**
- Preflight: HTTP 200 — a CR7-01 a provider-elutasítást megszüntette.
- Próba: M07 valós hívások (eredeti + 1 javító futás), egyenként ~27 s, ~3,8–4,1 ezer input- és ~4,1–4,3 ezer output-token;
  mindkét kimenet `SCHEMA_VALIDATION_FAILED` → a lánc ott megállt (helyes viselkedés: a hibás kimenet nem került be).
- Benchmark: mind a 18 M10-S kimenet `SCHEMA_VALIDATION_FAILED` → minden eset FAIL (fail closed); **nem minőségmérés**.
- Az ok (3. futás, run 40111028306, `trial_only`, diagnosztikával): a modell **nem kapja meg a kimeneti sémát** — a lezárt
  kérés-összeállítás az `output_schema.json`-t nem küldi, így a modell a mezőneveket / azonosító-mintákat kitalálja → **CR7-02
  PROPOSED** (`docs/cr7-02-proposal.md`; javítás a `cr7-02` ágon, `main` változatlan).
- **4. futás a `cr7-02` ágról** (run 40112066517, `trial_only`; `docs/cg7-real-provider-attempt4-cr7-02-branch-trial.json`): a teljes
  szintetikus lánc valós `claude-sonnet-5-5`-tel lefutott — M07 `ASSESSMENT_RECORDED` (30 s), M08 `CHALLENGE_RECORDED` (54 s), emberi
  jóváhagyás, M09 `REPORT_VERSION_RECORDED` (18 s), M10-D + M10-S → `PASS_WITH_WARNINGS` (48 s); 4 / 4 futás sémahelyes, javító futás
  nélkül, mind §26 szerint admissible. Össz. ~37,7 ezer input- és ~22,8 ezer output-token. A CR7-02-t a PO 2026-10-25-én jóváhagyta; a `main`-be olvasztva.
- (2. futás:) a sémahiba részleteit a harness akkor még nem exportálta. Pilot-eszköz bővítve: a kimenetek
  `schema_failure_diagnostics` mezőt kapnak (validációs hibák + a modellkimenet eleje / vége, csak szintetikus anyag), és a
  workflow `scope = trial_only` olcsó diagnosztikai futást tesz lehetővé. A javítás (ha a lezárt kimenet-feldolgozást
  érinti) PO-döntés.

Árak csak rögzített `pilot_provider_prices` mellett; nélküle a költség „ismeretlen”.

## BROWSER UX VALIDATION RESULT

**NOT YET EVIDENCED** (P7-04, PO) — az emberi böngészős végigjárást automatizálás nem helyettesíti (§17, P7-04).

Technikai bizonyíték (CR7-03, 2026-10-30): `tests/e2e/test_pilot_path_e2e.py` valódi böngészőben (Playwright /
Chromium), hat szereppel végigjárja a teljes utat helyi, eldobható veremben (PostgreSQL + PostgREST + teszt-auth +
Next.js production build + a valódi worker-hurok SYNTHETIC_TEST_ONLY modellel): M02-kérés → claim review → M05-kérés →
esemény review / állapot → M06 + relevancia-döntés → M07 (M08 automatikusan) → flag-diszpozíció → emberi jóváhagyás
végső bizonyossággal → candidate pool → M09 → QA (PASS_WITH_WARNINGS) → figyelmeztetés-nyugtázás (REVIEWER) → tartalmi
jóváhagyás (REVIEWER) → security review (SECURITY_REVIEWER) → release PDF + kiadás (RELEASE_AUTHORITY) → letöltött
`%PDF`, manifest-hash; pilot-ciklus COMPLETED (csak az eldobható DB-ben); VIEWER csak olvas, ADMIN-nak nincs elemzői
hatásköre. Eredmény: 2 / 2 PASS.

## PILOT-CYCLE SUMMARY

0 / 6 teljes ciklus (REPLAY 0, LIVE 0). **NOT YET EVIDENCED.**

## BENCHMARK RESULT / M10-S EMPIRICAL QUALITY

- Valós M10-S: **MÉRVE — valós `claude-sonnet-5-5`, a `main`-ről (CR7-01 + CR7-02), run 40203842179, 2026-10-25**
(`docs/cg7-real-provider-run5-main-*.json`). Mind a 18 M10-S futás `SUCCEEDED`, sémahelyes, javító futás nélkül.

| Réteg | Címke | TP | FN | FP | ebből tiszta eseteken | Precision | Recall | Kritikus kihagyás |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D (determinisztikus) | 13 | 13 | 0 | 10 | 0 | 0,5652 | 1,0 | 0 |
| S (valós M10-S) | 11 | 10 | 1 | 111 | 20 | 0,0826 | 0,9091 | 1 |

- **Detekció:** a valós M10-S a 11 seedelt szemantikai hibából 10-et megtalált (recall 0,91); **1 kritikus hibát kihagyott** (a
  kihagyott eset azonosítása a következő benchmark-futás esetenkénti bontásából).
- **Téves riasztás:** 121 nem-PASS jelzésből 111 nem címkézett; a **3 tiszta (seedeletlen) verzión 20 jelzés**, és mind a 3 tiszta
  eset FAIL lett (várt: PASS). A kombinált QA így **mind a 18 esetet FAIL-re** állította (a várt 3 PASS / 1 PASS_WITH_WARNINGS helyett).
- Értelmezés: a valós M10-S erős érzékenységű, de jelenlegi kalibrációjával **túlriaszt**; a rendszer biztonságosan (fail closed) viselkedik,
  de a tiszta anyagot is blokkolná → jelentős emberi QA-feloldási teher várható. A nem címkézett jelzések egy része lehet jogos
  megfigyelés a szintetikus anyagon (konzervatív FP-számítás); ennek szétválasztásához a benchmark-kimenet mostantól esetenkénti
  bontást ad (`per_case`: kihagyott címkék, a modell nem-PASS S-jelzései rövidítve).
- Kalibrálás (prompt / küszöb) a lezárt Phase 6 szemantikát érintené → csak külön CR-rel, a pilot bizonyítéka alapján (§4).

**Helyesbítés — 6. futás esetenkénti bontással (run 40206473436, 2026-10-25; `docs/cg7-real-provider-run6-main-*.json`):**
- S: 11 / 11 címke megtalálva (recall 1,0; kritikus kihagyás 0) — az előző futás 10 / 11-ével együtt: **recall 0,91–1,0, futásonként szóródik**.
- A „tiszta” esetek jelzéseit elolvasva: **a P7-BM-01 alapverziója nem tiszta.** A szintetikus fixture claim-attribúciója „the ministry”,
  a report viszont „The air force reported” / „a spokesman denied” szöveget ad; az AS3 (Northland, „expanding”) nem következik a
  claimekből; a KJ `contested=false`, holott alapja cáfolt; a „probably” likelihood-term nélkül áll. A valós M10-S ezeket **helyesen**
  jelezte (QA-01 ACTOR_MISMATCH, S19, QA-09, QA-17, QA-07).
- Következmény: a P7-BM-01 **precision / téves-riasztás értéke érvénytelen** (a címkekészlet a bázis valódi hibáit nem tartalmazza);
  a 2026-10-25-i „túlriaszt” értelmezést visszavonom. A detekciós (recall) mérés érvényes.
- Mellékmegállapítás: ugyanez a szintetikus anyag a Phase 4–6 elfogadási korpuszokban is szerepel; a determinisztikus réteg (D19 a
  kötelező attribúció **meglétét** ellenőrzi, nem a claim-attribúcióval való egyezését) és a szabályalapú tesztdublőr ezt nem jelezte —
  a valós M10-S igen. Ez a tesztdublőr-alapú elfogadási bizonyíték korlátja; lezárt viselkedést nem érint.
- Változékonyság: a 6. futás próbájában az M07 kimenetét az ingestion `OUTPUT_REJECTED`-del elutasította (`ATTRIBUTION_MISSING` AS1, AS2),
  a lánc ott megállt; a korábbi két futásban ugyanez sikeres volt (M07: 2 / 3 elfogadva). A lezárt védelem működött.
- Következő lépés: **P7-BM-02** — konzisztens, valóban hibamentes szintetikus alapverzió (emberi értékelői ellenőrzéssel), ugyanazokkal a
  seedelt hibákkal; ebből mérhető érvényesen a téves riasztás. **Elkészült (PO-engedély 2026-10-25):** `evaluation/p7-bm-02/`,
  `tests/pilot/bm02_fixture.py`; tesztdublőrrel minden várt állapot teljesül, a tiszta eseteken 0 jelzés; az alapot a PO
  véglegesen jóváhagyta és saját szöveggel rögzítette (`docs/specs/PO_Decision_2026-10-25_P7-BM-02_Clean_Baseline.md`, SPEC_INDEX 29);
  a fixture erre átírva, minden eset újragenerálva; valós futás: workflow `scope = benchmark_02_only` (a jóváhagyott alap
  commitja után indított futás számít; a korábbi alappal indított futás csak előzmény).
- **7. futás (run 40210889526, `2daa9f6`, `benchmark_02_only`; `docs/cg7-real-provider-run7-bm02-superseded-base*.json`) — CSAK ELŐZMÉNY:**
  a PO-jóváhagyás előtti (felváltott) BM-02 alappal futott (a kimenetben a régi szövegek: „4 tanker”, „the two official Northland
  statements conflict”, AS2 cáfoló bizonyíték nélkül). Nyers számok: D recall 1,0, kritikus kihagyás 0, tiszta FP 0; S recall 0,82
  (Q03 hatókör, Q09 QA-07 kihagyva), tiszta FP 2 (Q01 „FACT” kategória; Q24 az AS2 aszimmetrikus `contested` jelzése — ez a felváltott
  alap valódi hibája volt). A 19. kritérium bizonyítékaként **nem** használható; az `1b87d19` utáni futás szükséges.
- Korábbi kísérletek (nem minőségmérés): 1. — minden hívás elutasítva (`temperature`, CR7-01); 2.–3. — sémahibás kimenetek (a séma nem jutott el a modellhez, CR7-02).
- Tesztdublőrrel (csak a mérőút regressziója, `docs/cg7-benchmark-test-double.json`): D — 13 címke, TP 13, FN 0, FP 10
  (tiszta eseteken 0), precision 0,5652, recall 1,0, kritikus kihagyás 0; S (szabályalapú stand-in) — 11 címke, TP 11,
  FN 0, FP 2 (tiszta eseteken 0), precision 0,8462, recall 1,0. A D réteg provider-független, így a D-eredmény a valós
  futásban is így várható; az S-eredmény nem a valós modell minősége.

**P7-BM-02 — érvényes valós futás (run 40213605927, `7aea2bf` ⊇ jóváhagyott alap `1b87d19`; `claude-sonnet-5-5`, `provider_fixed`,
`benchmark_02_only`; `docs/cg7-real-provider-run9-bm02-main-*.json`) — a 19. kritérium bizonyítéka:**
- Lefutás: 18 / 18 M10-S hívás SUCCEEDED, 0 sémahiba, minden esethez van QA-eredmény. Az eredményt a workflow annotációból
  olvastam ki (secret scan után; `scripts/fetch_pilot_result.py`), nem kézi átadással.
- **D (determinisztikus):** 13 / 13 címke (recall 1,0), kritikus kihagyás 0, tiszta eseteken 0 jelzés; precision 0,52 (konzervatív).
- **S (valós M10-S):** 10 / 11 címke (recall 0,91), **kritikus kihagyás 1** (Q09, QA-07 `EPISTEMIC_STRENGTH_MISMATCH`);
  precision 0,22 (konzervatív: minden nem címkézett jelzés FP), tiszta eseteken 3 jelzés.
- Állapot-egyezés: 15 / 18 pontos; a 3 tiszta eset PASS helyett **PASS_WITH_WARNINGS** — egyik sem FAIL, tehát tiszta anyagon
  nincs blokkoló téves riasztás.
- Esetenkénti bontás (kézi átnézés, minden S-jelzés):
  - A seedelt eseteken **minden FAIL-szintű S-jelzés a beültetett hibára vonatkozik**; hibán kívüli FAIL 0. A konzervatív FP-szám
    zöme ugyanannak a hibának több ellenőrzésen (QA-01 / 06 / 07 / 09 / 17) történő ismételt, egybehangzó jelzése.
  - A Q09 „kritikus kihagyás” tartalmilag nem kihagyás: a modell QA-07-en CRITICAL FAIL-t adott, de
    `MATERIAL_EPISTEMIC_STRENGTH_INCREASE` kóddal a címkézett `EPISTEMIC_STRENGTH_MISMATCH` helyett (kód-szintű eltérés; a
    pontozás szigorú kódegyezést mér, ezen nem változtattam).
  - Hibán kívüli WARNING-ok két okra vezethetők vissza, mindkettő a jóváhagyott alap tényleges tulajdonsága:
    (a) az S3 „the available benchmark record” fordulata LIVE reportban értékelési keretre utal (Q01, Q02, Q24, Q21);
    (b) az RS4 szövege „remains contested”, de `contested=false` (INFORMATION_GAP a lezárt Phase 5 levezetés szerint nem vitatott;
    Q05, Q09, Q21). Ezek nem hibák a PO-döntés szerint, de a modell megfigyelése tárgyszerű.
- Korlát: egyetlen érvényes futás (a korábbi futások 0,82–1,0 S-recallt mutattak más alappal) → a szóródás nincs kimérve.
- 8. kísérlet (run 40212574426): technikailag sikeres, de az annotáció 4096 karakteren csonkult → az eredmény nem volt
  visszaolvasható, nem értékelt; javítva (`7aea2bf`, round-trip teszt).

## ANALYST-TIME / THROUGHPUT / CAPACITY-RELEASE MEASUREMENTS

**NOT YET EVIDENCED** (nincs ciklus). A számítás reprodukálható és tesztelt (§11 képletek, Decimal).

## ECONOMIC ASSUMPTIONS

A PO a DEV `/pilot` oldalán rögzítette (immutable rekordok; nincs alapérték):

- **Költség-feltevés `COST-2026-A`:** HUF, loaded hourly cost **6600**, heti 40 óra, évi 46 munkahét; alap: „597000 HUF
  net/month; estimated direct employer cost, 2026; excludes organisational overhead”.
- **Provider-ár:** `anthropic / claude-sonnet-5-5`, USD, input **2** / M token, output **10** / M token, hatályos
  **2026-09-28** (helyi dátum). Egy korábbi, téves hatálydátummal rögzített immutable ár-rekord is létezik; nem lett
  törölve vagy módosítva — **a későbbi, helyes dátumú rekord az alkalmazandó.**

Kapacitásérték ≠ pénzbeli megtakarítás; pénzbeli megtakarítás nincs állítva. Éves érték csak kontrollált, igényelhető heti
értékből; comparator nélkül (az első ciklus: `NONE`) az eredmény csak megfigyelési jellegű (observational only).

## PROVENANCE / SECURITY / AUDIT STATUS

- Provenancia: a Phase 1–6 lánc változatlan; ciklusonként a kiadott manifest újraellenőrzése (`p6_manifest_problems`)
  a metrikák része. Pilot-termékre: NOT YET EVIDENCED.
- Biztonság: pilot csak DEV / localhost, külső elérés nélkül (Next.js tétel külön követve, §29); provider-input csak
  szintetikus / publikus; kulcs csak a PO titoktárolóiban; címkék értékelői hozzáféréssel; worker nem olvas pilot-adatot.
- Audit: a pilot emberi döntései (ciklus létrehozás / kötés / lezárás, comparator, költség, ár, pénzbeli bizonyíték,
  UX rögzítés / diszpozíció, benchmark, címke) a hash-láncolt auditba kerülnek; az időzítő-telemetria nem (§21). A lánc
  ellenőrzése a tesztekben PASS.

## SPECIFICATION DEVIATIONS

SD7-01 … SD7-12 — `docs/pilot-design.md` „Specification deviations” táblázat (séma-elhelyezés, PILOT_LEAD szerep,
csak szerveróra szerinti idő, interakció = auditált döntés, lánc-alapú áteresztés, QA által detektált minőség,
benchmark a harnessben, valós-provider bizonyíték forrásai, terminális pilot-állapotok, nyers NASA-TLX, éves érték csak
kontrollált eredményből, a ciklus cutoffja = a report cutoffja).

## CHANGE REQUESTS

- **CR7-01 — IMPLEMENTED (B), PO-utasítás 2026-10-24 alapján** (migráció `20261011004200`, `provider_fixed_sampling`) — **igazolva**: a provider minden hívást elfogadott (runs 40105881022, 40111028306): a `claude-sonnet-5-5` a `temperature` paramétert elavultnak jelöli (preflight: HTTP 400 `invalid_request_error`, "`temperature` is deprecated for this model."), a lezárt low-variance szabály (explicit `temperature ≤ 0,2`, M02–M10) pedig mindig küldi. Opciók: A) régebbi, `temperature`-t elfogadó modell kódváltozás nélkül; B) „provider által vezérelt mintavétel” konfiguráció (zárt szemantika változik); C) mindkettő. Részletek: `docs/cr7-01-proposal.md`.
- **CR7-02 — APPROVED és a `main`-be olvasztva** (PO, 2026-10-25, SPEC_INDEX 28; merge `25043c2`, CI zöld: run 40203246537 / `3c5de52`; nem nyitja újra a CG2-t / Phase 2-t). Eredeti megállapítás (2026-10-24): a lezárt Phase 2 kérés-összeállítás a regisztrált `output_schema.json`-t nem küldi a modellnek; valós modellel minden modul kimenete sémahibás lesz (M07 diagnózis: kitalált mezőnevek, `S1` az `AS1` minta helyett, hiányzó burok). Javaslat: a séma a kérés része (trusted blokk az untrusted adat előtt), a prompt-csomagok és hashek változatlanok. Egyetlen érintett lezárt viselkedés: `render_messages` (a kérés felhasználói üzenete); minden más változatlan. Részletek és pontos előtte / utána: `docs/cr7-02-proposal.md`. A 19. kritérium csak a `main`-ről futtatott teljes valós P7-BM-01 benchmarkból lehet PASS.

- **CR7-03 — PO APPROVED (2026-10-30, SPEC_INDEX 31) · IMPLEMENTED ON BRANCH (`cr7-03-pilot-operational-path`, PR #1) ·
  automated tests PASS · technical browser E2E PASS · NOT YET DEPLOYED / APPLIED TO DEV · human P7-04 browser
  validation NOT YET EVIDENCED.** Tartalom:
  emberi kérés-út a meglévő M02 / M04 / M05 / M06 / M07 / M08 jobokhoz (HUMAN_ONLY, auditált `WORKFLOW_JOB_REQUESTED`,
  idempotens, a megfelelő emberi lépés jogosultságához kötött; M07 csak M06-ajánlás vagy auditált kézi kérés után) és a
  hiányzó munkafelület. Lezárt szemantika, szerepek, provider / modell, költség- és ár-rekordok változatlanok.
  Részletek: `docs/cr7-03.md`.

## KNOWN FAILURES

- Next.js 16.4.0 a (nem interaktív / agent) `next build` első futását egyszer megállítja a biztonsági frissítési
  ajánlással (`SecurityFatalError`), az ismételt futás lefut; `next dev` interaktív terminálban frissítési menüt mutat,
  amelynek alapértelmezett választása leállítja a szervert. Függőség nem frissült (PO); a webes felület DEV / localhost
  marad.  A biztonsági frissítés külső elérés előtt kötelező.

## OPEN ITEMS

1. ~~DEV: 4100 migráció + smoke~~ — kész (2026-10-23: 42 migráció, 68 / 68 PASS).
2. ~~Szerepek~~ — kész (PO): lfhe-admin → ADMIN, lfhe-viewer → VIEWER, lfhe-analyst → ANALYST + PILOT_LEAD,
   lfhe-reviewer → REVIEWER, lfhe-security → SECURITY_REVIEWER, lfhe-release → RELEASE_AUTHORITY; ADMIN és VIEWER nem
   kapott pilot-operatív többletjogot.
3. ~~Költség-feltevés és provider-ár~~ — kész (PO): `COST-2026-A`; `claude-sonnet-5-5` ára 2026-09-28-tól (ECONOMIC ASSUMPTIONS).
4. ~~Valós-provider próba + benchmark~~ — kész (lánc: run 40203842179; P7-BM-02: run 40213605927).
5. CR7-03 telepítése és DEV-validálása (az első mért ciklus előfeltétele): beolvasztás a `main`-be; DEV `git pull`;
   4300-as migráció; DEV smoke; worker M02–M10 konfigurációval és indítással; a BLOCKING UX-megállapítás rögzítése a
   `/pilot → UX findings` felületen, majd a humán ellenőrzés után diszpozíciója; humán P7-04 böngészős végigjárás
   UX-megállapításokkal (a technikai E2E nem helyettesíti).
6a. **First REPLAY readiness: NOT READY FOR P7C-REPLAY-01** — kizárólag az 5. pont lépései hiányoznak.
6. 6 pilot-ciklus (≥ 2 REPLAY, ≥ 2 LIVE; jelenleg 0 / 6; az első mért ciklus REPLAY: `P7C-REPLAY-01`), majd `scripts/pilot_export.py`.
7. A bizonyíték alapján a findings és a capability-ajánlás véglegesítése; K-11 / GS-001 csatorna (opcionális, §23);
   ~~Phase 4 review UI~~ (CR7-03) és opcionális service-role smoke.

## CG7 ACCEPTANCE CRITERIA (40)

| # | Kritérium | Állapot | Bizonyíték |
| --- | --- | --- | --- |
| 1 | Baseline és PO-felhatalmazás szó szerint tárolva | PASS | `docs/specs/…Phase7…`, SPEC_INDEX 26–27 (diff-ellenőrzött) |
| 2 | CG1–CG6 CLOSED marad | PASS | PROJECT_STATUS; semmi nincs újranyitva |
| 3 | Lezárt migráció nem módosult | PASS | `migrations.lock.json` + `test_migration_lock.py`; DEV: 41 / 41 egyezik a zárolással (smoke 2026-10-23) |
| 4 | Minden új migráció előrefelé | PASS | `test_new_migrations_are_forward_only` |
| 5 | Phase 1–6 regresszió zöld | PASS | 563 / 563 |
| 6 | Az instrumentáció nem módosíthatja az analitikai igazságot | PASS | táblázat-ujjlenyomat teszt; pilot-függvények csak pilot_* táblákat írnak |
| 7 | REPLAY / LIVE explicit | PASS | ciklus-mód, mismatch-elutasítás, CHECK |
| 8 | Pilot cutoff-szemantika megmarad | PASS | cutoff = report cutoff (`PILOT_MODE_OR_CUTOFF_MISMATCH`); benchmark REPLAY-eset |
| 9 | Analista-idő mérés létezik és nyomon követhető | NOT YET EVIDENCED | mechanizmus kész és tesztelt; pilot-mérés még nincs |
| 10 | Szakaszonkénti idő ahol szükséges | NOT YET EVIDENCED | mechanizmus kész; pilot-mérés még nincs |
| 11 | Áteresztési metrikák reprodukálhatók | NOT YET EVIDENCED | determinisztikus számítás tesztelve; pilot-adat nincs |
| 12 | Minőségi metrikák reprodukálhatók | NOT YET EVIDENCED | determinisztikus számítás tesztelve; pilot-adat nincs |
| 13 | Kapacitás-metrikák reprodukálhatók | NOT YET EVIDENCED | §11 számítás tesztelve; pilot-adat nincs |
| 14 | Kapacitásérték és pénzbeli megtakarítás nincs összemosva | PASS | külön mezők / tábla; teszt 13 |
| 15 | Költség-feltevések explicitek | PASS | nincs alapérték; kötelező explicit input; teszt 11; a PO rögzítette: `COST-2026-A`, provider-ár 2026-09-28-tól |
| 16 | Valós-provider futás megtörtént | PASS | run 40105881022: valódi M07 és M10-S hívások (provider-válaszazonosító, tokenek, latencia); a kimenetek sémahibásak — a minőség külön kritérium (19) |
| 17 | Valós-provider modell / konfig / prompt nyomonkövetés teljes | PASS | §26 ellenőrzés minden valós futásra admissible: modell, konfiguráció-hash (benne `provider_fixed_sampling`), prompt 1.0.0 + hash, ingestion, repair-link |
| 18 | Provider-hibák és javító futások megőrizve | PASS | valós provider-hiba (HTTP 400) `PROVIDER_ERROR`-ként rögzítve, nem lett siker; QA fail closed (run 40102872833); repair-link tesztelve |
| 19 | M10-S valós minősége empirikusan mérve | PASS | P7-BM-02 valós futás (run 40213605927, PO-jóváhagyott alap): S recall 0,91, 1 kód-szintű kritikus kihagyás (tartalmilag jelzett), tiszta eseteken 0 FAIL / 3 WARNING, hibán kívüli FAIL 0; D recall 1,0. **PO által elfogadva** (SPEC_INDEX 30; Q09 szigorú kihagyásként megtartva); korlát: n = 1 futás, nem stabil termelési becslés |
| 20 | D és S QA külön mérhető | PASS | benchmark és ciklus-metrikák rétegenként |
| 21 | Böngészős E2E megtörtént | NOT YET EVIDENCED | humán P7-04 (PO) hátra van; a technikai automatizált E2E (CR7-03) PASS, de nem helyettesíti |
| 22 | UX-megállapítások rögzítve | NOT YET EVIDENCED | rögzítő felület kész |
| 23 | BLOCKING UX-hibák megoldva vagy az út használhatatlannak nyilvánítva | NOT YET EVIDENCED | lezárási szabály kikényszerítve; a „No UI / request path …” BLOCKING megállapítás CR7-03-mal kezelve, DEV-en rögzítendő és humán ellenőrzés után diszponálandó |
| 24 | Benchmark-címkék izolálva | PASS | értékelői táblák / fájl; teszt 9, 19 |
| 25 | K-11 / GS izoláció ép | PASS | GS-izolációs tesztek változatlanul zöldek |
| 26 | Tiltott adat nem jutott providerhez | PASS | az eddigi provider-hívások csak szintetikus 'Northland' anyagot vittek (run 40102872833) — a DEV-pilot után újra megerősítendő |
| 27 | Emberi analitikai hatáskör ép | PASS | RBAC-teszt; PILOT_LEAD jogai |
| 28 | Emberi biztonsági hatáskör ép | PASS | Phase 6 hatáskör-kiosztás változatlan (teszt) |
| 29 | Emberi kiadási hatáskör ép | PASS | ugyanaz; worker / service_role / anon elutasítva |
| 30 | Provenancia teljes | NOT YET EVIDENCED | pilot-termék még nincs; ciklusonkénti manifest-ellenőrzés kész |
| 31 | A mérés nem gyengíti a kiadási védelmet | PASS | egyetlen Phase 6 objektum sem változott; pilot csak olvas |
| 32 | Minimális pilot-bizonyíték teljes VAGY PO által elfogadott korai leállítás | NOT YET EVIDENCED | 0 / 6 |
| 33 | Pilot-korlátok dokumentálva | PASS | `docs/phase7-pilot-findings.md` LIMITATIONS |
| 34 | Pozitív és negatív megállapítások is | NOT YET EVIDENCED | előzetesen rögzítve; a pilot után véglegesítendő |
| 35 | Nincs alátámasztatlan kereskedelmi termelékenységi állítás | PASS | nincs ilyen állítás |
| 36 | Capability-ajánlás készült | PASS | OPERATIONAL VALUE NOT YET VALIDATED |
| 37 | Nyitott tételek azonosítva | PASS | fenti OPEN ITEMS |
| 38 | Phase 7 eltérések listázva | PASS | SD7-01 … SD7-12 |
| 39 | Phase 7 change requestek listázva | PASS | CR7-01, CR7-02, CR7-03 (CHANGE REQUESTS) |
| 40 | Későbbi fázis nem indult | PASS | — |

Összesítve: **PASS 29, FAIL 0, NOT YET EVIDENCED 11.**

## RECOMMENDED CAPABILITY VERDICT

**OPERATIONAL VALUE NOT YET VALIDATED.** A CG7-et a jelenlegi állapotban nem javaslom jóváhagyásra (a pilot végrehajtása
még nem igazolt); a döntés a PO-é.

## NEXT ACTION

**DEV PILOT HOLD — LIFTED** (PO, 2026-10-25, SPEC_INDEX 30). Nincs M10-S kalibrációs CR; minden M10-S jelzés megőrzendő.
A 2026-10-25-i döntés előfeltételei közül (1) szerepek, (2) loaded-cost feltevés és (3) provider-ár **kész**; (4) humán
böngészős végigjárás és (5) UX-megállapítások hátra vannak. Más fázis nem indítható.

Aktuális (2026-10-30): a szerepek, a költség-feltevés és a provider-ár kész (PO). **NOT READY FOR P7C-REPLAY-01** — hátra
van: CR7-03 beolvasztása a `main`-be; DEV `git pull`; 4300-as migráció; DEV smoke; worker M02–M10 konfiguráció és indítás;
a BLOCKING UX-megállapítás rögzítése, majd humán ellenőrzés utáni diszpozíciója; humán P7-04 végigjárás. Utána az első
mért ciklus: REPLAY `P7C-REPLAY-01` (runbook 4. pont). 0 / 6 valós ciklus. CG7 **OPEN**; verdikt: **OPERATIONAL VALUE NOT
YET VALIDATED**.
