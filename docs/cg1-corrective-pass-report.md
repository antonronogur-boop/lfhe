# LFHÉ — CG1 CORRECTIVE PASS REPORT

**Phase / gate:** Phase 1 / Control Gate 1. A Control Gate 1 még **nincs jóváhagyva**.
**Dátum:** 2026-10-11
**Hatókör:** csak a CG1-01…CG1-06 javítások készültek el. A Phase 2 nem kezdődött el, M02/M03 nincs.
**Commitok:** `b7108ec` (CG1-01) … `b83d0d0` (CG1-06), plusz a dokumentáció-commit.

A tesztszámok kumulatívak, az eredeti 133 tesztből indulnak. Minden „lefuttatva” jelölés tényleges futtatást jelent: ideiglenes PostgreSQL 16 klaszteren, `-W error::DeprecationWarning` mellett.

---

## CG1-01 — Nem újrapróbálható tételhibák

**STATUS:** RESOLVED

**FILES CHANGED:**
- `services/collector/lfhe_collector/collector.py`: `classify_run()`; tételenkénti `retryable` jelző; ugyanazon job korábban véglegesen elbukott URL-jei kimaradnak.
- `services/collector/lfhe_collector/http.py`: a `FetchError` dokumentációja.
- `tests/site_server.py`: 401-es útvonal.
- `tests/integration/test_collection.py`: a 403-as elvárás javítva; korábban `RetryableJobError` volt, most `PermanentJobError`.
- `docs/collection-semantics.md`

**MIGRATIONS:** nincs.

**TESTS ADDED:** `tests/integration/test_item_failures.py` (13 teszt).
- Végleges hibák, job-szinten ellenőrizve: 401, 402, 403, robots-tiltás, nem engedélyezett tartalomtípus.
- Átmeneti 5xx hiba.
- Vegyes hiba három job-kísérlettel.
- Részleges siker.
- `classify_run` táblateszt.

**TESTS ACTUALLY RUN:** a teljes Python csomag.

**RESULTS:** mind PASS.
- Véglegesen hibás tételnél a job `FAILED` lesz, nem keletkezik újrapróbálás, és a tétel kérésszáma egy (robots-tiltásnál nulla).
- Vegyes esetben három kísérlet alatt a `/forbidden.html` és az `/unauthorized.html` pontosan egyszer kapott kérést, a tranziens tétel háromszor. A második kísérlettől a kód `PERMANENT_FAILURE_NOT_RETRIED`.

**Determinisztikus szabály:**

| Helyzet | Run státusz | Job |
| --- | --- | --- |
| nincs hiba | `SUCCESS` | — |
| van sikeres és hibás tétel is | `PARTIAL` | nincs job-retry |
| minden hiba tranziens | `SOURCE_UNAVAILABLE` | retry |
| minden hiba végleges | `FAILED` | végleges hiba, nincs retry |
| vegyes | `FAILED` | retry csak a tranziens tételekre |

**REMAINING LIMITATIONS:** L-11. Egy későbbi, ütemezett új job ismét lekéri a korábban megtagadott tételt, ha a feed még listázza. Ez ütemezési intervallumonként egyszer történik, retry-hurokban soha.

## CG1-02 — Snapshot-identitás / provenance-revízió

**STATUS:** RESOLVED

**FILES CHANGED:**
- `services/collector/lfhe_collector/snapshots.py`: `source_state()`, előzetes ellenőrzés az objektumírás előtt.
- `services/shared/lfhe_shared/integrity.py`
- `services/shared/lfhe_shared/storage.py`: `iter_keys`, `find_unreferenced_objects`.
- `scripts/object_store_reconcile.py`
- `docs/snapshot-identity.md`

**MIGRATIONS:** `20261011000900_snapshot_source_state_identity.sql`
- új mezők: `source_state`, `source_state_sha256`;
- a `record_snapshot` a source state alapján dönt a duplikátumról;
- új `snapshot_state_is_current()` függvény.

**Identitásmodell:**
- **A. Forrás-snapshot identitás:** `lfhe-snapshot-state/1` RFC 8785 hash. Tartalma: tartalom-hash, final URL, médiatípus, cím, nyelv, minden forrás által közölt publikációs és frissítési időbélyeg mezővel és bázissal, felfedezési azonosítók (guid, feed-cím, szerző), retention mode.
- **Kizárva:** kozmetikai bájtok, fejlécek, redirect-lépések, letöltési idő, származtatott értékek.
- **B. Szövegidentitás:** `text_sha256`, változatlan maradt. Ha csak provenance változik, az új verzió szövege azonos hash-ű, így a spanok stabilak.

**TESTS ADDED:** `tests/integration/test_snapshot_identity.py` (7 teszt):
1. azonos nyers tartalom → `DUPLICATE`, nem keletkezik objektum;
2. kozmetikai változás → `DUPLICATE`, nincs árva objektum;
3. azonos törzs, új cím → új verzió;
4. azonos törzs, módosuló publikációs, elérhetőségi és frissítési metaadat → négy verzió, az első változatlan;
5. törzsszöveg-revízió;
6. a tárolt state függetlenül ellenőrizhető;
7. egyidejű betöltés hat szálon → egy `NEW`, öt `DUPLICATE`, egy sor, nincs árva objektum.

**TESTS ACTUALLY RUN:** a teljes csomag.

**RESULTS:** mind PASS.

**REMAINING LIMITATIONS:**
- Árva objektum továbbra is keletkezhet, ha a folyamat az objektumírás és a DB-beszúrás között összeomlik, vagy ha versenyhelyzetben eltérő bájtok érkeznek. Ezt a `object_store_reconcile.py` jelenti, de nem töröl.
- A 0900 előtti sorokban nincs state (L-12, csak teszt-adatbázisokban).

## CG1-03 — Rekurzív hitelesítőkulcs-tiltás

**STATUS:** RESOLVED

**FILES CHANGED:**
- `services/shared/lfhe_shared/credentials.py`
- `apps/web/lib/credentials.ts`
- `apps/web/lib/sources.ts`
- `apps/web/tests/sources.test.ts`

**MIGRATIONS:** `20261011001000_recursive_credential_keys.sql`
- `lfhe.is_credential_key()` és `lfhe.credential_key_paths()`: bármilyen mélységben, tömbökben is.
- BEFORE triggerek, amelyek csak az útvonalat adják vissza. A titok így nem kerül tárolásra, auditba vagy hibaüzenetbe.
- CHECK backstop a `sources.collection_config`, `model_configurations.settings` és `processing_jobs.payload` mezőkre.

**Döntés (dokumentálva):**
- A kulcsokat normalizálom: camelCase szétbontása, kisbetűsítés, `_` szegmensek.
- Tiltott, ha bármely szegmens: headers, header, auth, authorization, authentication, cookie(s), password(s), passwd, token, secret(s), apikey, credential(s), bearer.
- Tiltott, ha az **utolsó** szegmens `key` vagy `keys`.
- Engedélyezett a `keyword` és a `max_tokens` (a többes számú tokens szándékosan nincs tiltva).

**TESTS ADDED:**
- `tests/security/test_credential_keys.py` (8 teszt):
  - Python és DB paritás 34 kulcson és beágyazott dokumentumon;
  - közvetlen RPC: legfelső szint, beágyazott objektum, tömbön belüli objektum, többszörös tömb;
  - a titok nem szerepel a hibában, az auditban és a táblában;
  - update RPC;
  - tulajdonosi (owner) közvetlen UPDATE;
  - CHECK backstop letiltott triggerrel;
  - modellbeállítások és job payload;
  - ártalmatlan beágyazott konfiguráció elfogadva.
- Web: 2 vitest teszt.

**TESTS ACTUALLY RUN:** Python teljes csomag; `vitest` (12/12); `tsc`.

**RESULTS:** mind PASS.

**REMAINING LIMITATIONS:**
- Csak kulcsnév alapján szűr; titokszerű *értéket* ártalmatlan kulcs alatt nem ismer fel.
- A jogos `sort_key` jellegű mezőknek más nevet kell adni.

## CG1-04 — Domainen kívüli redirect

**STATUS:** RESOLVED

**FILES CHANGED:**
- `services/collector/lfhe_collector/http.py`: `redirect_guard`, `ExternalRedirectRejected`.
- `collector.py`: domain-guard.
- `docs/collection-semantics.md`

**MIGRATIONS:** `20261011001100_final_origin_provenance.sql`
- `final_origin_host`: generált mező.
- `final_url_in_source_domain`.
- A `record_snapshot` az adatbázisban is elutasítja a külső eredetet, ha az nem engedélyezett (`EXTERNAL_ORIGIN_NOT_ALLOWED`).

**Viselkedés:**
- `allow_external_links=false` esetén a redirect-lépést a kérés **előtt** ellenőrzöm. Ha kilép a domainből, az eredmény `EXTERNAL_REDIRECT_REJECTED`: ez szabály szerinti kihagyás, nem újrapróbálható. A külső hostot nem kérjük le, és nem tárolódik semmi.
- `true` esetén tárolódik, `final_url_in_source_domain=false` és `final_origin_host` jelöléssel.

**TESTS ADDED:** `tests/integration/test_redirect_provenance.py` (6 teszt):
- azonos domain;
- engedélyezett aldomain;
- külső domain `false` mellett, közvetlenül és aldomainen keresztül;
- külső domain `true` mellett;
- adatbázis-oldali védelem és hasonmás domain (`notexample.org`).

**TESTS ACTUALLY RUN:** a teljes csomag.

**RESULTS:** mind PASS.

**REMAINING LIMITATIONS:** a külső eredetű dokumentumok lineage-kezelése Phase 2+ feladat.

## CG1-05 — Model-run bemenet és kontextus hash-ei

**STATUS:** RESOLVED

**FILES CHANGED:**
- `services/shared/lfhe_shared/envelopes.py`
- `services/ai-orchestrator/lfhe_orchestrator/runner.py`
- `docs/model-run-traceability.md`
- `docs/prompt-versioning.md`
- ADR-0004 kiegészítése

**MIGRATIONS:** `20261011001200_model_run_input_context_hashes.sql`
- `envelope_sha256` (korábban `input_sha256`)
- `task_parameters`
- `input_manifest` és `input_snapshot_sha256`
- `context_manifest` és `context_snapshot_sha256`
- A két halmaz-hash-t az **adatbázis számolja és CHECK-kel érvényesíti**; a manifest-tételek (`object_type`, `object_id`, `content_sha256`) validáltak, duplikátum nem lehet.

**TESTS ADDED:**
- `tests/unit/test_envelopes.py` (6 teszt):
  - ismert vektor;
  - sorrendfüggetlenség;
  - az input és a kontextus hash-e szétválik;
  - a feladatparaméter csak az envelope-hash-t érinti;
  - manipuláció kimutatása;
  - hibás hivatkozás elutasítása.
- DB-paritás és hamisított halmaz-hash elutasítása (tulajdonosként is).

**TESTS ACTUALLY RUN:** a teljes csomag.

**RESULTS:** mind PASS.

**REMAINING LIMITATIONS:** az envelope törzsét Phase 1 nem tárolja, csak a manifesteket és a hash-eket. Ennek helye Phase 2 döntés.

## CG1-06 — Reprodukálható toolchain / CI

**STATUS:** RESOLVED (kiegészítve 2026-10-11 16:19-kor: a GitHub CI és a DEV Supabase smoke teszt is lefutott)

**FILES CHANGED:**
- `requirements/py313-test.lock`: hash-ellenőrzött, a tesztelt verziók.
- `.python-version` (3.13); `pyproject.toml`: `requires-python >=3.13,<3.14`.
- `apps/web/.nvmrc` (22).
- `.github/workflows/ci.yml`:
  - checksum-ellenőrzött gitleaks 8.24.3 a teljes git-előzményen;
  - lockból telepítés Python 3.13-ra;
  - web build.
- `scripts/supabase_dev_smoke.py`
- `docs/runbooks/dev-supabase-smoke.md`
- `docs/runbooks/environments.md`
- `README.md`

**MIGRATIONS:** nincs.

**TESTS ACTUALLY RUN:**
- A teljes Python csomag **friss, csak a lockból telepített Python 3.13 venv-ben**, kétszer egymás után.
- gitleaks 8.24.3 (`git` mód, a teljes előzmény: 21 commit).
- `next build` helyben.

**RESULTS:**

| Részfeladat | Eredmény |
| --- | --- |
| 1. lock | kész |
| 2. futtatókörnyezet | Python 3.13 a mérvadó |
| 3. GitHub CI | **PASS** — run 38143832019, commit `ada9a55` |
| 4. gitleaks | lefutott, **nincs szivárgás** a git-előzményben |
| 5. DEV Supabase | **PASS** — 13/13 migráció, a smoke teszt 16/16 ellenőrzése sikeres |

**REMAINING LIMITATIONS:**
- A DEV futtatást a Product Owner végezte a saját Windows gépén. Ott a Python-függőségek nem a Linux lockból települtek (`pip install -e .`, pl. pydantic 2.14.0 a lockban szereplő 2.13.5 helyett). A teljes tesztcsomag a lockból épített környezetben a CI-ben és helyben futott.
- A webes felületet böngészőben nem kattintottuk végig. A smoke teszt ugyanazokat a Supabase Auth, PostgREST és RPC hívásokat ellenőrzi, amelyeket a felület használ.

---

## UPDATED TEST TOTAL

**Python: 174 teszt, mind sikeres.** Megoszlás: unit 52, integration 96, security 16, acceptance 10. A Phase 1 végén 133 volt, tehát +41.
- Futott a fejlesztői környezetben és a lockból épített friss 3.13-as venv-ben is, összesen többször, hiba nélkül.

**Web:** vitest 12/12, `tsc` hibátlan, `next build` sikeres.

## GITHUB CI STATUS

**PASS** (kiegészítés, 2026-10-11 15:4x). Privát repó: `antonronogur-boop/lfhe`, push a `main` ágra, commit `ada9a55`.
- Run: https://github.com/antonronogur-boop/lfhe/actions/runs/38143832019 — mindhárom job `success`:
  - `secret-scan`: gitleaks 8.24.3 a teljes git-előzményen + repository secret scan;
  - `python-tests`: Python 3.13, hash-ellenőrzött lockból telepítés, prompt-lock ellenőrzés, teljes tesztcsomag PostgreSQL 16-on;
  - `web`: `npm ci`, typecheck, vitest, `next build`.
- A lépésszintű eredményeket a GitHub API-ból olvastam ki; a részletes naplókat a munkamenet proxyja nem engedi letölteni, ezért a CI-beli tesztszámot innen nem tudtam ellenőrizni.

## GITLEAKS STATUS

**LEFUTOTT (helyben), 8.24.3:**
- `gitleaks git`, 21 commit (a jelentés-commitot is beleértve): **nincs szivárgás**.
- `gitleaks dir`: 6 találat, mind a nem verziókezelt `apps/web/.next/` build-kimenetben. Ezek a Next.js által véletlenszerűen generált preview-kulcsok, nem kerülnek commitba.

A CI-ben ugyanez a bináris (checksum-ellenőrzéssel) a teljes előzményen lefutott: **success**.

## DEV SUPABASE SMOKE STATUS

**PASS** (2026-10-11, PO futtatta a saját gépén; a kimenet a beszélgetésben rögzítve).
- DEV projekt: `lfhe-dev` (külön LFHÉ szervezet, eu-north-1). `lfhe.deployment_environment = 'DEV'`. Az adatbázis nincs GitHubhoz kötve; a Data API „Automatically expose new tables” kapcsolója ki van kapcsolva.
- **Migrációk:** mind a 13 hiba nélkül lefutott (`scripts/apply_migrations.py`, Session pooler).
- **Smoke teszt: 16/16 PASS:**

| Ellenőrzés | Eredmény |
| --- | --- |
| migrációk jelen | PASS (13) |
| jelszavas bejelentkezés (admin, viewer) | PASS |
| RLS: anon nem olvashatja a `sources` táblát | PASS (HTTP 401) |
| RLS: viewer olvashatja a `sources` táblát | PASS (HTTP 200) |
| RLS: viewer nem lát audit sorokat | PASS (HTTP 200, üres) |
| viewer jogosultságai | PASS (`ARTICLE_READ`, `SOURCE_READ`) |
| HUMAN_ONLY: anon → `create_source` | PASS (HTTP 401) |
| HUMAN_ONLY: viewer → `create_source` | PASS (HTTP 403) |
| HUMAN_ONLY: **service_role** → `create_source` | PASS (HTTP 403) |
| CG1-03: beágyazott hitelesítőkulcs RPC-n át | PASS (HTTP 400, `CREDENTIAL_KEY_REJECTED`) |
| admin létrehoz forrást | PASS (HTTP 200) |
| jóváhagyás / aktiválás / deaktiválás | PASS (204/204/204) |
| audit: forrás-életciklus | PASS (4 eseménytípus) |
| audit: hash-lánc ellenőrzés | PASS (7 bejegyzés, head `21caf087…`) |
| pg_cron: `lfhe-enqueue-due-collections` ütemezve | PASS (`*/5 * * * *`, aktív) |
| pg_cron: sikeres futás | PASS (`succeeded`, 2026-10-11 14:15:00 UTC) |

- A DEV adatbázisban maradt egy `smoke-…` nevű, deaktivált forrás és a hozzá tartozó audit bejegyzések. A források szándékosan nem törölhetők.

## PG_CRON STATUS

**PASS** a DEV Supabase-en. A feltételes migráció létrehozta a `lfhe-enqueue-due-collections` jobot (jobid 1, `*/5 * * * *`, aktív), a `cron.job_run_details` táblában pedig sikeres (`succeeded`) futás szerepel 2026-10-11 14:15:00 UTC-kor.
- A smoke teszt a legutóbbi 15 perc sikeres futását fogadja el. Ez a futás a teszt indítása előtt pár perccel történt, de ugyanennek a jobnak valódi, sikeres futása.

## SPECIFICATION DEVIATIONS

| ID | Leírás |
| --- | --- |
| D-07 | `model_runs.input_sha256` → `envelope_sha256` átnevezés, `input_refs` törölve (CG1-05). Csak teszt-adatokat érint. |
| D-08 | Új Phase 1 kódok: `EXTERNAL_REDIRECT_REJECTED`, `PERMANENT_FAILURE_NOT_RETRIED`, `EXTERNAL_ORIGIN_NOT_ALLOWED`, `CREDENTIAL_KEY_REJECTED`. Additívak. |
| D-09 | A hitelesítőkulcs-szótár bővebb a PO által adott minimumnál (szegmens- és végződés-alapú); a `tokens` (max_tokens) szándékosan megengedett. |

D-01: a dokumentáció a PO feltétele szerint frissült. A tranzakciós visszagörgetés **nem** séma-visszaállítás.

## CHANGE REQUESTS

Nincs.

## OPEN ITEMS

- **K-05 OPEN.** Nem találtam ki forráslistát. A valós forrásokon történő validálás még hiányzik.
- A CG1-06 lezárult. Maradék: a webes felület kézi végigkattintása DEV-en (L-01, nem blokkoló).
- L-02 (S3), L-11, L-12.

**STOP.** A Phase 2 nem kezdődött el.
