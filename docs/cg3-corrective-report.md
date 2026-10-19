# LFHÉ — TARGETED CG3 CORRECTIVE REPORT (CG3-01, CG3-02, CG3-03)

**Dátum:** 2026-10-19 · **Alap:**
- PO-döntés „CONTROL GATE 3 — TARGETED CORRECTIVE PASS” (`docs/specs/PO_Decision_2026-10-19_CG3_Targeted_Corrective_Pass.md`, SPEC_INDEX 12. sor);
- Phase 3 Authoritative Baseline Addendum v1.0.

**Hatókör:** kizárólag a három hiba. Nem végeztem új architektúra-felülvizsgálatot, a CG2-t nem nyitottam újra, a Phase 4 nem kezdődött el, és a DEV-migrációt nem futtattam. Az 1800–2200 migrációkat nem módosítottam; minden javítás új, forward-only migráció.

## SUMMARY

| Hiba | Állapot | Migráció |
|---|---|---|
| CG3-01 REPLAY / cutoff as-of kontextus-szivárgás | **RESOLVED** | `20261011002300_cg3_01_asof_context.sql` |
| CG3-02 teljes split után nyitva maradó szülő | **RESOLVED** | `20261011002400_cg3_02_full_split_terminal.sql` |
| CG3-03 külső forrás név alapú automatikus összevonása | **RESOLVED** | `20261011002500_cg3_03_external_origin_identity.sql` |

## COMMITS AND CI

| Szerep | Commit | CI |
|---|---|---|
| Kiindulópont (átadott CG3-archívum) | `7197389` | run 39267955183 ✔ |
| Javító kód + migrációk + tesztek | `d3e1302` | **run 39274247863: secret-scan ✔, python-tests ✔, web ✔** |
| Dokumentáció (ez a jelentés, frissített CG3-jelentés, metrikák, traceability, PROJECT_STATUS) | `2b40878` | lásd lent |

## CG3-01 — REPLAY / CUTOFF AS-OF CONTEXT LEAKAGE — RESOLVED

**Hiba:** a `_claims` az aktuális `claim_independence_group`-ot, a `_lineage_context` az aktuális `active_claim_lineage`-et, a `candidate_events` pedig az aktuális `event_heads`-et használta. Egy REPLAY így később megállapított tudást kaphatott.

**Javítás — tudáskorlát (knowledge bound).** Egy hiteles objektum csak akkor kerülhet egy (`report_mode`, `information_cutoff`) futásba, ha a teljes tudáskorlátja cutoff-jogosult. A korlátot változtathatatlan, tárolt bizonyítékból számolom, ezért reprodukálható. A `created_at ≤ cutoff` sehol nem egyedüli szabály.

| Objektum | Tudáskorlát | Függvény |
|---|---|---|
| validált lineage | végpontok (gyerek claim, szülő claim / cikk, a külső forrás bizonyíték-claimje)<br>+ elfogadott javaslatnál: a javasló M04-futás **teljes** inputja és kontextusa (a kontextusban lévő lineage rekurzívan)<br>+ emberi rögzítésnél: a megadott `evidence_basis` (`claim_lineage_evidence`) | `lfhe.lineage_usable` |
| függetlenségi csoport | összefüggő komponensek **csak** a használható lineage-élek mentén | `lfhe.claim_independence_group_asof`, `lfhe.independence_summary_asof` |
| eseményverzió | tag-claimek, minden előző verzió, AI-verziónál a futás inputja és kontextusa (a mutatott eseményverziók is), elfogyasztott verziók (MERGED_INTO forrás, SPLIT_INTO szülő) | `lfhe.event_version_eligible` |
| eseményállapot | a beíráskor aktuális head (`event_state_version_bindings`, trigger); kötés nélkül nem használható | `lfhe.event_asof` |
| merge / supersede / split kimenet | a kapcsolat mindkét verziója jogosult | `lfhe.event_asof` |

`lfhe.event_asof(event, mode, cutoff)` adja meg egy esemény állapotát a cutoffkor:
- a legutolsó jogosult verziót;
- a legutolsó használható állapotot;
- a használható szerkezeti kimenetet;
- az `is_open` értéket.

Ha egyetlen verzió sem bizonyítható, nem ad vissza semmit.

**Kötelező viselkedések:**

| PO-pont | Megvalósítás |
|---|---|
| A. REPLAY lineage-kontextus | Az M04/M05 csak `lineage_usable` lineage-et kap. A ma létező döntésből nem lesz automatikusan történeti tudás. Emberi lineage bizonyítékalap nélkül REPLAY-ben **soha** nem használható (fail closed); LIVE-ban csak akkor, ha a rögzítés ≤ cutoff |
| B. REPLAY függetlenségi csoport | Az M05 claim-elem `independence_group` mezője az `claim_independence_group_asof` értéke, a futás lineage-halmazából számolva |
| C. REPLAY eseménykontextus | A `candidate_events` a cutoffkor nyitott eseményeket adja, as-of verzióval. A cím, leírás, dátum, hely, tagság, állapot és merge/split/supersede kimenet mind as-of. Bizonyítható reprezentáció nélkül nincs eseménykontextus |
| D. Emberi döntések | Emberi lineage: reprodukálható korlát a megadott `evidence_basis`-ból; hiányában REPLAY → fail closed. Emberi eseményverzió vagy állapot: a bizonyítékhalmaza a korlát (SD3-12). Az ingestion csak a futásnak mutatott as-of verziót fogadja el; UPDATE csak akkor materializálódik, ha az as-of verzió az aktuális head (`UPDATE_TARGET_VERSION_NOT_SUPPLIED`), így REPLAY soha nem ír későbbi tudást tartalmazó headre |

**Regressziós tesztek** (`tests/integration/test_asof_context.py`, 6 teszt, mind PASS):

| PO-teszt | Teszt | Eredmény |
|---|---|---|
| 1–3 | `test_replay_sees_only_the_cutoff_eligible_version_never_later_fields` | REPLAY: pontosan v1 — v1 cím és hely, csak a cutoff előtti claim. A v2 cím, leírás, hely, claim és verzió-ID egyike sem szerepel az envelope-ban. LIVE: v2 |
| 4 | `test_later_state_does_not_leak_backwards_but_later_processing_on_eligible_evidence_counts` | A v2 után beírt CONFIRMED és REJECTED nem látszik vissza: REPLAY-ben ACTIVE, nyitott |
| 5 | `test_later_merge_and_supersede_do_not_alter_the_replay` | A cél as-of verziója a merge előtti; a csak később ismert forrásesemény hiányzik. A supersede REPLAY-ben nem látszik, LIVE-ban igen |
| 6 | `test_lineage_from_later_evidence_is_not_used_in_an_earlier_replay`, `test_human_recorded_lineage_needs_a_declared_evidence_bound_for_replay` | A későbbi bizonyítékot látó M04-futásból elfogadott lineage REPLAY-ben nincs a kontextusban, és a csoportot sem vonja össze (2 csoport; LIVE-ban 1). Emberi lineage: alap nélkül false, cutoff előtti alappal true, cutoff utáni alappal false |
| 7 | pozitív kontrollok mindhárom tesztben | A cutoff után, de csak jogosult bizonyítékon hozott döntés (CONFIRMED, merge, lineage) REPLAY-ben **látszik** |
| ingestion | `test_replay_ingestion_accepts_only_the_asof_version_and_never_materialises_on_a_later_head` | v1-es kontextus elfogadva; v2-es kontextus REPLAY-ben elutasítva; későbbi headre UPDATE elutasítva |

Korpusz R1 (`replay_context_leakage = 0`): REPLAY v1 és v2 között. Nincs későbbi mező, claim, állapot vagy lineage, és a független csoport 2 marad.

## CG3-02 — SPLIT PARENT REMAINS OPEN WITHOUT RETAINED EVENT — RESOLVED

**Hiba:** retained nélküli splitnél a szülő nyitva maradt a régi headdel és a teljes claim-halmazzal.

**Javítás:** `event_fully_split(e)` ⇔ létezik `SPLIT_INTO`, amely a szülő **aktuális** headjéből indul (nem követte megtartott verzió).
- **SPLIT WITH RETAINED:** a szülő a megtartott verziót kapja, nyitott marad, és csak a megtartott claimekkel aktuális.
- **FULL SPLIT:**
  - az ID, az összes verzió és a `SPLIT_INTO` kapcsolatok megmaradnak;
  - `event_is_open = false`, így a szülő nem M05-jelölt (a nem-REPLAY futásokban sem);
  - `update_event`, `set_event_state`, merge / supersede / újabb split → `EVENT_NOT_OPEN`;
  - `event_heads`: `structural_status = SPLIT_INTO`, `is_current = false`, `current_version_id = NULL`.
  - Semmit nem töröltem vagy írtam át. A `resolve_event(szülő)` kapcsolat alapú marad.
  - REPLAY-ben a teljes split csak akkor látszik, ha bizonyítható (as-of `SPLIT_INTO` az as-of verzióból).

**Tesztek** (`tests/integration/test_events.py`), mind PASS:
- `test_full_split_parent_is_no_longer_open_or_current`:
  - nem M05-jelölt, a gyerekek igen;
  - `update_event`, `set_event_state` és újabb split elutasítva;
  - a történeti verzió hash-e ép, 2 `SPLIT_INTO` kapcsolat;
  - claim nem vész el; a régi tagság nem aktuális.
- `test_split_with_retained_parent_stays_current_only_with_the_retained_claims`: `current_version_id` = a megtartott verzió, csak a megtartott claimmel. Az M05-jelölt is ezt a verziót kapja; a régi verzió ép.

## CG3-03 — EXTERNAL ORIGIN NAME-ONLY AUTO-COLLAPSE — RESOLVED

**Hiba:** a 2200-as migráció a legkorábbi azonos normalizált nevű forrást hasznosította újra, így bizonyíték nélkül függőséget következtetett.

**Javítás:** a név alapú összevonás megszűnt (`resolve_external_origin` újradefiniálva). Azonosság csak két úton állapítható meg:
- **explicit emberi választással:**
  - `decide_lineage_proposal(id, accept, reason, p_external_origin_id)` vagy `record_claim_lineage({external_origin_id})`;
  - a választott forrás nevének bizonyítva kell lennie a gyerek-claim szakaszában (`EXTERNAL_ORIGIN_INVALID`);
  - a javaslat URL-je nem ütközhet a forráséval (`EXTERNAL_ORIGIN_IDENTITY_CONFLICT`);
- **egyértelmű bizonyítékkal:** azonos kanonikus URL + azonos normalizált név, pontosan egy meglévő forrással.

Minden más esetben (csak a név egyezik, eltérő URL, nincs URL, több jelölt) új forrás jön létre, és a különbség megmarad. A korábbi `decide_lineage_proposal(uuid, boolean, text)` helyett a 4 argumentumos alak áll; a 4. argumentum alapértéke NULL, ezért a 3 argumentumos hívások (DEV smoke) továbbra is működnek.

**Tesztek** (`tests/integration/test_lineage.py`), mind PASS:

| PO-teszt | Teszt |
|---|---|
| 1 azonos név + ember által választott forrás → 1 csoport | `test_same_name_with_explicit_human_selection_is_one_group` |
| 2 azonos név + eltérő URL → külön (azonos URL + név → újrahasznosítás) | `test_same_name_different_urls_remain_distinct_same_url_is_reused` |
| 3 azonos név, nincs URL, nincs explicit választás → nincs összevonás | `test_same_name_without_explicit_reuse_does_not_collapse` |
| 4 bizonytalan azonosság → nincs hamis függőség (URL vs. nincs URL külön; nem bizonyított vagy ütköző explicit választás elutasítva) | `test_ambiguous_identity_never_creates_false_dependence` |
| 5 az L3 közös forrás explicit emberi validálással | fenti 1. teszt + korpusz L3 (explicit választás → 1 csoport) |

A korpusz új L6 esete (azonos nevű, különböző URL-ű forrás) 2 csoport marad: `false_dependence_collapse = 0`.

## FILES CHANGED (`7197389..d3e1302` + dokumentáció)

- **Migrációk:** `20261011002300_cg3_01_asof_context.sql`, `20261011002400_cg3_02_full_split_terminal.sql`, `20261011002500_cg3_03_external_origin_identity.sql`.
- **Kód:** `services/ai-orchestrator/lfhe_orchestrator/event_inputs.py` (as-of lineage-kontextus, as-of függetlenségi csoport, as-of eseményjelöltek).
- **Tesztek:**
  - `tests/integration/test_asof_context.py` (új, 6);
  - `test_events.py` (+2);
  - `test_lineage.py` (−1 régi név alapú teszt, +4);
  - `tests/acceptance/test_phase3_acceptance.py` (L3 explicit választás, `false_dependence_collapse`, R1 `replay_context_leakage`);
  - `tests/fixtures/phase3_acceptance/corpus.json` (L3, L6, R1);
  - `tests/claims_support.py` és `tests/lineage_support.py` (opcionális `available_at`; alapértelmezés változatlan).
- **Dokumentáció:** `docs/specs/PO_Decision_2026-10-19_CG3_Targeted_Corrective_Pass.md` (verbatim), `docs/SPEC_INDEX.md`, `docs/lineage-events.md`, `docs/phase3-test-traceability.md`, `docs/permission-matrix.md`, `docs/PROJECT_STATUS.md`, `docs/cg3-acceptance-metrics.json`, `docs/control-gate-3-report.md`, ez a jelentés.
- Prompt bundle nem változott, a prompt-lock változatlan.

## TESTS RUN AND RESULTS

| Ellenőrzés | Eredmény |
|---|---|
| Teljes Python-csomag (`-W error::DeprecationWarning`) | **429 passed**, 0 failed (Phase 3: 60; Phase 1+2: 369) |
| Web (`apps/web`) | **21 passed** |
| Phase 1 + Phase 2 regresszió | **369/369 PASS** |
| PROMPT-LOCK | ok |
| `scripts/secret_scan.py` | clean |
| gitleaks (git-mód, teljes előzmény) | no leaks |
| CI run 39274247863 (`d3e1302`) | secret-scan ✔, python-tests ✔, web ✔ |
| Korpusz §16 + új metrikák (`docs/cg3-acceptance-metrics.json`) | mind 0: `replay_context_leakage`, `false_dependence_collapse`, `republication_inflation`, `claims_lost_in_structural_ops`, `ancestry_breaks`, `gs_leakage`, `model_runs_incomplete_provenance` stb. |
| SECURITY DEFINER | 109 definer, 0 rögzítetlen `search_path`; 29 HUMAN_ONLY függvény, csak `authenticated` |

## NEW SPECIFICATION DEVIATIONS (PO-döntést kérek)

| ID | Tartalom |
|---|---|
| SD3-12 | Az emberi eseményverzió és állapotváltás tudáskorlátja a bizonyítékhalmaza (tag-claimek + elfogyasztott verziók). A szabad szöveges mezők (cím, leírás) az elemző összefoglalói; gépileg nem bizonyítható, hogy nincs bennük későbbi tudás (L-25) |
| SD3-13 | A visszavont lineage REPLAY-ben sem használható, akkor sem, ha a visszavonás a cutoff után történt. Ez a hibajavítás iránya; a felső korlát nőhet, de a függetlenség nem állapítható meg |

## OPEN ITEMS

- DEV-migráció (1800–2500) + smoke: a PO döntése szerint **nem futtattam**; külön utasításra.
- Új korlátok: L-25 (SD3-12), L-26 (as-of számítás olvasáskor; méréssel materializálható), L-27 (emberi lineage alap nélkül REPLAY-ben nem használható).
- Változatlanok: valódi provider (L-09, L-20), Phase 3 UI (L-21).

## RECOMMENDED NEXT ACTION

A PO döntsön a CG3-ról és az SD3-12 / SD3-13 pontokról. A DEV-migráció csak külön PO-utasításra futhat.

**STOP.** Phase 4-et nem kezdtem el.

## FINAL DOCUMENTATION COMMIT

`2b40878` — a javító jelentés, a frissített CG3-jelentés és a dokumentáció commitja (kód és migrációk azonosak a CI-tesztelt `d3e1302`-vel). Ezt a sort a következő commit rögzíti.
