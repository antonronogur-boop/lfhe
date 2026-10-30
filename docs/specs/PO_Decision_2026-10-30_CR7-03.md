<!-- PO decision received 2026-10-30 08:10 (Europe/Budapest): authorisation and execution instruction for CR7-03 (option A). Stored verbatim (SD-12). -->

Az LFHÉ Phase 7 Controlled Operational Pilot előkészítését folytatjuk.

A következő munkaszakaszban legalább egy órán keresztül nem leszek elérhető. Ezért most kifejezetten AUTONÓM végrehajtást kérek: minden olyan feladatot, amelyhez nincs szükség jelszavamra, titkos kulcsra, külső account-beállításra vagy olyan PO-döntésre, amely a jelen utasításban nincs lefedve, önállóan végezz el.

A feladathoz tartozó repository teljes tartalmához, minden releváns mappához, specifikációhoz, runbookhoz, migrációhoz, teszthez és frontend/backend kódhoz hozzáférést kapsz. Ezekhez ne kérj külön engedélyt vagy megerősítést.

A cél nem egy gyors workaround, hanem egy ténylegesen használható, professzionális Phase 7 pilot rendszer kialakítása:

**profi és felhasználóbarát webalkalmazás + stabil háttér-elemző rendszer + végigjárható human-in-command workflow.**

## 1. JELEN UTASÍTÁS PO-DÖNTÉSNEK MINŐSÜL

A korábbi diagnózisod alapján a pilotot jelenleg blokkolja, hogy nincs végigjárható felhasználói út:

CLAIM  
→ EVENT  
→ RELEVANCE / EVENT BUILDING  
→ ASSESSMENT  
→ HUMAN REVIEW  
→ APPROVED ASSESSMENT  
→ REPORT CANDIDATE  
→ REPORT  
→ QA  
→ CONTENT APPROVAL  
→ SECURITY REVIEW  
→ RELEASE.

Ezért:

**CR7-03 megnyitását és végrehajtását jóváhagyom.**

A CR7-03 kizárólag a Phase 7 pilot működtetéséhez szükséges, additív operációs/UI belépési pontokat és hiányzó workflow-kapcsolatokat hozhatja létre.

NEM nyithatja újra a Phase 1–6 lezárt szemantikáját.

NEM változtathatja meg:

- a human-in-command elvet;
- a FACT / ASSUMPTION / ASSESSMENT szétválasztását;
- a likelihood és analytic confidence különválasztását;
- a provenance láncot;
- az auditálhatóságot;
- a human release authority követelményt;
- a meglévő QA szabályokat;
- a security review követelményeit;
- a release gate-ek szemantikáját;
- a lezárt Phase 1–6 adatmodellt vagy üzleti szabályokat, kivéve ha technikailag elkerülhetetlen additív kiterjesztés szükséges.

Ha meglévő HUMAN_ONLY vagy worker-függvény rendelkezésre áll, azt használd; ne implementáld újra ugyanazt a logikát a frontendben.

---

# 2. ELSŐDLEGES FELADAT — A BLOKKOLÓ WORKFLOW-RÉS MEGSZÜNTETÉSE

A jelenlegi alkalmazásban a claims és a reportok közötti operációs lánc nem járható végig.

Ezt teljesen készítsd el.

## 2.1 Event workflow

Készíts professzionális `/events` felületet.

A felület legalább tegye lehetővé:

- claim(ek)ből esemény létrehozását;
- eseménylista megtekintését;
- esemény részletes megnyitását;
- kapcsolódó claims megtekintését;
- source/evidence provenance gyors ellenőrzését;
- relevancia-döntést;
- event version kezelését;
- szükséges emberi döntések végrehajtását;
- challenge / conflict / contested állapotok egyértelmű megjelenítését;
- a meglévő megfelelő HUMAN_ONLY funkciók használatát.

Vizsgáld meg különösen a már létező funkciókat, például:

- `create_event`
- `decide_relevance`
- `promote_event_version`
- `dispose_challenge_flag`

és minden kapcsolódó Phase 3 funkciót.

Ne csak UI-vázat készíts: a műveletek valóban működjenek a DEV adatbázissal.

---

# 3. ASSESSMENT WORKFLOW

Készíts professzionális `/assessments` felületet.

A felület tegye lehetővé:

- assessmentre váró eventek megtekintését;
- assessment output megtekintését;
- evidence és claim lineage ellenőrzését;
- M07/M08 eredmények világos elkülönítését;
- assessment statementek áttekintését;
- likelihood és analytic confidence külön megjelenítését;
- assumption/fact/assessment státusz egyértelmű megkülönböztetését;
- emberi review-t;
- approve / reject / return / challenge jellegű, baseline által engedett döntéseket;
- approved assessment verzió létrejöttének ellenőrzését.

Használd a meglévő Phase 4 HUMAN_ONLY funkciókat, különösen a `review_assessment` és kapcsolódó függvényeket.

A frontend semmilyen körülmények között ne tudja megkerülni a human approvalt.

---

# 4. HIÁNYZÓ JOB-INDÍTÁSI ÚT

Korábban megállapítottad, hogy a worker feldolgozza az M05/M06/M07 jobokat, de nincs rendes operációs belépési pont ezek sorba állítására.

Ezt CR7-03 keretében oldd meg.

Készíts minimális, additív, auditált HUMAN_ONLY request/enqueue megoldást a szükséges workflow-jobokhoz.

Vizsgáld meg:

- BUILD_EVENTS
- ASSESS_RELEVANCE
- ASSESS_EVENT
- és minden olyan köztes jobot, amely nélkül a normál lánc nem járható.

Követelmények:

- ember indítsa;
- auditálva legyen;
- megfelelő role kelljen hozzá;
- service_role önmagában ne váljon human decision substitute-tá;
- idempotencia legyen kezelve;
- dupla enqueue ne okozzon állapotromlást;
- hiba esetén érthető státusz legyen;
- a frontendről látható legyen, hogy QUEUED / RUNNING / SUCCEEDED / FAILED;
- retry csak a baseline szerint megengedett módon történjen.

---

# 5. CLAIMS FELÜLET TELJESSÉ TÉTELE

A meglévő `/claims` oldalt ne hagyd jelenlegi minimális állapotában.

Tedd valóban használható analyst review felületté.

Legyen legalább:

- státusz szerinti szűrés;
- needs review nézet;
- source megjelenítés;
- publication timestamp;
- original-language evidence span;
- extracted claim;
- claim type;
- confidence / extraction metadata, ahol releváns;
- contested/challenged állapot;
- kapcsolódó event;
- approve/reject/return jellegű baseline-kompatibilis human action;
- audit trail;
- gyors navigáció a source/evidence/event között.

Ha egy művelethez nincs jogosultsága az aktuális role-nak, ne csak eltűnjön: ahol UX szempontból jobb, jelenjen meg read-only formában és legyen érthető, miért nem elérhető.

---

# 6. REPORT WORKSPACE TELJESSÉ TÉTELE

Vizsgáld át a teljes `/reports` és `/reports/<id>` workflow-t.

A pilot végigjárhatóság érdekében legyen ténylegesen használható:

- report létrehozás;
- eligible candidate pool;
- candidate refresh;
- assessment kiválasztás;
- report item összeállítás;
- M09 wording segítség;
- analyst által kontrollált inclusion/exclusion;
- section placement;
- draft;
- versions;
- canonical version;
- QA view;
- warning acknowledgement;
- content approval;
- security review;
- release decision;
- released artifact;
- PDF;
- manifest;
- manifest hash;
- provenance inspection.

A lezárt Phase 5–6 logikát ne változtasd meg.

Ha valamelyik funkció már implementálva van, ne készíts második párhuzamos implementációt; kösd össze normálisan a felhasználói felülettel.

---

# 7. PILOT WORKSPACE TELJESSÉ TÉTELE

A `/pilot` jelenleg funkcionális, de minimális.

Tedd professzionális pilot measurement workspace-szé.

Legyen egyértelműen látható:

- 6 ciklusos target;
- REPLAY / LIVE arány;
- aktuális ciklusok;
- cycle status;
- report binding;
- comparator;
- timer stage;
- analyst time;
- reviewer time;
- security time;
- release time;
- AI executions;
- provider/model;
- token usage;
- model cost;
- cost assumption;
- capacity value;
- QA D/S eredmények;
- UX findings;
- blocking findings;
- provenance;
- cycle completion readiness.

A „capacity value” továbbra se jelenjen meg cash savingként.

Ha nincs comparator, legyen egyértelműen:

`observational only / productivity claim not available`.

---

# 8. UX FINDINGS

A Phase 7 UX findings funkció legyen ténylegesen használható.

Severity:

- BLOCKING
- MAJOR
- MINOR
- ENHANCEMENT

A most feltárt probléma kerüljön megfelelően dokumentálásra:

Area:
`EVENT_ASSESSMENT`

Severity:
`BLOCKING`

Class:
`USABILITY_DEFECT`

Title:
`No UI / request path from claims to approved assessment`

A CR7-03 validálása után ennek státusza megfelelően frissíthető/resolved-ra állítható, de az eredeti finding maradjon auditálható.

---

# 9. WEBOLDAL — TELJES PROFESSZIONÁLIS UX/UI RENDBETÉTEL

A jelenlegi nyers HTML-szerű megjelenés nem elfogadható végleges pilot UI-ként.

A teljes `apps/web` felületet alakítsd át egységes, professzionális, modern elemzői alkalmazássá.

Nem marketingoldalt kérek, hanem professzionális intelligence-analysis workspace-t.

## Elvárt vizuális rendszer

Legyen:

- konzisztens application shell;
- bal oldali vagy egyértelmű felső navigáció;
- jól elkülönített fő modulok;
- egységes typography;
- értelmes spacing;
- kártyák;
- status badge-ek;
- severity badge-ek;
- role badge-ek;
- táblázatok;
- filterek;
- keresés, ahol indokolt;
- breadcrumb;
- loading state;
- empty state;
- error state;
- success state;
- confirmation state;
- form validation;
- disabled state magyarázattal;
- responsive layout;
- legalább alapvető accessibility;
- billentyűzettel használható formok;
- egyértelmű CTA hierarchia.

## Fő navigáció

Értékeld és szükség szerint alakítsd át legalább ezekre:

- Dashboard
- Sources
- Claims
- Events
- Assessments
- Reports
- Pilot

Role-tól függően jelenjen meg:

- QA
- Security / Release
- Admin jellegű funkció, ha indokolt.

---

# 10. DASHBOARD

Készíts értelmes landing/dashboard oldalt a sikeres login után.

Ne a Source registry legyen az egyetlen kezdőoldal.

A dashboard role-aware módon mutassa például:

ANALYST:

- claims awaiting review;
- events awaiting action;
- assessments awaiting review;
- active report;
- current pilot cycle;
- active timer;
- failed jobs;
- unresolved blocking UX findings.

REVIEWER:

- pending assessment/content reviews.

SECURITY_REVIEWER:

- pending security reviews.

RELEASE_AUTHORITY:

- reports ready for release decision.

PILOT_LEAD:

- cycle progress;
- incomplete measurements;
- unresolved findings;
- target 6 cycle progress.

Az adatokat valódi DB állapotból kérje le, ne statikus számokat mutasson.

---

# 11. SZEREPKÖRÖK ÉS JOGOSULTSÁGOK

A már létrehozott DEV role-ok:

- ADMIN
- VIEWER
- ANALYST
- PILOT_LEAD
- REVIEWER
- SECURITY_REVIEWER
- RELEASE_AUTHORITY

A jelenlegi pilot user mapping:

- lfhe-admin → ADMIN
- lfhe-viewer → VIEWER
- lfhe-analyst → ANALYST + PILOT_LEAD
- lfhe-reviewer → REVIEWER
- lfhe-security → SECURITY_REVIEWER
- lfhe-release → RELEASE_AUTHORITY

A UI legyen role-aware.

Ne adj plusz jogosultságot csak azért, hogy egyszerűbb legyen a frontend.

Különösen:

- ADMIN nem válhat automatikusan human analyst/reviewer/release authority szereplővé;
- service_role nem lehet emberi döntéshozó;
- VIEWER maradjon read-only.

---

# 12. WORKER ÉS BACKEND OPERÁCIÓS ÁLLAPOT

Vizsgáld át a worker teljes Phase 7 működését.

Ahol nincs szükség titkos kulcsra vagy emberi external setupra:

- javítsd;
- egészítsd ki;
- dokumentáld;
- teszteld.

Külön ellenőrizd:

M02  
M03  
M04  
M05  
M06  
M07  
M08  
M09  
M10-D  
M10-S.

A provider-abstractiont és CR7-01/CR7-02 eredményeket ne nyisd újra.

A jelenlegi elfogadott real-provider modell:

`anthropic / claude-sonnet-5-5`

provider-fixed samplinggal.

Ne változtass modellt csak azért, mert más verzió létezik.

---

# 13. REPLAY READINESS

A cél az, hogy a munka végére az első valódi REPLAY pilot ciklus technikailag elindítható legyen.

Az első ciklus tervezett konfigurációja:

Report code:
`RPT-P7-REPLAY-01`

Title:
`LFHÉ Phase 7 pilot — REPLAY cycle 1 (K-05 DEV corpus)`

Cycle label:
`P7-REPLAY-01`

Mode:
`REPLAY`

Information cutoff:
`2026-10-19 13:25` Budapest local time  
= `2026-10-19 11:25 UTC`

Reason:
`First measured Phase 7 REPLAY pilot cycle`

Pilot cycle code:
`P7C-REPLAY-01`

Data boundary:
`PUBLIC_OSINT`

Input scope:
`K-05 DEV corpus: sources K05-01,02,05,06,07,08; collection run 2026-10-19T11:24Z; REPLAY eligibility = stated public availability <= cutoff`

Comparator első ciklusban:

Method:
`NONE`

Comparable scope:
`no`

Reference:
`No timed or documented manual baseline exists; cycle 1 validates instrumentation (observational only)`

FONTOS:

**Ne indíts tényleges mért pilot ciklust csak azért, hogy teszteld a rendszert.**

A cycle `started_at` és a teljes turnaround measurement miatt ne szennyezd be az első valódi pilot ciklus bizonyítékát.

A workflow-validációhoz használj külön dev/test adatot vagy megfelelő teszt-harnesst.

A valódi `P7C-REPLAY-01` csak akkor indulhat, amikor az út már végig validált.

---

# 14. K-05 CORPUS ÉS DEV ADAT

Vizsgáld meg a meglévő K-05 DEV korpuszt.

Ne találj ki új operational evidence-et.

Állapítsd meg:

- hány article;
- hány snapshot;
- hány replay-eligible snapshot;
- hány claim;
- hány event;
- hány assessment;
- hány approved assessment;
- mennyi report-eligible material áll rendelkezésre.

Ha a meglévő cikkekből még nincs claim/event/assessment, készítsd el az operációs utat, amely a normál pipeline-on keresztül elő tudja állítani ezeket.

Ha validáláshoz synthetic fixture szükséges, az legyen egyértelműen:

`SYNTHETIC_TEST_ONLY`

és semmilyen pilot metricbe ne keveredjen.

---

# 15. AUTOMATIZÁLT E2E

Készíts valódi browser/E2E tesztet a teljes kritikus útra.

Legalább:

login  
→ claim review  
→ event  
→ assessment  
→ human assessment review  
→ approved assessment  
→ report candidate  
→ report draft  
→ QA  
→ warning acknowledgement  
→ content approval  
→ security review  
→ release decision  
→ released artifact  
→ PDF / manifest / hash.

A teszt több role-t is használjon.

A teszt ne kerülje meg közvetlen SQL-lel azokat a human actionöket, amelyeket a valódi felhasználó UI-ról végez.

Ha Playwright vagy más megfelelő browser framework még nincs a projektben, válassz minimális és fenntartható megoldást.

---

# 16. TESZTELÉS

A munkát ne tekintsd késznek pusztán azért, mert buildel.

Futtasd, ahol lehetséges:

- frontend typecheck;
- frontend tests;
- backend/unit tests;
- migration tests;
- RLS/security tests;
- role permission tests;
- worker tests;
- Phase 7 tests;
- relevant smoke tests;
- browser E2E;
- production build.

Ne módosíts tesztet azért, hogy egy valódi regresszió „zöld” legyen.

Ha egy korábban lezárt expectation változna, előbb bizonyítsd, hogy CR7-03 scope-jába tartozik.

---

# 17. ADATBÁZIS-MIGRÁCIÓ

Ha új adatbázis-függvény vagy tábla szükséges:

- új forward-only migration legyen;
- régi migrationt ne írj át;
- megfelelő RLS;
- megfelelő GRANT;
- SECURITY DEFINER esetén fixált `search_path`;
- audit event;
- actor attribution;
- idempotencia;
- megfelelő role authorization;
- anon tiltás;
- service-role bypass ne helyettesítse a humán identitást.

---

# 18. CR7-03 DOKUMENTÁCIÓ

Hozd létre a CR7-03 dokumentációt.

Legalább:

- probléma;
- hatás;
- root cause;
- scope;
- non-scope;
- változások;
- security impact;
- audit impact;
- test evidence;
- rollback considerations;
- acceptance criteria;
- PO authorization hivatkozása;
- Phase 1–6 closure preservation.

Frissítsd a megfelelő:

- SPEC_INDEX-et;
- CHANGELOG-ot;
- Phase 7 dokumentációt;
- runbookot;
- CG7 reportot;

de csak tényszerűen.

A CG7-et NE zárd le.

A verdict maradjon:

`OPERATIONAL VALUE NOT YET VALIDATED`

amíg a 6 valódi pilot ciklus nincs meg.

---

# 19. WEB SECURITY / DEV BOUNDARY

A web jelenleg csak DEV / localhost.

Ezt tartsd meg.

Ne tegyél internetre publikus deploymentet.

A Next.js dependency security issue miatt exposed deployment továbbra sem engedélyezett, amíg külön döntés nem születik.

Ne upgrade-elj dependencyt automatikusan, hacsak az nem feltétlenül szükséges ehhez a CR-hez.

Ne futtass automatikus agresszív dependency fixet (`audit fix --force` stb.).

---

# 20. NE KÉRJ TŐLEM OLYAN DOLGOT, AMIT MAGAD IS MEG TUDSZ CSINÁLNI

A következő időszakban nem leszek elérhető.

Ezért:

- ne állj meg approval kérésnél, ha a jelen utasítás már lefedi;
- ne kérdezd meg, melyik fájlt nyithatod meg;
- ne kérdezd meg, melyik mappát használhatod;
- ne kérdezd meg, futtathatsz-e tesztet;
- ne kérdezd meg, készíthetsz-e migrációt;
- ne kérdezd meg, készíthetsz-e UI-oldalt;
- ne kérdezd meg, frissítheted-e a CR7-03 dokumentációt;
- ne kérdezd meg, hogy az A megoldást választom-e.

**Az A megoldást választom.**

Ez a PO-engedély.

---

# 21. HA VALAMIHEZ TÉNYLEG KÜLSŐ TITOK KELL

Ha olyan lépéshez érkezel, amely ténylegesen megkövetel:

- jelszót;
- API secretet;
- service_role secretet;
- Anthropic API keyt;
- GitHub secretet;
- Supabase dashboard manuális beállítást;

és ezek nincsenek biztonságosan elérhető környezeti változóként:

NE kérdezz most.

NE állj le.

NE találj ki credentialt.

NE hardcode-olj secretet.

Jelöld:

`EXTERNAL ACTION REQUIRED`

és folytasd az összes többi feladattal.

A végső jelentésben külön blokkban sorold fel ezeket.

---

# 22. AUTONÓM MUNKAMÓD

A következő prioritási sorrendben dolgozz:

### P0 — pilotot blokkoló funkciók

1. CR7-03
2. job enqueue path
3. `/events`
4. `/assessments`
5. claims → event → assessment működő lánc
6. approved assessment → report candidate
7. browser E2E critical path

### P1 — pilot operáció

8. report workflow hiányzó részei
9. pilot workspace
10. job/status visibility
11. UX finding workflow
12. role-aware dashboards

### P2 — professzionális UI

13. application shell
14. navigation
15. design system
16. tables/cards/statuses/forms
17. empty/loading/error states
18. responsive/accessibility

### P3 — dokumentáció és quality

19. tests
20. runbook
21. CR evidence
22. CG7 update
23. final readiness report

Ha az időkeret miatt minden enhancement nem készül el, a P0 és P1 funkciók elsőbbséget élveznek a vizuális finomhangolással szemben.

Ugyanakkor ne hagyd a rendszert a jelenlegi nyers HTML-szintű megjelenésen, ha van idő a működő út elkészítése után.

---

# 23. GIT FEGYELEM

Munka előtt ellenőrizd a repository állapotát.

Ne írj felül ismeretlen user módosítást.

Dolgozz külön, jól azonosítható branch-en, például:

`cr7-03-pilot-operational-path`

A commitok legyenek logikusan elkülönítve, például:

- CR7-03 DB/API
- event/assessment UI
- pilot/report integration
- UX/design system
- tests/docs

Ne force pusholj.

---

# 24. DEFINITION OF DONE

A munka akkor tekinthető technikailag késznek, ha legalább:

1. analyst UI-ról el tud indulni claimből;
2. event létrejön / kezelhető;
3. szükséges jobok emberi requestre enqueue-zhatók;
4. worker végig tudja vinni a szükséges AI lépéseket;
5. assessment megjelenik;
6. human assessment review végrehajtható;
7. approved assessment létrejön;
8. report candidate pool fel tudja venni;
9. report workflow UI-ról használható;
10. QA megnyitható;
11. warning acknowledgement működik;
12. content approval működik;
13. security review működik;
14. release authority döntés működik;
15. released artifact elérhető;
16. PDF és manifest ellenőrizhető;
17. pilot timer és measurement nem sérül;
18. role boundary-k megmaradnak;
19. audit/provenance végig megmarad;
20. az egész út browser E2E-ben bizonyítható.

---

# 25. AMIT MOST KIFEJEZETTEN NE TEGYÉL

- ne indíts éles LIVE ciklust;
- ne indíts valódi P7C-REPLAY-01 mért ciklust pusztán teszt céljából;
- ne állítsd CG7-et PASS/CLOSED állapotra;
- ne állítsd, hogy operational value validated;
- ne változtasd meg a Phase 1–6 baseline semantics-ot;
- ne hardcode-olj secreteket;
- ne töröld a korábbi immutable provider-price rekordot;
- ne változtasd meg a jelenleg elfogadott cost assumptiont;
- ne változtasd meg az elfogadott provider/model konfigurációt;
- ne építs deploymentet internetre.

---

# 26. A MUNKA VÉGÉN NE KÉRJ ÁLTALÁNOS VISSZAJELZÉST

A végén készíts egy tömör, de teljes EXECUTION REPORT-ot.

Pontosan ezeket tartalmazza:

### A. Elkészült
Minden megvalósított funkció.

### B. Fájlok / migrációk
Mely fájlok változtak és milyen új migration készült.

### C. UI
Milyen oldalakat és UX-elemeket készítettél el.

### D. Backend
Milyen DB/API/worker változás történt.

### E. Security / roles
Mit teszteltél és milyen eredménnyel.

### F. Tests
Pontosan mely tesztek futottak és milyen eredménnyel.

### G. E2E
Meddig jut el ténylegesen a böngészőből végigjárható workflow.

### H. First REPLAY readiness
Kifejezetten:

`READY FOR P7C-REPLAY-01`

vagy

`NOT READY FOR P7C-REPLAY-01`

és egy mondatban az ok.

### I. External action required
Csak azok a dolgok, amelyeket valóban nem lehetett nélkülem megoldani.

### J. Remaining work
Csak valódi maradék, prioritással.

### K. Git
Branch és commit hash-ek.

Ne adj nekem közben végrehajtandó feladatokat.

A következő időszak célja az, hogy mire visszatérek, ne egy újabb tervet kapjak, hanem **a lehető legnagyobb részben elkészült, tesztelt, használható LFHÉ Phase 7 pilot rendszert**.