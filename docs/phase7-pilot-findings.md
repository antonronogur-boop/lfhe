# LFHÉ — PHASE 7 PILOT FINDINGS & CAPABILITY ASSESSMENT (P7-08)

Állapot: **ELŐZETES — a valós pilot-bizonyíték még nincs összegyűjtve.** Ez a jelentés a módszertant, a mérőrendszert és az
eddig rendelkezésre álló (automatizált, nem pilot) bizonyítékot rögzíti. Minden empirikus szakasz kitöltése a PO
által futtatott DEV / pilot lépések eredményéből történik (`docs/runbooks/phase7-pilot.md`); hiányzó mérést nem
pótolunk becsléssel.

## METHODOLOGY

* Ciklusok: cél 6 teljes ciklus (≥ 2 REPLAY, ≥ 2 LIVE / near-live publikus OSINT, 2 tetszőleges). Egy ciklus
  akkor teljes, ha a kötött report terminális pilot-állapotban van (RELEASED, RELEASE_REJECTED,
  SECURITY_REJECTED, CONTENT_REJECTED) és `pilot_cycle_missing_metrics` üres.
* Analista-idő: kizárólag szerveróra szerinti aktív-idő szegmensek, szakaszonként (`pilot_timing_segments`).
* Összehasonlítás: ciklusonként rögzített comparator (módszer, időzített / dokumentált alapidő, összevethető
  terjedelem). Kontrollált csak időzített alapidővel, kontrollált módszerrel és összevethető terjedelemmel;
  minden más megfigyeléses (§9).
* Minőség: ciklusonként a végső QA által detektált arányok; valós hibaarány (TP / FP / FN, precision / recall,
  kritikus kihagyás) csak a P7-BM-01 benchmarkon, D és S réteg külön.
* AI-végrehajtás: modulonként a kötött model_run-ok (provider, modell, konfiguráció-hash, prompt-verzió / hash,
  latencia, tokenek, költség csak explicit árral, séma-hibák, javító futások, provider-hibák).
* Gazdasági számítás: §11 képletek, explicit költség-feltevéssel; kapacitásérték ≠ pénzbeli megtakarítás;
  pénzbeli hatás csak dokumentált bizonyítékból.
* UX: valós böngészős végigjárás, strukturált UX-megállapítások (BLOCKING / MAJOR / MINOR / ENHANCEMENT).

## PILOT POPULATION

Nincs még pilot-ciklus (0 / 6). Résztvevők, analista-szerepek és provider-beállítás a ciklusokkal együtt kerül
rögzítésre.

## LIMITATIONS (ismert, a mérés előtt)

* P7-BM-02: egyetlen érvényes valós futás (run 40213605927) — a recall és a figyelmeztetési viselkedés **nem** statisztikailag
  stabil termelési becslés; a szóródást a pilot-ciklusok során kell figyelni (PO, SPEC_INDEX 30).

* Egy személyes működés (a PO egyetlen elemzőként): a ciklusok analista-populációja kicsi; a különböző emberi
  szerepek (ANALYST / REVIEWER / SECURITY_REVIEWER / RELEASE_AUTHORITY) külön DEV-felhasználók, de ugyanaz az
  ember működtetheti őket — ez a szereptanulási és időmérési eredményeket torzíthatja.
* A comparator-alapidő sok esetben dokumentált (nem időzített) lesz → megfigyeléses eredmény, nem kontrollált.
* Elfelejtett időzítő túlszámol; utólagos javítás nincs (SD7-03) — mérési UX-megállapításként kell jelölni.
* A ciklusonkénti minőségi arány a QA által detektált érték, nem ground truth (SD7-06).
* A benchmark szintetikus, a Phase 6 elfogadási mutációkra épül; a valós hibaeloszlást nem reprezentálja.
  A nem címkézett, de jogos másodlagos detekciók FP-ként számolódnak (konzervatív precision).
* A valós provider valódiságát a rögzített provider-válaszazonosító és a futási környezet igazolja, nem
  kriptográfiai bizonyíték (SD7-08).

## METRICS / RESULTS

| Terület | Eredmény |
| --- | --- |
| Analista aktív idő, ciklusidő, áteresztés, korrekciók | **NOT YET EVIDENCED** (nincs ciklus) |
| Kapacitás-felszabadítás, FTE, kapacitásérték | **NOT YET EVIDENCED** (nincs ciklus, nincs rögzített költség-feltevés) |
| Valós provider: M07 / M08 / M09 / M10-S siker, latencia, token, költség | **MÉRVE (szintetikus lánc)** — run 40203842179: M07 26,5 s, M08 36,7 s, M09 16,3 s, M10 43,3 s; 4 / 4 sémahelyes, 0 javító futás; ~36 ezer input / ~19 ezer output token a láncra; költség: ár nincs rögzítve → ismeretlen. Előzmény: CR7-01 (`temperature`), CR7-02 (séma a kérésben) |
| M10-S empirikus minőség (P7-BM-01, valós provider) | **RÉSZBEN MÉRVE**: S recall 0,91 / 1,0 (runs 40203842179 / 40206473436); a téves riasztás a P7-BM-01 hibás alapverziója miatt érvénytelen (a jelzések nagy része a bázis valódi hibáira vonatkozik) → P7-BM-02. D: recall 1,0 |
| **M10-S empirikus minőség (P7-BM-02, PO-jóváhagyott alap, run 40213605927)** | **MÉRVE**: S recall 0,91 (10 / 11), 1 kritikus kihagyás (Q09 — kód-eltérés, a hibát CRITICAL FAIL-lel jelezte), tiszta eseteken 0 FAIL / 3 WARNING, hibán kívüli FAIL 0, konzervatív precision 0,22 (ismételt egybehangzó jelzések). D: recall 1,0, tiszta FP 0. n = 1 érvényes futás |
| P7-BM-01 a szabályalapú tesztdublőrrel (csak a mérőút regressziója) | D: 13 címke, TP 13, FN 0, FP 10 (ebből tiszta eseteken 0), precision 0,5652, recall 1,0, kritikus kihagyás 0. S (tesztdublőr): 11 címke, TP 11, FN 0, FP 2 (tiszta eseteken 0), precision 0,8462, recall 1,0. **Nem a valós M10-S minősége.** |
| Böngészős UX | **NOT YET EVIDENCED** |

## POSITIVE FINDINGS (eddig, automatizált bizonyíték)

* A teljes mérőlánc működik a meglévő rendszeren a zárt szemantika érintése nélkül (a nem-pilot táblák ujjlenyomata
  változatlan; audit-lánc ép).
* A determinisztikus M10-D a benchmark minden címkézett hibáját és minden kritikus esetét jelezte (provider-független).
* A valós-provider próba teljes folyamata (M07 → M08 → emberi jóváhagyás → M09 → M10-D + M10-S → pilot-kötés →
  §26-ellenőrzés) a valós Anthropic adapterrel, csonkolt HTTP-vel hibátlanul fut — a valós futás technikailag kész.

* A valós M10-S a PO-jóváhagyott, hibamentes alapon a beültetett hibák 10 / 11-ét a várt kóddal, a 11.-et más kóddal
  CRITICAL szinten jelezte, és tiszta anyagon nem blokkolt (P7-BM-02).

## NEGATIVE FINDINGS (eddig)

* MODEL_PERFORMANCE_LIMITATION (P7-BM-02): tiszta anyagon is ad nem blokkoló WARNING-ot (a 3 tiszta esetből 3 PASS_WITH_WARNINGS),
  és egy hibát többszörösen jelez → elemzői QA-feloldási teher; a finding-kód választása nem mindig egyezik a címkével.

* MEASUREMENT (2026-10-25, helyesbítve): a P7-BM-01 „tiszta” alapverziója valódi hibákat tartalmaz (attribúció-eltérés a claimhez képest,
  claimből nem következő állítás, `contested=false` cáfolt alapon). A valós M10-S ezeket helyesen jelezte; a benchmark téves-riasztás
  mérése ezért érvénytelen → P7-BM-02. A korábbi „túlriaszt” értelmezés visszavonva.
* ANALYTICAL / TESZT-KORLÁT: ugyanez a szintetikus anyag a Phase 4–6 elfogadási korpuszokban a determinisztikus rétegen és a
  tesztdublőrön átment; csak a valós M10-S vette észre.
* MODEL_PERFORMANCE_LIMITATION: futásonkénti szóródás — M07 egy futásban kihagyta a kötelező attribúciót (ingestion elutasította);
  M10-S recall 0,91 és 1,0 két futásban.

* CONFIGURATION_PROBLEM (2026-10-24): az első valós-provider kísérletben a provider minden kérést HTTP 400-zal utasított el; a
  preflight szerint az ok: a `claude-sonnet-5-5` a `temperature` paramétert elavultnak jelöli, a lezárt low-variance szabály
  viszont explicit `temperature ≤ 0,2`-t küld → CR7-01 (PROPOSED, `docs/cr7-01-proposal.md`).

* A D réteg a szintetikus benchmarkon sok nem címkézett másodlagos jelzést ad (10), ami az elemzői QA-feloldási
  terhet növelheti; hogy ez valós ciklusban zaj-e, a pilot mutatja meg.
* Valós provider és valós felhasználói használat nélkül a működési érték egyetlen dimenziója sem igazolt.

## UX FINDINGS / MODEL LIMITATIONS / ANALYTICAL LIMITATIONS / PROVIDER RESULTS / CAPACITY / COST

NOT YET EVIDENCED — a ciklusok és a valós-provider futás után töltendő ki.

## SECURITY OBSERVATIONS

* A pilot csak DEV / localhost környezetben, külső elérés nélkül futhat (Next.js függőség, §29).
* Provider-input csak szintetikus vagy publikus OSINT; kulcs csak a PO titoktárolóiban (DEV shell / GitHub secret).
* Benchmark-címkék csak értékelői hozzáféréssel; a worker nem olvas pilot-adatot.

## RECOMMENDED FUTURE CHANGES

Csak a pilot-bizonyíték alapján; jelenleg nincs. Egyik javaslat sem módosíthatja csendben a Phase 1–6 szemantikát.

## CAPABILITY OUTCOME (ajánlás)

**OPERATIONAL VALUE NOT YET VALIDATED** — a mérőrendszer kész, a valós pilot-bizonyíték még hiányzik.
