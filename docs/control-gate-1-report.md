# LFHÉ — Control Gate 1 jelentés

**PHASE / GATE:** Phase 1 — Foundation (P1-01 … P1-11) / Control Gate 1
**Dátum:** 2026-10-11 · **Repository HEAD:** a jelentést tartalmazó commit (P1-11 után)
**Állapot:** a Phase 1 kész, a munka **leállt**. Phase 2 nem kezdődött el.

## 1. IMPLEMENTED

| Lépés | Tartalom |
| --- | --- |
| P1-01 | Repo-váz, CI (gitleaks + saját secret-scan + tesztek), SPEC_INDEX, PROJECT_STATUS, ADR-0001…0007 |
| P1-02 | Környezetszétválasztás: statikus konfigurációs szabályok (PROD nem használhat LOCAL tárolót, dev/test URL-t) + az adatbázisban rögzített, megváltoztathatatlan `deployment_environment`, amelyet a worker csatlakozáskor ellenőriz |
| P1-03 | `lfhe` séma, kanonikus enumok (A3), checksumos migráció-futtató |
| P1-04 | Szerepkörök/jogosultságok, HUMAN_ONLY SECURITY DEFINER függvények (guardrail 2) |
| P1-05 | Sorosított SHA-256 hash-láncú audit, párhuzamossági bizonyítás, független Python-ellenőrző, lánc-fej export (guardrail 1) |
| P1-06 | Forrásnyilvántartás (DB + Next.js admin felület): létrehozás → gyűjtési módszer jóváhagyása → aktiválás |
| P1-07 | Idempotens táblaalapú job-sor (SKIP LOCKED, lease, exponenciális backoff), ütemező belépési pont, feltételes pg_cron |
| P1-08 | Udvarias HTTP kliens (robots.txt, throttling, méret- és típuskorlát, 401/402/403 nem kerülhető meg, SSRF-védelem), RSS/Atom, sitemap, hivatalos API és HTTP-fetch adapterek, collection run-ok és hibanapló |
| P1-09 | `articles`, verziózott **megváltoztathatatlan eredeti nyelvű** `article_snapshots`, `text_representations` (NFC, Unicode code point offset, DB által ellenőrzött SHA-256), write-once tartalomcímzett objektumtár, determinisztikus `lfhe-clean-text` 1.0.0, span-feloldó primitívek |
| P1-10 | Prompt-verzió igazságforrás és model-run nyomonkövethetőség (guardrail 3), RFC 8785 kanonikus JSON, `prompt_registry.py`, provider-absztrakció + FakeProvider |
| P1-11 | F1–F10 elfogadási tesztcsomag, backup/restore round-trip teszt, dokumentáció |

## 2. FILES CHANGED

112 verziókezelt fájl (a jelentéssel együtt), 14 commit. Főbb területek: `database/migrations/` (9), `services/shared/lfhe_shared/` (audit, canonical_json, config, db, hashing, jobs, prompts, spans, storage), `services/collector/lfhe_collector/` (adapters, collector, extract, http, snapshots, urls, worker), `services/ai-orchestrator/lfhe_orchestrator/` (providers, runner), `apps/web/` (login, sources), `scripts/` (apply_migrations, audit_tool, prompt_registry, secret_scan), `tests/` (unit, integration, security, acceptance, szintetikus fixture-ök), `docs/` (ADR-ek, permission-matrix, audit-catalogue, prompt-versioning, runbookok, PROJECT_STATUS), `packages/prompts/` (README + üres lock).

## 3. DATABASE MIGRATIONS

| Fájl | Tartalom |
| --- | --- |
| `20261011000100_foundation.sql` | szerepkörök, séma, enumok, deployment_environment, audit eseménykatalógus |
| `20261011000200_rbac.sql` | szerepkör/jogosultság modell, HUMAN_ONLY guard függvények, RLS |
| `20261011000300_audit.sql` | `audit_log`, hash-lánc, `write_audit`, általános audit trigger |
| `20261011000400_sources.sql` | `sources` + jóváhagyási/aktiválási függvények |
| `20261011000500_jobs.sql` | `processing_jobs`, `system_errors` |
| `20261011000600_collection_runs.sql` | `collection_runs`, `enqueue_due_collections()` |
| `20261011000601_pg_cron_schedule.sql` | feltételes pg_cron ütemezés |
| `20261011000700_articles_snapshots.sql` | `articles`, `article_snapshots`, `text_representations`, `record_snapshot()` |
| `20261011000800_prompts_model_runs.sql` | `lfhe_registrar`, `prompt_versions`, `prompt_activations`, `model_configurations`, `model_runs` |

Nincs down-migráció (lásd D-01).

## 4. TESTS RUN

`pytest -W error::DeprecationWarning` eldobható PostgreSQL 16 klaszteren a valódi migrációkkal (lokális Supabase-shim: `auth` séma, `anon`/`authenticated`/`service_role`):
unit 46 · integration 69 · security 8 · acceptance 10 = **133 teszt**.
Továbbá: `scripts/secret_scan.py`, `scripts/prompt_registry.py check-lock`, web: `tsc --noEmit`, `vitest` (10 teszt); a `next build` a P1-06-ban sikeres volt.

## 5. TEST RESULTS

- Python: **133 passed, 0 failed** — három egymást követő teljes futásban.
- Secret scan: **clean**. Prompt lock: **ok**. Web typecheck: **0 hiba**; vitest **10/10**.
- **Nem futott:** gitleaks (lokálisan nincs telepítve), a GitHub CI workflow (nincs push), web E2E élő Supabase ellen, S3 backend, pg_cron.

## 6. F1–F10 ACCEPTANCE CRITERIA

| # | Kritérium | Eredmény | Bizonyíték |
| --- | --- | --- | --- |
| F1 | Jogosult felhasználó létrehozhat forrást | **PASS** | `test_F1…` (ANALYST igen, VIEWER nem; új forrás inaktív/jóváhagyatlan) + `test_sources.py` |
| F2 | Aktiválás/deaktiválás jogosultság szerint | **PASS** | `test_F2…` (ANALYST nem, REVIEWER igen; jóváhagyás nélkül nem aktiválható; worker nem) |
| F3 | Jóváhagyott módszer cikket tölt le | **PASS — szintetikus forráson** | `test_F3…` ütemezett jobon át RSS-ből; valós forráson nem tesztelve, mert **K-05 OPEN** |
| F4 | Provenance tárolása | **PASS** | `test_F4…`: forrás, URL, cím, megengedett tartalomreprezentáció, publikációs, nyilvános elérhetőségi és letöltési metaadat, nyelv, tartalom-hash, snapshot metaadat |
| F5 | Újrafutás nem hoz létre kontrollálatlan duplikátumot | **PASS** | `test_F5…` (3 futás: 2/0/0 új), revízió → új verzió, az előző változatlan |
| F6 | Gyűjtési futások és hibák naplózása | **PASS** | `test_F6…` (SOURCE_UNAVAILABLE run, system_error, retry backoff-fal) |
| F7 | Kötelező műveletek auditálva | **PASS** | `test_F7…` + audit láncellenőrzés, `test_audit.py` (konkurencia, manipuláció-detektálás) |
| F8 | Nincs commitolt titok | **PASS** (gitleaks nélkül) | `test_F8…`, `secret_scan.py`, `.env*` nincs a repóban |
| F9 | Hitelesítés + szerveroldali jogosultságkezelés | **PASS — adatbázis-szinten** | `test_F9…`, `test_rbac.py`, `test_security_definer_hardening.py`; UI E2E élő Supabase-en nem (L-01) |
| F10 | Alap a jövőbeni pontos eredeti nyelvű snapshot-groundinghoz | **PASS** | `test_F10…`: ukrán szöveg pontos code-point span-feloldása; a szöveg megváltoztathatatlan; fordítás nem tárolható eredetiként |

## 7. KNOWN FAILURES

Nincs ismert hibás teszt. Ismert korlátok (PROJECT_STATUS L-01…L-10): web E2E élő Supabase nélkül; S3 backend nem tesztelt; pg_cron nem futott; CI nem futott GitHubon; per-process udvariassági limit; sorosított auditírás; árva (ártalmatlan, hash-nevű) objektum lehetséges DB-hiba esetén; csak FakeProvider; py3langid csak tartalék nyelvfelismerés.

## 8. SECURITY NOTES

- **Guardrail 1:** egyetlen advisory lock sorosítja az auditírást; 8 párhuzamos munkamenet × 12 írás után egyetlen, hézagmentes, ellenőrizhető lánc; független Python-ellenőrző és lánc-fej export; a lánc **tamper-evident, nem tamper-proof** (tulajdonos/szuperuser elvben átírhatja — ezt az exportált fej teszi detektálhatóvá).
- **Guardrail 2:** minden SECURITY DEFINER függvény rögzített `search_path`-szal; PUBLIC EXECUTE visszavonva (katalógus-alapú meta-teszt minden jövőbeni függvényre is); HUMAN_ONLY függvények: `authenticated` szerep + JWT + létező `auth.users` + nem worker; negatív tesztek: worker, registrar, service_role, anon, hamisított/nem létező felhasználó.
- **Guardrail 3:** lásd 9. pont és `docs/prompt-versioning.md`.
- A web alkalmazás nem használ service_role kulcsot (a konfiguráció kifejezetten elutasítja); a workerek saját, korlátozott `lfhe_worker` szerepkörrel futnak.
- Gyűjtés: robots.txt tiszteletben tartva; 401/402/403 nincs megkerülve, nincs újrapróbálva; privát címek, nem-http sémák és URL-be ágyazott hitelesítő adatok elutasítva; a forráskonfiguráció és a modellkonfiguráció nem tartalmazhat hitelesítő kulcsokat (DB CHECK); válaszfejlécekből csak fehérlistás mezők tárolódnak (cookie nem).
- Utasításszerű szöveg a forrásban adatként, változatlanul tárolódik; semmilyen pipeline nem értelmezi utasításként (Phase 1-ben nincs LLM-hívás valós providerrel).
- GS-001 válaszkulcs nem került a repóba, fixture-be, promptba.

## 9. ANALYTICAL-INTEGRITY NOTES

- **DC-01 betartva:** Phase 1-ben nincs semmilyen analitikai konfidencia-oszlop. A `public_availability_confidence` kizárólag időbélyeg-megbízhatóság (külön enum).
- **Három idő külön:** publikáció (csak ha a forrás kimondja, időzónával, a mező nevével), nyilvános elérhetőség (bázissal és megbízhatósággal), rendszer-letöltés. Eseményidő nem snapshot-attribútum. Dátum nélkül: NULL + `UNKNOWN` + `DATE_UNCERTAIN`; jövőbeli dátum: NULL elérhetőség + `LOW_CONFIDENCE_TIMESTAMP`; „updated”/lastmod soha nem publikáció.
- Snapshotok verziózottak és megváltoztathatatlanok; egy oldal későbbi módosítása új verziót hoz létre, a korábbit nem írja felül (replay-védelem).
- A szöveg eredeti nyelvű; `is_original_language` CHECK; fordítás nem tárolható; offsetek NFC szövegben Unicode code pointban, Python és PostgreSQL egyezően számol.
- Prompt: egy `prompt_versions` rekord **nem hivatkozhat eltérő tartalomra** (immutábilis sor, DB által számolt hash CHECK, ütközés azonos semver + eltérő tartalom esetén); aktiválás csak ember, indoklással, auditálva; minden model_run összetett idegen kulccsal kötve a regisztrált prompthoz (semver, hash, modulverzió) és modellkonfigurációhoz; sémahiba rögzül, nincs csendes javítás.
- M02–M10 promptok és analitikai logika nincsenek; csak szintetikus `T00_ECHO` fixture (PROD-ban nem aktiválható).

## 10. SPECIFICATION DEVIATIONS / ÉRTELMEZÉSEK (PO-jóváhagyásra)

| ID | Leírás |
| --- | --- |
| D-01 | Nincs down-migráció; visszafordíthatóság = fájlonkénti tranzakciós alkalmazás + fix-forward + backup/restore (round-trip tesztelve). |
| D-02 | Additív audit eseménytípusok („Phase 1 impl.”): DEPLOYMENT_ENVIRONMENT_SET, SOURCE_COLLECTION_METHOD_APPROVED/REVOKED, ARTICLE_CREATED, TEXT_REPRESENTATION_CREATED, PROMPT_VERSION_DEACTIVATED, MODEL_CONFIGURATION_REGISTERED. |
| D-03 | Új DB-szerepkör `lfhe_registrar` (regisztráció ≠ aktiválás); additív, a szerepkör-szétválasztást erősíti. |
| D-04 | Phase 1-ben a nyilvános elérhetőség bázisa az alap G-03 értékek egyike (SOURCE_PUBLISHED_TIMESTAMP / RSS_TIMESTAMP); a v1.2 §8 replay-szintű bázisok (pl. …WITH_FROZEN_SNAPSHOT) hozzárendelése a Phase 2+ replay-jogosultsági logikára marad. |
| D-05 | A model_run, collection_run, job és system_error rekordok maguk is megváltoztathatatlan működési naplók, nem duplikálódnak az audit logba. |
| D-06 | Lokális Python 3.13, a CI 3.12-vel van definiálva (nem futott). |

## 11. CHANGE REQUESTS

**Nincs.** A megvalósítás során nem merült fel olyan architekturális konfliktus, amely CR-t igényelt volna.

## 12. OPEN ITEMS

- **K-05 — OPEN.** A kezdeti 5–10 operatív forrás listája nem érkezett meg; **nem találtam ki forrásokat**. Minden gyűjtési teszt szintetikus, témasemleges fixture-ökön fut. Valós forrásokon az F3/F4/F5 nem lett validálva.
- K-01 worker hosting (ADR az első telepítés előtt).
- L-01…L-10 (PROJECT_STATUS).
- Phase 2-re halasztva: valós provider adapterek, untrusted-content envelope, modulonkénti modellválasztás, evidence span / claim táblák.

## 13. RECOMMENDED NEXT ACTION

1. PO-döntés a Control Gate 1-ről, beleértve a D-01…D-06 értelmezéseket.
2. K-05: a valós induló forráslista átadása (név, domain, nyelv, gyűjtési módszer, retention mode / jogosultság).
3. Javasolt, Phase 2 előtt: DEV Supabase projektre telepítés és smoke-teszt (L-01 web E2E, L-03 pg_cron, L-04 CI futtatás), majd a K-05 forrásokkal valós gyűjtési próba.
4. Phase 2 **csak kifejezett PO-jóváhagyás után** kezdődhet.
