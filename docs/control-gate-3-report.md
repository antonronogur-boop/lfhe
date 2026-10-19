# LFHÉ — CONTROL GATE 3 REPORT (Phase 3 — Lineage & Events)

**Dátum:** 2026-10-19 (frissítve a CG3 célzott javító kör és a végső javítás után) · **Alap:** Phase 3 Authoritative Baseline Addendum v1.0 (`docs/specs/LFHE_Phase3_Authoritative_Baseline_Addendum_v1.0.md`), PO-döntés „AUTHORISE PHASE 3” (`docs/specs/PO_Decision_2026-10-19_Authorise_Phase3.md`), valamint a jóváhagyott Phase 1/2 állapot (CG2 APPROVED) · **Repository:** `antonronogur-boop/lfhe` (privát)

## PHASE / GATE

**Phase 3 — Lineage & Events (M04 Lineage + M05 Event Builder): IMPLEMENTÁCIÓ KÉSZ, a CG3 célzott javító kör (CG3-01, CG3-02, CG3-03) lezárva. CONTROL GATE 3: a PO döntésére vár.** A Phase 4 nem kezdődött el.

- A PO 2026-10-19-én az SD3-01…SD3-11 pontokat **APPROVED** minősítéssel fogadta el. A CG3-at nem hagyta jóvá három implementációs hiba miatt (`docs/specs/PO_Decision_2026-10-19_CG3_Targeted_Corrective_Pass.md`).
- **CG3-01 RESOLVED, CG3-02 RESOLVED, CG3-03 RESOLVED.** Részletek: `docs/cg3-corrective-report.md`.
- A PO végső döntése (2026-10-19, `docs/specs/PO_Decision_2026-10-19_CG3_Final_Correction.md`):
  - CG3-02 és CG3-03: **RESOLVED / ACCEPTED**;
  - SD3-12: **APPROVED**;
  - CG3-01: elfogadva, kivéve az SD3-13-at.
- Az SD3-13-at a végső javítás (2600-as migráció) a jóváhagyott szemantikával váltja fel: *„Lineage retractions are themselves knowledge-bound. A retraction affects a historical run only when its supporting evidence is eligible for that run's cutoff.”* **A végső javítás RESOLVED.**

| Szerep | Commit |
|---|---|
| CG2 végső dokumentációs állapot (kiindulópont) | `8ff862f` |
| Phase 3 baseline verbatim tárolása (P3-00) | `8e8d5b0` |
| Phase 3 implementáció + dokumentáció, CI-tesztelt (CI run 39267104102: secret-scan, python-tests, web — mind success) | `2f0b50b` |
| Az első CG3-jelentés (átadott archívum `7197389`) | `6092849` / `7197389` |
| CG3 javító kör: 2300–2500 migráció + tesztek, CI-tesztelt (CI run 39274247863: secret-scan, python-tests, web — mind success) | `d3e1302` |
| Végső javítás: 2600 migráció + tesztek, CI-tesztelt (CI run 39279160435: mind success) | `128f1a7` |
| Javító kör dokumentációja | `2b40878` / `4ad7b02` |
| Végső jelentés és dokumentáció | `8b7e6ed` (FINAL DOCUMENTATION COMMIT) |

DEV Supabase: a Phase 3 migrációk (1800–2600) még nincsenek alkalmazva a DEV-en. A pontos parancsok: `docs/cg3-corrective-report.md` (DEV MIGRATION + SMOKE) és OPEN ITEMS.

## IMPLEMENTED

| Lépés | Tartalom | Commit |
|---|---|---|
| P3-00 | Baseline és PO-döntés verbatim a `docs/specs/` alatt; `docs/SPEC_INDEX.md` 11. sor | `8e8d5b0` |
| P3-01 | M04 lineage séma: javaslatok, csak emberi validálás, levezetett függetlenségi csoportok, cutoff-jogosultság | `dd3c980` |
| P3-02 | M05 eseményséma: változtathatatlan, hash-hez kötött verziók; AI CREATE → CANDIDATE, UPDATE → új, review-ra váró verzió; MERGE/SPLIT/SUPERSEDE/REJECT csak ember | `dc4d1db` |
| P3-03 | `M04_LINEAGE/1.0.0`, `M05_EVENT_BUILDER/1.0.0` prompt bundle-ök + JSON sémák; determinisztikus input-építők | `a927750` |
| P3-04 | Orkesztráció (max. 1 külön repair-futás), `ANALYSE_LINEAGE` / `BUILD_EVENTS` jobok, worker; 2100-as migráció | `a927750` |
| P3-05 | Elfogadási korpusz + §16 metrikák, GS-izolációs teszt; 2200-as migráció | `5100ed6` |
| P3-06 | Dokumentáció, DEV smoke Phase 3 ellenőrzések, CI, első CG3-jelentés | `2f0b50b`, `6092849` |
| CG3-C | Célzott javító kör: 2300 as-of kontextus (CG3-01), 2400 végleges teljes split (CG3-02), 2500 név alapú forrás-összevonás megszüntetése (CG3-03); input-építők, tesztek, korpusz | `d3e1302` |

## FILES CHANGED

A `8ff862f..2f0b50b` tartományban 28 kód/teszt/migrációs fájl (4642 sor hozzáadva, 8 törölve) + dokumentáció. Phase 1/2 kódban csak bővítés történt: `worker.py` (két új job-handler), `config.py` (M04/M05 konfiguráció-ID), `model_settings.py` (alacsony variancia M04/M05-re), `supabase_dev_smoke.py` (P3 ellenőrzések), `tests/pipeline_support.py` (modul-paraméter, alapértelmezés változatlan). **Phase 1/2 teszt nem módosult.**

- Új: `services/ai-orchestrator/lfhe_orchestrator/event_inputs.py`, `event_pipeline.py`; `packages/prompts/M04_LINEAGE/1.0.0/*`, `M05_EVENT_BUILDER/1.0.0/*`, `prompt-lock.json` (újralockolva).
- Tesztek: `tests/integration/test_lineage.py` (18), `test_events.py` (22), `test_phase3_pipeline.py` (9), `test_asof_context.py` (6, CG3-01), `tests/acceptance/test_phase3_acceptance.py` (1, korpusz), `tests/security/test_gs_isolation.py` (4), `tests/lineage_support.py`, `tests/fixtures/phase3_acceptance/corpus.json`.
- Javító kör (`7197389..d3e1302`):
  - 3 új migráció;
  - `event_inputs.py` (as-of építés);
  - `tests/claims_support.py` (opcionális `available_at` a REPLAY-jogosult teszt-snapshotokhoz; alapértelmezés változatlan);
  - `tests/lineage_support.py`, a Phase 3 tesztek és a korpusz.
- Dokumentáció: `docs/lineage-events.md`, `docs/phase3-test-traceability.md`, `docs/cg3-acceptance-metrics.json`, `docs/permission-matrix.md`, `docs/audit-catalogue.md`, `docs/PROJECT_STATUS.md`, `docs/SPEC_INDEX.md`, `docs/specs/*`.

## DATABASE MIGRATIONS

| Migráció | Tartalom |
|---|---|
| `20261011001800_lineage.sql` | enumok (2 kapcsolattípus, 5 ajánlás); `external_origins` (bizonyítékhoz kötött), `lineage_proposals`, `corroboration_recommendations`, `lineage_ingestion_results`, `claim_lineage` (append-only, csak ember), visszavonások, döntések; `claim_cutoff_eligible`, `claim_independence_group`, `independence_summary`; `ingest_lineage` (worker); 4 HUMAN_ONLY függvény; RLS + audit |
| `20261011001900_events.sql` | enumok (7 állapot, 8 AI-javaslat, 4 szerep, 3 kapcsolat); `events`, `event_versions` (hash, deferred ellenőrzés), `event_claims`, `event_state_history`, `event_relationships`, `event_actions`, `event_proposals`, `event_version_reviews`, `event_ingestion_results`, `event_claim_redistributions`; `ingest_event_proposals` (worker); 9 HUMAN_ONLY függvény; RLS + audit |
| `20261011002000_phase3_jobs.sql` | `ANALYSE_LINEAGE`, `BUILD_EVENTS` jobtípus |
| `20261011002100_event_ai_update_carry_forward.sql` | **javítás (forward-only):** AI-frissítésnél a meglévő claimek automatikusan átkerülnek; az AI csak hozzáadhat, nem törölhet és nem írhat át szerepet |
| `20261011002200_external_origin_reuse.sql` | **javítás (forward-only):** az elfogadott külső forrás azonos normalizált néven újrahasznosul (a korpusz L3 esetében talált hibát) |

| `20261011002300_cg3_01_asof_context.sql` | **CG3-01:**
  - tudáskorlát (knowledge bound) a lineage-re, eseményverzióra, állapotsorra és szerkezeti kapcsolatra;
  - `claim_lineage_evidence` (az ember által megadott bizonyítékalap), `event_state_version_bindings` (trigger);
  - `lineage_usable`, `event_version_eligible`, `run_evidence_eligible`, `event_asof`, `claim_independence_group_asof`, `independence_summary_asof`, `article_cutoff_eligible`;
  - az M05 ingestion az as-of verziót ellenőrzi, és későbbi headre soha nem materializál |
| `20261011002400_cg3_02_full_split_terminal.sql` | **CG3-02:**
  - a teljes split (retained nélkül) végleges: `event_fully_split`;
  - `event_is_open` / `require_event_head` / `set_event_state` → `EVENT_NOT_OPEN`;
  - `event_heads.current_version_id` / `is_current`, és `structural_status = SPLIT_INTO` |
| `20261011002500_cg3_03_external_origin_identity.sql` | **CG3-03:**
  - nincs név alapú újrahasznosítás;
  - azonosság csak explicit emberi választással (`decide_lineage_proposal` 4. argumentum / `external_origin_id`, bizonyíték- és URL-ütközés-ellenőrzéssel), vagy azonos kanonikus URL + név alapján, egyértelmű találat esetén |

| `20261011002600_cg3_knowledge_bound_retractions.sql` | **Végső javítás (SD3-13 helyett):**
  - append-only `claim_lineage_retraction_evidence`;
  - `lineage_retraction_usable`: a visszavonás csak akkor hat, ha bizonyítékalapja a futás cutoffjára jogosult; alap nélkül REPLAY-t nem módosít;
  - `lineage_usable` ezt értékeli;
  - `retract_claim_lineage(id, reason, p_evidence_basis DEFAULT NULL)` |

Minden javítás új migráció; a már commitolt migrációkat nem írtam át (D-01: fix-forward). Összesen 27 migráció. A 2200-as név alapú újrahasznosítást a 2500 felülírja.

## PROMPTS / SCHEMAS

| Bundle | module_version | Lock-hash (SHA-256) |
|---|---|---|
| `M04_LINEAGE/1.0.0` | `MPP-1.2.2+P3-ADDENDUM-1.0` | `9a0dfa7575369f1527315084745f9eda81810b116a8f4ecb70703e021cfe35e2` |
| `M05_EVENT_BUILDER/1.0.0` | `MPP-1.2.2+P3-ADDENDUM-1.0` | `1d1e9595be3271fdecb2d5756bdbb2e6c836fca41da4117976f1759514004426` |

- A sémák enumjai tesztelten megegyeznek a DB-szótárakkal (`lineage_relationship_type`, `corroboration_recommendation`, `claim_status`, `event_proposal_type`, `claim_type`, `event_claim_role`).
- `additionalProperties: false`: az M04 kimenet nem tud függetlenséget állítani (nincs ilyen mező; a próbálkozás SCHEMA_VALIDATION_FAILED, tesztelve).
- A forrásszöveg a system prompt szerint megbízhatatlan adat; prompt-injection teszt: a system prompt változatlan, egyetlen envelope-blokk.
- Regisztráció és aktiválás csak a meglévő auditált úton (registrar + ember `PROMPT_ACTIVATE`). Alacsony varianciájú modellbeállítás kötelező mindkét modulra.

## M04 LINEAGE MODEL

- Kapcsolattípus csak `COMMON_ORIGINAL_SOURCE` vagy `DERIVED_REPORTING`.
- Szülő: pontosan egy claim, cikk vagy külső forrás.
- Külső forrás csak akkor jöhet létre, ha a neve szerepel a claim eredeti nyelvű bizonyíték-szakaszában, az URL-je pedig a forrásszövegben.
- Két külső forrás azonossága soha nem következik csak a névből (CG3-03). Azonosságot csak ez állapít meg:
  - explicit emberi választás, ahol a választott forrás nevének bizonyítva kell lennie a gyerek-claimben, és az URL-ek nem ütközhetnek; vagy
  - azonos kanonikus URL + név, pontosan egy meglévő forrással.

  Minden más esetben külön forrás jön létre.
- As-of használat (CG3-01): egy validált lineage-sor csak akkor kerülhet egy futásba, ha a teljes tudáskorlátja cutoff-jogosult. A tudáskorlát:
  - a végpontok és a forrás bizonyíték-claimje;
  - elfogadott javaslatnál a javasló M04-futás teljes inputja és kontextusa;
  - emberi rögzítésnél a megadott `evidence_basis`.

  Megadott alap nélkül REPLAY-ben soha nem használható.
- Ingestion: bármely hibás hivatkozás (nem input claim, nem cutoff-jogosult, önhivatkozás, ismeretlen típus, bizonyítatlan forrás) **az egész kimenetet** elutasítja.
- A kimenetből csak javaslat lesz (`human_review_required = true`). Lineage-et csak `CLAIM_REVIEW` jogú ember validálhat, rögzíthet vagy vonhat vissza; a visszavonás nem töröl.

## INDEPENDENCE-GROUP RESULTS

- A csoportok **levezetettek**: összefüggő komponensek kizárólag emberileg validált lineage-élek mentén. Nincs szerkeszthető csoport-tábla.
- Kiadó, nyelv, megfogalmazás vagy domain **soha** nem választ szét csoportot. A validált lineage csak összevonhat.
- `independence_summary`: `distinct_groups_upper_bound` (felső korlát), `claims_with_unknown_lineage`, és mindig `independence_established: false`.
- Az M04/M05 a csoportot as-of számolja (`claim_independence_group_asof` / `independence_summary_asof`): csak a futás módjára és cutoffjára használható lineage-élek mentén.

Korpusz (valós pipeline, szkriptelt modell):

| Eset | Claimek | Csoport validálás előtt → után | Igazság |
|---|---|---|---|
| L1 újraközlés 4 kiadónál, 3 nyelven | 4 | 4 → **1** | 1 |
| L2 újraközlés, naiv modell (lineage-et nem lát, korroborációt javasol) | 3 | 3 → 3 (mind ismeretlen lineage; státusz változatlan) | 1 |
| L3 közös külső forrás, 2 nyelv — az azonosságot az ember explicit választással állapítja meg | 2 | 2 → **1** | 1 |
| L4 csak felszíni különbségek | 3 | 3 → 3 (mind ismeretlen; függetlenség nem állapítható meg) | ismeretlen |
| L5 high impact | 1 | 1 → 1 | 1 |
| L6 azonos nevű, különböző forrás (eltérő URL) | 2 | 2 → **2** (nincs hamis függőség) | 2 |
| R1 REPLAY: későbbi bizonyítékból megállapított lineage | 2 | REPLAY-ben 2 (a későbbi lineage nem használható) | 2 a cutoffkor |

`republication_inflation = 0`, `surface_difference_independence = 0`, `independence_established_true = 0`, `false_dependence_collapse = 0`, `replay_context_leakage = 0`.

Az L2 sor helyes olvasata: a 3 felső korlát, nem 3 megerősítés. Mindhárom claim „ismeretlen lineage” jelzést kap, ezért semmi sem számít független megerősítésnek, amíg ember nem dönt (L-22).

## CLAIM-STATUS WORKFLOW RESULTS

- Az M04 csak ajánl. A `claim_status_auto_rules` tábla üres marad; a DEV smoke ezt ellenőrzi.
- `decide_corroboration_recommendation`:
  - csak ember hívhatja, `CLAIM_REVIEW` joggal;
  - a várt aktuális státuszhoz kötött (`STATUS_STALE`);
  - `HUMAN_DECISION` státusztörténet-sort ír, amely megnevezi az ajánló model_runt;
  - auditbejegyzés: `CLAIM_STATUS_CHANGED` (HUMAN) és `CORROBORATION_RECOMMENDATION_DECIDED`.
- Korpusz: `silent_status_finalisation = 0`; a worker döntési kísérlete minden ajánlásnál `InsufficientPrivilege`.

## HIGH-IMPACT REVIEW RESULTS

- A high impact claim státusza csak emberi döntéssel változhat. A Phase 2 `HIGH_IMPACT_REQUIRES_HUMAN` őr megmaradt, és az automatikus út egy szintetikus szabállyal is el van utasítva (teszt).
- Az ajánlás rögzíti a `high_impact_at_recommendation` értéket, és mindig `human_review_required`.
- Korpusz L5: a státusz a modellfutás után változatlan, majd emberi megerősítéssel lesz `PARTIALLY_CORROBORATED`. `high_impact_changes_without_human = 0`.

## M05 EVENT MODEL

- Szótárak:
  - AI-javaslat: 8 érték;
  - emberi EVENT_ACTION: 7 érték;
  - eseményállapot: 7 érték;
  - eseménytípus = a `claim_type` szótár (PO-döntés).
- `CREATE_NEW_EVENT`: AI-esemény, 1. verzió, állapot `CANDIDATE`. Worker csak ezt az egy kezdőállapotot írhatja (CHECK).
- `UPDATE_EXISTING_EVENT`: az **aktuális head** új AI-verziója, emberi review-ra vár. A meglévő claimek szerepükkel együtt átkerülnek; claim csak hozzáadható.
- Minden más javaslat csak `event_proposals` sor lesz, strukturális hatás nélkül.
- Ingestion-elutasítások (az egész kimenet elutasul):
  - a claim nem input és nem cutoff-jogosult;
  - a hivatkozott eseményt nem kapta meg a modell kontextusként az aktuális head-del;
  - a cél nem head, vagy nem nyitott;
  - meglévő claim szerepe átíródna;
  - a dátum vagy a hely nem a claimekből származik (a publikálás dátuma nem eseménydátum);
  - a típus vagy a szerep szótáron kívüli;
  - egy claim két materializáló javaslatban szerepel;
  - ugyanazt az eseményt egy kimenet kétszer frissítené.
- Kontextus (CG3-01): legfeljebb 20 olyan eseményjelölt, amely **a cutoffkor nyitott**, és **as-of verziója** egyezik típusban, helyben vagy normalizált entitásban (`lfhe.event_asof`).
  - A cím, leírás, dátum, hely, tagság, állapot és szerkezeti kimenet mind az as-of reprezentációból jön.
  - Későbbi verzió soha nem szivárog vissza. Bizonyítható as-of verzió nélkül az esemény nem kerül a kontextusba.
- Az ingestion csak azt az as-of verziót fogadja el, amelyet a modell kapott (`EVENT_NOT_IN_MODEL_RUN_CONTEXT_OR_STALE`).
- UPDATE csak akkor materializálódik, ha a modellnek mutatott verzió az aktuális head (`UPDATE_TARGET_VERSION_NOT_SUPPLIED`).
- Az eseményverzió tudáskorlátja: a tag-claimek, az összes előző verzió, AI-verziónál a futás inputja és kontextusa, valamint az elfogyasztott verziók (merge-források, split-szülő).
- Az állapotsor ahhoz a headhez kötött, amely a beíráskor aktuális volt. A szerkezeti kapcsolat csak akkor érvényes, ha mindkét verziója jogosult.

## EVENT VERSIONING RESULTS

- `event_versions` és `event_claims`: változtathatatlan (`block_mutation`).
- `content_hash` = SHA-256 a kanonikus `lfhe-event-version/1` JSON-ról (mezők, rendezett helyek, rendezett claim–szerep tagság, előző verzió).
- Deferred trigger ellenőrzi commitkor: legalább 1 claim, hash-egyezés (`EVENT_VERSION_HASH_MISMATCH`), érvényes láncolat.
- A régi verzió változatlan marad, és hash-e újra ellenőrizhető. Lényegi változás = új hash.
- A tagság minden verzióra visszaállítható. A review `(version_id, content_hash)`-hez kötött.
- Tesztek: 11, 12, 24, 25, 26 PASS. Korpusz `ancestry_breaks = 0`.

## EVENT CLUSTERING RESULTS

**Determinisztikus garanciák (tesztelve):**
- AI nem tud egyesíteni;
- ország, rendszer vagy hét egyezése önmagában semmit nem kényszerít ki;
- az AI-frissítés validálatlan marad, amíg ember nem dönt;
- korlátozott, cutoff-szűrt kontextus.

**Korpusz (szkriptelt kimenetek, köztük szándékosan túlbuzgó):**
- E1 — három gyengén kapcsolódó claim (azonos ország és hét): 3 külön CANDIDATE.
- E2 — a modell egy gyengén kapcsolódó claimet csatol egy meglévő eseményhez:
  - a verzió `head_pending_review`, az esemény `CANDIDATE` marad;
  - az ember REJECT-tel bírálja, majd `update_event`-tel kiveszi a claimet;
  - `removed_claim_ids` rögzítve, tehát nem csendes.
- E3 — régi esemény új tudósítással: frissítés, nem hamis új esemény (`old_event_new_reporting_updated = true`).
- E4 — SUGGEST_MERGE/SPLIT/SUPERSEDE + KEEP_SEPARATE: nincs strukturális hatás.

Metrikák: `over_merge_in_validated_events = 0`, `unvalidated_ai_grouping_promoted = 0`; `ai_over_eager_versions_held_for_review = 1` (az E2 eset, szándékosan).

**Korlát (őszintén):** a valódi modell klaszterezési minőségét Phase 3-ban nem mértem. Ez modelltulajdonság, és a valódi provider-futás nem blokkoló (L-09, L-20). A fenti eredmény azt bizonyítja, hogy egy rosszul klaszterező modell sem tud validált túlösszevonást létrehozni.

## MERGE / SPLIT / SUPERSEDE LINEAGE RESULTS

- **MERGE:**
  - a cél új verziót kap a claimek uniójával (CONTRADICTS soha nem gyengül);
  - a forrás megtartja ID-ját és összes verzióját, kap egy `MERGED_INTO` kapcsolatot (verzió+hash kötéssel), és többé nem nyitott;
  - `resolve_event(régi)` → a célra mutat;
  - újraelosztás rögzítve.
- **SPLIT:**
  - minden claim a megtartott verzióba vagy egy gyerekbe kerül (`SPLIT_WOULD_DROP_CLAIMS`);
  - idegen claim nem kerülhet be (`SPLIT_INTRODUCES_FOREIGN_CLAIMS`);
  - `SPLIT_INTO` kapcsolat jön létre, és a szülő története ép marad.
  - **retained esetén** a szülő a megtartott verzióval nyitott marad, és csak a megtartott claimekkel aktuális (teszt).
  - **teljes split esetén (CG3-02)**:
    - a szülő ID-ja, verziói és `SPLIT_INTO` kapcsolatai megmaradnak;
    - a szülő végleges: nem M05-jelölt, `update_event` / `set_event_state` / újabb split → `EVENT_NOT_OPEN`;
    - `event_heads`: `is_current = false`, `current_version_id = NULL`, `structural_status = SPLIT_INTO`;
    - claim nem vész el, és a régi tagság nem jelenik meg aktuálisként.
  - A `resolve_event(szülő)` kapcsolat alapú marad.
- **SUPERSEDE:** a régi esemény verziói megmaradnak, `SUPERSEDED_BY` kapcsolatot kap, `resolve_event` követi a láncot.
- **REJECT:** csak állapotváltozás; a verziók és a történet megmaradnak.
- Korpusz-lánc (merge → split → supersede):
  - `claims_lost_in_structural_ops = 0`, `ancestry_breaks = 0`;
  - a régi verziók hash-e változatlan;
  - a cáfoló claim CONTRADICTS marad az összevont és a felváltó eseményben is.

## HUMAN REVIEW / RBAC NEGATIVE TEST RESULTS

- Engedélyek:
  - lineage, függetlenség és claim-státusz: `CLAIM_REVIEW`;
  - esemény: `EVENT_ACTION` (mindkettő ANALYST);
  - új engedélyt nem vezettem be.
- Mind a 13 új HUMAN_ONLY függvény (4 lineage + 9 esemény) le van zárva a nem emberi szerepek elől:
  - `test_human_only_functions_are_closed_to_non_human_roles` ellenőrzi, hogy anon, service_role, lfhe_worker, lfhe_evaluator és lfhe_registrar nem futtathatja őket;
  - a VIEWER és az ADMIN a `require_human_permission` miatt bukik el.
- Explicit negatív teszt öt szereplővel (**worker, service_role, anon, VIEWER, ADMIN** → `InsufficientPrivilege`): `decide_lineage_proposal`, `record_claim_lineage`, `decide_corroboration_recommendation`, `merge_events`, `split_event`, `supersede_event`, `reject_event`. A worker `set_event_state`-je külön tesztelve.
- Ember nem hívhatja a worker ingestion-függvényeket.
- `tests/security/test_security_definer_hardening.py`: minden SECURITY DEFINER rögzített `search_path`-szal fut, a HUMAN_ONLY függvények csak `authenticated` számára futtathatók. Lokálisan 110 definer, 0 rögzítetlen; 29 HUMAN_ONLY függvény.
- A javító kör új definer-függvényei (as-of ellenőrzések) csak a `lfhe_worker` számára futtathatók. A `decide_lineage_proposal` 4 argumentumos alakja HUMAN_ONLY, csak `authenticated`.
- DEV smoke P3 ellenőrzések (a PO futtatja):
  - táblák + RLS;
  - üres auto-szabálytábla;
  - rögzített `search_path`;
  - események RLS-e;
  - viewer és ADMIN nem tud MERGE-t és lineage-validálást;
  - service_role nem tud MERGE-t;
  - ember nem tud ingestiont hívni.

## FAIL-CLOSED RESULTS

- Sémahibás kimenet: `SCHEMA_VALIDATION_FAILED`, pontosan 1 külön repair-futás azonos input snapshot-hash-sel, utána semmilyen állapot (sem esemény, sem javaslat).
- Provider-hiba: `PROVIDER_ERROR`, nincs állapot; a job `max_attempts`-on belül újrapróbál.
- Hiányzó modellkonfiguráció: a job FAILED (nem csendes kihagyás).
- Hivatkozási, cutoff- vagy elavult head-hiba: az egész kimenet `OUTPUT_REJECTED`, az okok rögzítve.
- Nem SUCCEEDED futás: csak a kimenetel rögzül.
- Elavult emberi nézet: `EVENT_HEAD_STALE` / `STATUS_STALE`.
- As-of (CG3-01):
  - bizonyítható tudáskorlát nélküli objektum nem kerül REPLAY-kontextusba (emberi lineage `evidence_basis` nélkül; kötés nélküli állapotsor);
  - ismeretlen típusú bizonyíték egy futás manifestjében → nem jogosult;
  - REPLAY-futás nem írhat későbbi tudást tartalmazó headre.
- Teljes split után a szülőn minden frissítő művelet `EVENT_NOT_OPEN`.
- Azonossági bizonytalanság → külön forrás, nem összevonás (CG3-03). Nem bizonyított vagy ütköző explicit választás → `EXTERNAL_ORIGIN_INVALID` / `EXTERNAL_ORIGIN_IDENTITY_CONFLICT`.

## REPRODUCIBILITY / MODEL_RUN RESULTS

- Minden futás tárolja:
  - prompt verziót, semvert és hash-t, module_version-t;
  - modellkonfigurációt + hash-t, providert, modellt;
  - input manifestet + set-hash-t, context manifestet + set-hash-t, envelope-hash-t;
  - `task_parameters`-t (`report_mode`, `information_cutoff` kötelező — `CUTOFF_NOT_DECLARED`);
  - nyers kimenetet vagy hibaállapotot.
- A repair külön model_run. `verify_envelope` = [] (teszt).
- Azonos DB-állapot és cutoff mellett azonos envelope-hash (teszt).
- Korpusz: 11 futás, `model_runs_incomplete_provenance = 0`.

## TESTS ACTUALLY RUN

- Teljes Python-csomag lokálisan (PostgreSQL 16 + Supabase-shim, Python 3.13 locked venv, `-W error::DeprecationWarning`): **432 teszt**.
  - Phase 3: 63 (lineage 18, events 22, pipeline 9, as-of 9, acceptance 1, GS 4);
  - Phase 1+2: 369.
- `apps/web`: 21 teszt.
- `scripts/prompt_registry.py check-lock`, `scripts/secret_scan.py`, gitleaks git-mód a teljes előzményen (lokálisan és CI-ban).
- GitHub CI: run 39274247863 (`d3e1302`), run 39275062633 (`4ad7b02`), és a végső kódcommit `128f1a7` futása (lásd TEST RESULTS).
- Elfogadási korpusz metrikái: `docs/cg3-acceptance-metrics.json`.
- Nem futott:
  - DEV migráció és smoke (a PO javító döntése szerint egyelőre tilos);
  - valódi provider (L-09).

## TEST RESULTS

| Csomag | Eredmény |
|---|---|
| Python (lokális) | **432 passed**, 0 failed |
| Web | **21 passed** |
| CI run 39274247863 (`d3e1302`) | secret-scan ✔, python-tests ✔, web ✔ |
| CI a végső kódcommiton (`128f1a7`) | run 39279160435: secret-scan ✔, python-tests ✔, web ✔ |
| PROMPT-LOCK / SECRET-SCAN / gitleaks | ok / clean / no leaks |
| §15 kötelező tesztek 1–31 | mind PASS |
| CG3-01 (7 kötelező viselkedés), CG3-02 (5), CG3-03 (5), végső javítás A–E | mind PASS |

Leképezés: `docs/phase3-test-traceability.md`.

## PHASE 3 ACCEPTANCE CRITERIA — individually PASS/FAIL

| # | Kritérium (§16) | Eredmény | Bizonyíték |
|---|---|---|---|
| 1 | Az újraközlés soha nem növeli a független megerősítést a korpuszban | **PASS** | `republication_inflation = 0`, `independence_established_true = 0` (L1–L3), `false_dependence_collapse = 0` (L6), `replay_context_leakage = 0` (R1) |
| 2 | Kiadó / nyelv / megfogalmazás különbsége önmagában soha nem állapít meg függetlenséget | **PASS** | `surface_difference_independence = 0` (L4), tesztek 2, 5 |
| 3 | Az M04 nem véglegesíthet csendben claim-státuszt | **PASS** | `silent_status_finalisation = 0`, teszt 6, 9 |
| 4 | High-impact státuszváltozáshoz emberi megerősítés kell | **PASS** | `high_impact_changes_without_human = 0`, teszt 8 |
| 5 | AI nem végezhet MERGE/SPLIT/SUPERSEDE-et | **PASS** | `ai_structural_actions = 0`, tesztek 17–19 |
| 6 | A csak emberi strukturális műveletek RBAC-védettek | **PASS** | tesztek 20–23 (worker, service_role, anon, VIEWER, ADMIN elutasítva), definer-hardening az összes HUMAN_ONLY függvényre |
| 7 | Az eseményverziók változtathatatlanok és hash-nyomonkövethetők | **PASS** | tesztek 11, 12, 24, 25, 26 |
| 8 | Merge/split/supersede megőrzi az eseményfelmenőket és a történeti ID-kat | **PASS** | `ancestry_breaks = 0`, tesztek 20–22 |
| 9 | Strukturális művelettől egy claim sem tűnik el csendben | **PASS** | `claims_lost_in_structural_ops = 0`, SPLIT-őrök, 2100-as migráció; teljes splitnél a régi tagság nem aktuális (CG3-02) |
| 10 | A konzervatív klaszterezés nem vonja össze a gyengén kapcsolódó claimeket | **PASS** (determinisztikus őrökre és szkriptelt kimenetekre) | `over_merge_in_validated_events = 0`, `unvalidated_ai_grouping_promoted = 0`; korlát: valódi modell nem mérve (L-20) |
| 11 | Minden Phase 3 teszt átmegy | **PASS** | 63/63 |
| 12 | Phase 1 és Phase 2 regresszió PASS | **PASS** | 369/369 + web 21/21, CI zöld |
| 13 | A model-run provenance teljes | **PASS** | `model_runs_incomplete_provenance = 0`, teszt 29 |
| 14 | GS answer-key szivárgás = 0 | **PASS** | `gs_leakage = 0` (minden envelope és renderelt üzenet), `test_gs_isolation.py` 4/4 |

## REGRESSION STATUS

- Phase 1 + 2: **369/369 PASS**, web 21/21, CI zöld.
- Phase 1/2 tesztet, migrációt vagy viselkedést nem módosítottam; csak bővítés történt (FILES CHANGED).
- A Phase 2 `HIGH_IMPACT_REQUIRES_HUMAN` őr és az SD-11 minta változatlan.

## KNOWN FAILURES

Nincs ismert hibás teszt.

A PO által talált, a javító körben javított hibák (mind teszttel lefedve):
- **CG3-01:** az M04/M05 kontextus az aktuális lineage-et, függetlenségi csoportot és event headet használta, így egy REPLAY később megállapított tudást kaphatott. Javítás: 2300-as migráció + as-of input-építők.
- **CG3-02:** a teljes split után a szülő nyitva maradt, a régi teljes claim-halmazzal. Javítás: 2400-as migráció.
- **CG3-03:** a 2200-as migráció csak név alapján vonta össze a külső forrásokat. Javítás: 2500-as migráció.

Javított hibák az eredeti fejlesztés közben:
1. Az első eseményséma minden valós AI-frissítést elutasított volna, mert az összes meglévő claim újrafelsorolását kérte, a cutoff miatt visszatartott claimeket is. Javítás: 2100-as migráció, és a prompt szövege is ehhez igazítva.
2. Azonos nevű külső forrás két külön rekordot kapott, ezért 2 csoport maradt 1 helyett az L3-ban. Az akkori javítás (2200, név alapú összevonás) maga is hibás volt (CG3-03); a 2500 felváltotta, az L3 most explicit emberi választással ad 1 csoportot.

## SECURITY NOTES

- OSINT-only: a korpusz és minden fixture kitalált („Northland”), nincs minősített vagy belső adat.
- Nincs titok a repóban: gitleaks a CI-ban a teljes git-előzményen tiszta.
  - A lokális `dir`-módú gitleaks 6 találata kizárólag az `apps/web/.next/` build-kimenetben van (gitignore-olt, automatikusan generált Next.js preview-kulcsok, nincs commitolva).
- Provider-kulcs csak a titokkezelt környezetből jöhet. Modellbeállítás csak engedélyezőlistáról.
- Minden új SECURITY DEFINER függvényen rögzített `search_path = pg_catalog, pg_temp` van.
  - A belső írófüggvényeknek nincs grantja.
  - A levezetett olvasófüggvények (`claim_cutoff_eligible`, `claim_independence_group`, `independence_summary`) invoker jogú, így az RLS érvényesül.
- `external_origins.url`: kanonikus, hitelesítőadat-mentes URL-t kényszerít (CG1-08 szabályok).
- A forrásszöveg megbízhatatlan adat; prompt-injection teszt PASS.

## ANALYTICAL-INTEGRITY NOTES

- „Unknown stays unknown”: a függetlenség soha nem következtetett. A csoportszám felső korlát, az ismeretlen lineage külön számolva (L-22).
- A publikálás dátuma nem eseménydátum: dátum és hely csak claimekből jöhet.
- Az ellentmondás megmarad: a CONTRADICTS szerep merge és supersede során sem gyengül.
- Cutoff-fegyelem: LIVE = lekérve ≤ cutoff ÉS (elérhetőség ismeretlen VAGY ≤ cutoff); REPLAY = ismert elérhetőség ≤ cutoff. Az eseményidő soha nem jogosultsági feltétel.
- As-of tudás (CG3-01): származtatott, hiteles objektum csak a tudáskorlátja alapján kerülhet futásba. A korlátot változtathatatlan, tárolt bizonyítékból számolom, reprodukálhatóan.
  - A feldolgozás vagy emberi döntés a cutoff után is megengedett, ha a bizonyíték maga jogosult.
  - A `created_at ≤ cutoff` soha nem egyedüli szabály.
  - A lineage-visszavonás maga is tudáskorlátos: csak akkor hat egy történeti futásra, ha az alátámasztó bizonyítéka jogosult az adott cutoffra. Egy később tudott visszavonás így nem teremt hamis történeti függetlenséget (`retraction_hindsight_leakage = 0`).
- Az AI-frissítés csak bővíthet. Claimet csak ember vehet ki, és az `removed_claim_ids`-ként rögzül.
- Külső forrás azonossága nem következtethető névből (CG3-03). Bizonytalan azonosság esetén a különbség megmarad, és az ember explicit választással állapíthatja meg a közös forrást.
- `final_analytic_confidence`: nincs `confidence` nevű oszlop (DC-01 / guardrail 4). A javaslatoknál `proposal_confidence` szerepel.

## SPECIFICATION DEVIATIONS

| ID | Eltérés / értelmezés | Indoklás |
|---|---|---|
| SD3-01 | A függetlenségi csoport függvény/nézet, nem szerkeszthető `independence_groups` tábla (a CG0 táblát említett) | A baseline szerint a függetlenség nem következtethető. A validált lineage-ből levezetve nincs külön módosítható másolat, ami elcsúszhatna. A „függetlenségi csoport validálás/javítás” = lineage validálás/visszavonás (`CLAIM_REVIEW`) |
| SD3-02 | Az M04 a v1.2-es Prompt Packnél kevesebb mezőt ad (nincs `independence_group_candidate` / `independent_confirmation`) | Az addendum 2 kapcsolattípusra szűkít, és tiltja az inferált függetlenséget |
| SD3-03 | Nincs új jogosultság; lineage/státusz = `CLAIM_REVIEW`, esemény = `EVENT_ACTION` | Meglévő ANALYST-jogok, a permission matrix szerint |
| SD3-04 | Emberi `create_event` alapállapota ACTIVE; a split-gyerek CANDIDATE vagy ACTIVE | Emberi létrehozás nem AI-jelölt; a REJECTED nem kezdőállapot |
| SD3-05 | Az összevont forrásesemény megtartja életciklus-állapotát; `structural_status = MERGED_INTO`, és nem nyitott | Állapot és szerkezet külön; a történet nem íródik át |
| SD3-06 | Az M05 kimenet több javaslatot tartalmazhat egy futásban | Több új claim több eseményt érinthet; ütközésőrök (egy claim egy materializáló javaslatban, egy esemény egy frissítésben) |
| SD3-07 | A Phase 3 jobokat explicit enqueue indítja, nincs automatikus láncolás | SD-11 analógia (Phase 2/DEV döntés); a PO SD-11 pontosítása szerint később automatizálható |
| SD3-08 | LIVE módban az ismeretlen elérhetőségű claim jogosult, ha a lekérés ≤ cutoff | LIVE-ban a lekérési idő a bizonyított legkésőbbi elérhetőség; REPLAY ismert elérhetőséget követel |
| SD3-09 | AI-frissítésnél a meglévő claimek automatikusan átkerülnek (2100) | A modell a cutoff miatt nem látja az összes claimet; így „nem tűnhet el csendben claim” teljesül |
| SD3-10 | A PO a „docs/specs/SPEC_INDEX” helyet írta; a tényleges index a `docs/SPEC_INDEX.md` | A meglévő struktúra; ott kapta meg a 11. sort |
| SD3-11 | Nincs Phase 3 UI | A Phase 3 baseline nem írja elő; a döntések HUMAN_ONLY RPC-n keresztül mennek (L-21) |
| SD3-12 — **APPROVED** | Az emberi eseményverzió és állapotváltás tudáskorlátja a bizonyítékhalmaza (tag-claimek + elfogyasztott verziók). A szabad szöveges mezőket (cím, leírás) az elemző e bizonyíték összefoglalójaként rögzíti; gépileg nem bizonyítható, hogy nincs bennük későbbi tudás (L-25) | A tudáskorlát reprodukálható és tárolt adatból számolható. Ennél erősebb bizonyítást csak egy elemzői nyilatkozat vagy a szöveg tiltása adna, ezek már új hatókört jelentenének |
| SD3-13 — **NOT APPROVED → REPLACED** | Eredetileg: a visszavont lineage feltétel nélkül használhatatlan. Helyette: „Lineage retractions are themselves knowledge-bound. A retraction affects a historical run only when its supporting evidence is eligible for that run's cutoff.” | A PO döntése; 2600-as migráció, tesztek A–E |

SD3-01…SD3-12: **APPROVED** (PO, 2026-10-19). SD3-13: a jóváhagyott szemantikával felváltva. Nyitott eltérés nincs; további PO-tervezési döntést nem kérek.

## CHANGE REQUESTS

Nincs. Magasabb rendű specifikációval ütköző anyagi konfliktust nem találtam; implementációt nem kellett leállítani.

## OPEN ITEMS

| ID | Tétel | Blokkoló? |
|---|---|---|
| OI3-01 | DEV Supabase: az 1800–2600 migráció alkalmazása + smoke (27 migráció; a 22 meglévő smoke-ellenőrzés mellé 10 új P3 ellenőrzés, service_role kulccsal 11). Pontos PowerShell-parancsok: `docs/cg3-corrective-report.md` → DEV MIGRATION + SMOKE | A PO futtatja |
| OI3-02 | Valódi provider-futás M04/M05-tel, a klaszterezési minőség mérése (L-09, L-20) | Nem (baseline §13) |
| OI3-03 | Phase 3 review UI (L-21) | Nem |
| OI3-04 | Korábbról: L-09, L-18, Phase 3+ high-impact szabályok (CG2 nem blokkoló tételek) | Nem |

## RECOMMENDED NEXT ACTION

1. A PO futtassa a DEV-migrációt (1800–2600) és a smoke-ot (OI3-01), és küldje el a kimenetet.
2. A PO döntsön a CG3-ról.
3. A Phase 4 csak explicit PO-jóváhagyás után indulhat, a Phase 4 baseline `docs/specs/` alá verziózva (SD-12).

**STOP.** Phase 4-et nem kezdtem el.

## FINAL DOCUMENTATION COMMIT

Az első jelentés: `6092849`. A javító kör jelentése: `2b40878` / `4ad7b02`. A végső jelentés: `8b7e6ed` (kód és migrációk azonosak a CI-tesztelt `128f1a7`-tel). Ezt a sort a következő commit rögzíti.
