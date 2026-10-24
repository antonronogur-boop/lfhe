# LFHÉ — CONTROL GATE 7 REPORT (EVIDENCE PACK)

## PHASE / GATE

- Fázis: **Phase 7 — Controlled Operational Pilot & Validation** (`docs/specs/LFHE_Phase7_Authoritative_Baseline_v1.0.md`,
  SPEC_INDEX 26; PO felhatalmazás `docs/specs/PO_Decision_2026-10-23_Authorise_Phase7.md`, SPEC_INDEX 27).
- Kapu: **CONTROL GATE 7 — PO DECISION REQUIRED, de a bizonyítékcsomag még NEM teljes.** A P7-00 … P7-09 munkacsomagok
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
  (`lfhe_pilot.provider_trial`). A folyamat a valós Anthropic adapterrel, csonkolt HTTP-vel regressziós teszttel igazolt.
  **Valós hívás még nem történt.**
- **P7-04** — böngészős E2E: ellenőrzőlista és UX-rögzítés kész (`docs/runbooks/phase7-pilot.md` 5.); **a valós
  böngészős végigjárás a PO feladata, még nem történt.**
- **P7-05** — kontrollált benchmark P7-BM-01 (`evaluation/p7-bm-01/benchmark.json`): 18 szintetikus eset (15 seedelt
  hiba, 3 tiszta), 24 emberi címke; futtató `tests/pilot/test_p7_benchmark.py`; D és S külön.
- **P7-06** — pilot-ciklusok: instrumentáció és munkamenet kész; **0 / 6 ciklus** (valós naptári idő és PO-működtetés kell).
- **P7-07** — reprodukálható metrikák és kapacitásszámítás (`services/pilot/lfhe_pilot`), export
  (`scripts/pilot_export.py`, csak olvasó, titok- és címke-szűrt).
- **P7-08** — előzetes findings / capability assessment: `docs/phase7-pilot-findings.md`.
- **P7-09** — ez a jelentés; teszt-nyomonkövetés `docs/phase7-test-traceability.md`; metrika-export minta
  `docs/cg7-benchmark-test-double.json`.

## FILES CHANGED / MIGRATIONS ADDED

- Migráció (új, előrefelé): `database/migrations/20261011004100_p7_pilot_instrumentation.sql`. **Összes: 42.**
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

## AUTOMATED TEST RESULTS

- Teljes Python készlet: **576 passed, 1 skipped** (a skipped = a valós-provider próba, amely csak
  `LFHE_P7_PROVIDER=anthropic` mellett fut). Phase 7: 13 / 13 PASS (+1 kihagyott valós-provider teszt).
- **Phase 1–6 regresszió: 563 / 563 PASS** (változatlan tesztek).
- Web: **44 / 44** (5 fájl), TypeScript PASS, production build PASS (a Next.js frissítési figyelmeztetés változatlan).
- Prompt lock: PASS. Secret scan: clean. Gitleaks (git-előzmény): clean.
- CI: zöld — run 40009048791, commit `cba45d1` (secret-scan, python-tests, web).

## DEV SMOKE RESULT

**PASS** (PO, 2026-10-23): 42 migráció, smoke **68 / 68 PASS**, ebből a 6 Phase 7 ellenőrzés 6 / 6 (pilot-táblák RLS-sel 13 / 13;
nincs közvetlen írás, a worker nem olvas pilot-adatot; 16 HUMAN_ONLY pilot-függvény, 0 kitett; viewer és ADMIN nem hozhat
létre ciklust; PILOT_LEAD-nek nincs analitikai / QA / jóváhagyási / biztonsági / kiadási joga; a 41 lezárt migráció megegyezik a
zárolással). Audit hash-lánc: PASS, 161 bejegyzés; pg_cron aktív. `docs/dev-smoke-20261023-phase7.json`.

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

Árak csak rögzített `pilot_provider_prices` mellett; nélküle a költség „ismeretlen”.

## BROWSER UX VALIDATION RESULT

**NOT YET EVIDENCED** (P7-04, PO).

## PILOT-CYCLE SUMMARY

0 / 6 teljes ciklus (REPLAY 0, LIVE 0). **NOT YET EVIDENCED.**

## BENCHMARK RESULT / M10-S EMPIRICAL QUALITY

- Valós M10-S: **NOT YET EVIDENCED** (1. kísérlet: minden M10-S hívás elutasítva — nem minőségmérés; S recall 0 / 11 itt nem a modell teljesítménye).
- Tesztdublőrrel (csak a mérőút regressziója, `docs/cg7-benchmark-test-double.json`): D — 13 címke, TP 13, FN 0, FP 10
  (tiszta eseteken 0), precision 0,5652, recall 1,0, kritikus kihagyás 0; S (szabályalapú stand-in) — 11 címke, TP 11,
  FN 0, FP 2 (tiszta eseteken 0), precision 0,8462, recall 1,0. A D réteg provider-független, így a D-eredmény a valós
  futásban is így várható; az S-eredmény nem a valós modell minősége.

## ANALYST-TIME / THROUGHPUT / CAPACITY-RELEASE MEASUREMENTS

**NOT YET EVIDENCED** (nincs ciklus). A számítás reprodukálható és tesztelt (§11 képletek, Decimal).

## ECONOMIC ASSUMPTIONS

Nincs rögzített költség-feltevés és provider-ár (szándékosan nincs alapérték). A PO rögzíti a `/pilot` oldalon.
Kapacitásérték ≠ pénzbeli megtakarítás; éves érték csak kontrollált, igényelhető heti értékből.

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

- **CR7-01 — IMPLEMENTED (B), PO-utasítás 2026-10-24 alapján; valós futás igazolása a PO-ra vár** (migráció `20261011004200`, `provider_fixed_sampling`): a `claude-sonnet-5-5` a `temperature` paramétert elavultnak jelöli (preflight: HTTP 400 `invalid_request_error`, "`temperature` is deprecated for this model."), a lezárt low-variance szabály (explicit `temperature ≤ 0,2`, M02–M10) pedig mindig küldi. Opciók: A) régebbi, `temperature`-t elfogadó modell kódváltozás nélkül; B) „provider által vezérelt mintavétel” konfiguráció (zárt szemantika változik); C) mindkettő. Részletek: `docs/cr7-01-proposal.md`.

## KNOWN FAILURES

- A Next.js `next build` első futása időnként a frissítési figyelmeztetésen megáll, újrafuttatva PASS (ismert, nem
  blokkoló; a biztonsági frissítés külső elérés előtt kötelező).

## OPEN ITEMS

1. ~~DEV: 4100 migráció + smoke~~ — kész (2026-10-23: 42 migráció, 68 / 68 PASS).
2. Szerepek: PILOT_LEAD kiosztása; külön DEV-felhasználók az elemzői / reviewer / security / release szerepekhez.
3. Költség-feltevés és provider-ár rögzítése.
4. Valós-provider próba (workflow és / vagy DEV worker) → trial + benchmark JSON.
5. Böngészős E2E végigjárás UX-megállapításokkal.
6. 6 pilot-ciklus (≥ 2 REPLAY, ≥ 2 LIVE), majd `scripts/pilot_export.py`.
7. A bizonyíték alapján a findings és a capability-ajánlás véglegesítése; K-11 / GS-001 csatorna (opcionális, §23);
   Phase 4 review UI és opcionális service-role smoke (korábbi nem blokkoló tételek).

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
| 15 | Költség-feltevések explicitek | PASS | nincs alapérték; kötelező explicit input; teszt 11 |
| 16 | Valós-provider futás megtörtént | NOT YET EVIDENCED | workflow / DEV worker kész |
| 17 | Valós-provider modell / konfig / prompt nyomonkövetés teljes | NOT YET EVIDENCED | §26 ellenőrzés kész, csonkolt adapterrel tesztelve |
| 18 | Provider-hibák és javító futások megőrizve | PASS | valós provider-hiba (HTTP 400) `PROVIDER_ERROR`-ként rögzítve, nem lett siker; QA fail closed (run 40102872833); repair-link tesztelve |
| 19 | M10-S valós minősége empirikusan mérve | NOT YET EVIDENCED | P7-BM-01 futtató kész |
| 20 | D és S QA külön mérhető | PASS | benchmark és ciklus-metrikák rétegenként |
| 21 | Böngészős E2E megtörtént | NOT YET EVIDENCED | P7-04, PO |
| 22 | UX-megállapítások rögzítve | NOT YET EVIDENCED | rögzítő felület kész |
| 23 | BLOCKING UX-hibák megoldva vagy az út használhatatlannak nyilvánítva | NOT YET EVIDENCED | lezárási szabály kikényszerítve |
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
| 39 | Phase 7 change requestek listázva | PASS | nincs |
| 40 | Későbbi fázis nem indult | PASS | — |

Összesítve: **PASS 26, FAIL 0, NOT YET EVIDENCED 14.**

## RECOMMENDED CAPABILITY VERDICT

**OPERATIONAL VALUE NOT YET VALIDATED.** A CG7-et a jelenlegi állapotban nem javaslom jóváhagyásra (a pilot végrehajtása
még nem igazolt); a döntés a PO-é.

## NEXT ACTION

A PO futtatja a DEV-migrációt és smoke-ot, majd a pilotot (`docs/runbooks/phase7-pilot.md`); a visszaküldött JSON-ok
(smoke, trial, benchmark, export) alapján frissítem a bizonyítékcsomagot. Más fázis nem indítható.
