# LFHÉ – Control Gate 0: Architecture Review

Oct 11, 2026 · @Anton

## Státusz

**CONTROL GATE 0 STATUS: READY FOR PRODUCT OWNER REVIEW.** Nincs
blokkoló kérdés és nincs anyagi specifikációs ellentmondás; minden
nyitott pont biztonságos alapértelmezéssel indítható vagy későbbi
fázisban dönthető.

Kiindulási baseline: System Concept v1.0 · Master Spec v1.0 ·
Enforcement Addendum v1.0 · Development Spec v1.0 · Module Prompt
Baseline (v1.1 + v1.2 + v1.2.1 + v1.2.2, kumulatív) · GS-001 + v1.1 ·
Handoff Pack v1.1.

## A. Rendszerértelmezés

1.  **Küldetés:** OSINT-alapú, MI-támogatott, ember által validált
    feldolgozó rendszer; hetente arra felel, mi változott a légi
    tartományban, miért számít, mit kell figyelni.

2.  **Elsődleges fogyasztó:** felső katonai vezetés és felsővezetői
    törzs; „executive intelligence first”.

3.  **Alap felderítési követelmény:** a korábban ismert állapothoz
    képest érdemi változást jelentő légi és támogató
    képesség-fejlemények, ezek magyar és NATO implikációi, és a további
    figyelendő indikátorok.

4.  **Központi elemzési egység a változás:** INFORMATION → CHANGE →
    SIGNIFICANCE → ASSESSMENT → OUTLOOK, perzisztens baseline-hoz mérve.

5.  **Nyolc PIR, földrajzi prioritás:** a PIR-01 scope-ját a Concept
    teljes felsorolása adja. PA1 Oroszország, Ukrajna, Belarusz, keleti
    szárny; PA2 fő NATO-szövetségesek; PA3 szelektív; Global Watch.

6.  **Objektumhierarchia:** SOURCE → ARTICLE → ORIGINAL-LANGUAGE
    SNAPSHOT → EVIDENCE SPAN → CLAIM → EVENT (verziók) → ASSESSMENT
    (verziók, statementek) → TREND / INDICATOR → REPORT (verziók,
    statementek). A rétegek nem vonhatók össze.

7.  **Episztemikus fegyelem:** elkülönül a tény, a feltevés és az
    értékelés; a valószínűség és a bizonyosság; a jelentett és a
    megerősített; a publikálás és az esemény ideje; a publikációszám és
    a függetlenség.

8.  **Provenance:** minden kiadott tényállítás visszavezethető az
    eredeti nyelvű snapshot pontos szövegrészéig; a fordítás csak
    segédeszköz.

9.  **Időfegyelem:** INFORMATION_CUTOFF LIVE és REPLAY szabállyal; a
    baseline és a referencia-kontextus is cutoff-jogosult; historikus
    verziót nem írunk felül.

10. **Feladatmegosztás:** az MI feldolgoz és javasol (M02–M10);
    determinisztikus szoftver szűr, ellenőriz és állapotot vezet (M01,
    M10-D, kiadási ellenőrzés); az ember ítél, véglegesíti a
    bizonyosságot, biztonsági felülvizsgálatot végez és kiad.

11. **Fail-closed működés:** a bizonytalansági állapotok érvényes
    kimenetek; eszkalálunk, nem kitalálunk.

12. **Kontrollált pipeline, nem ágens:** elhatárolt modulok, sémakötött
    kimenet, verziózott promptok, provider-absztrakció.

13. **Minőségkapuk:** az M10-D és M10-S QA a kanonikus report-verzióhoz
    és hash-hez kötött; kiadás csak verzióhoz kötött emberi
    jóváhagyásokkal.

14. **OSINT-only határ:** nincs minősített vagy védett adat; titok nem
    kerül kódba vagy promptba; a kereskedelmi MI csak engedélyezett
    OSINT-ot kap.

15. **Végtermék:** kétoldalas vezetői jelentés (max. 3 KJ, 4–5 SD, 4–6
    indikátor, 3 What-to-Watch) kanonikus JSON-ból renderelve; a termék
    a rendszer, a PDF csak a kimenete.

## B. Követelmény → komponens térkép

| Objektum                   | Felelősség                                                                              | Tárolás                                                 | Fő kapcsolatok                                            | Fázis          |
|----------------------------|-----------------------------------------------------------------------------------------|---------------------------------------------------------|-----------------------------------------------------------|----------------|
| SOURCE                     | Forrásregiszter, megbízhatósági prior, függetlenségi csoport, gyűjtési és megőrzési mód | PG sources                                              | → articles, collection_runs                               | P1             |
| ARTICLE                    | Logikai cikk (kanonikus URL forrásonként)                                               | PG articles                                             | source → ; → snapshots                                    | P1             |
| ORIGINAL-LANGUAGE SNAPSHOT | Változtathatatlan tartalmi állapot; időpontok, elérhetőségi basis                       | PG article_snapshots + Storage (content-addressed)      | article → ; → claims, text_representations                | P1             |
| EXACT EVIDENCE SPAN        | Claim lehorgonyzása az eredeti nyelvű kanonikus szöveghez                               | Claim-mezők + text_representation_id                    | snapshot / text_representation → claim                    | P2             |
| CLAIM                      | Önállóan vizsgálható, attribuált állítás                                                | PG claims + claim_status_history                        | span → ; → lineage, events, statement evidence; model_run | P2             |
| CLAIM LINEAGE              | Claim-szintű leszármazás, külső eredet, független csoport                               | PG claim_lineage, external_origins, independence_groups | claim ↔ claim / article / external origin                 | P3             |
| ENTITY                     | Konzervatív entitásfeloldás                                                             | PG entities, entity_relationships, claim_entities       | ↔ claims, events                                          | P2             |
| EVENT                      | Perzisztens esemény (fej)                                                               | PG events                                               | → versions, event_claims, relationships                   | P3             |
| EVENT VERSION              | Változtathatatlan esemény-snapshot, változásmodell                                      | PG event_versions (hash)                                | event → ; ← assessment_versions, report_items             | P3             |
| ASSESSMENT STATEMENT       | Típusos analitikai állítás, provenance-osztály                                          | PG assessment_statements (változtathatatlan)            | assessment_version → ; → statement_evidence               | P4             |
| ASSESSMENT VERSION         | M07-tervezet, emberi módosítás és jóváhagyás külön verzióként                           | PG assessment_versions (hash, AI- és végső bizonyosság) | event_version, baseline_version, előző verzió, model_run  | P4             |
| BASELINE                   | Verziózott, cutoff-jogosult előző állapot                                               | PG baseline_versions (knowledge_as_of)                  | ← assessment_versions; → forrásobjektumok                 | P4             |
| REFERENCE CONTEXT          | Kurált háttértudás kötelező provenance-szel                                             | PG reference_contexts, reference_context_versions       | → provenance refs; ← statement evidence                   | P4             |
| TREND                      | Több eseményen átívelő fejlemény (irány és sebesség külön)                              | PG trends, trend_versions, trend_events                 | ↔ events, indicators                                      | P4             |
| INDICATOR                  | Megfigyelhető jel, állapot                                                              | PG indicators, indicator_claims                         | ↔ assessments, trends, claims                             | P4             |
| REPORT ITEM STATEMENT      | Renderelt állítás, mapping, editorial transform, szerző                                 | PG report_item_statements + report_statement_sources    | report_item → ; → jóváhagyott assessment_statements       | P5             |
| REPORT VERSION             | Kanonikus JSON és hash; változtathatatlan                                               | PG report_versions                                      | report → ; ← qa_runs, approvals, manifest                 | P5             |
| QA RUN                     | M10-D / M10-S futás és eredmények                                                       | PG qa_runs, qa_check_results                            | (report_version_id, hash) → ; model_run                   | P6             |
| HUMAN REVIEW               | Analitikai döntések, eredeti és módosított érték                                        | PG human_reviews, analytical_approvals                  | objektum-verzió és hash →                                 | P1 alap, P3–P4 |
| SECURITY REVIEW            | Emberi kezelési és biztonsági döntés                                                    | PG security_reviews                                     | (report_version_id, hash) →                               | P6             |
| RELEASE MANIFEST           | A kiadott állapot hash-elt leltára                                                      | PG release_manifests + Storage (PDF)                    | release_decision, verziók, QA-futások                     | P6             |
| AUDIT LOG                  | Csak hozzáfűzhető, hash-láncolt napló                                                   | PG audit_log + külső export                             | minden állapotváltozás →                                  | P1             |
| MODEL RUN                  | LLM-hívások reprodukálható rekordja                                                     | PG model_runs + Storage (nyers kimenet)                 | prompt_version → ; ← MI-objektumok                        | P1 alap        |
| PROMPT VERSION             | Verziózott, sémakötött prompt                                                           | Git /packages/prompts + PG prompt_versions              | ← model_runs                                              | P1 alap        |

## C. Technikai architektúra (MVP)

A jóváhagyott stacket használja változatlanul; a kulcsdöntés, hogy a
workerek nem a Supabase service_role kulccsal, hanem korlátozott
adatbázis-szerepkörrel futnak.

1.  **Frontend:** Next.js / React, Vercelen vagy egyenértékű helyen.
    Elemzői munkaterület (dashboard, esemény-review, provenance-nézet,
    report workspace, forrásadminisztráció); minden emberi döntés
    szerveroldali műveleten megy át.

2.  **Backend / API:** Next.js szerveroldali route handlerek és server
    actionök. A csak emberi állapotátmenetek PostgreSQL SECURITY DEFINER
    függvények, amelyek az auth.uid() és a jogosultsági mátrix alapján
    ellenőriznek, és csak hitelesített felhasználói tokennel hívhatók.

3.  **Worker-futtatás:** Python workerek konténerben, hosszú futásra
    alkalmas környezetben (Fly.io, Cloud Run vagy Render; fejlesztéskor
    helyi Docker). Szolgáltatások: collector, preprocessor,
    ai-orchestrator, qa. Saját lfhe_worker Postgres-szerepkör, amely nem
    hívhat emberi átmeneti függvényt és nem írhat jóváhagyási vagy
    kiadási táblába.

4.  **Ütemező és sor:** egyetlen ütemezési réteg; a pg_cron csak jobokat
    ír a processing_jobs táblába, a workerek FOR UPDATE SKIP LOCKED
    mintával veszik fel őket. Idempotencia-kulcs: job_type, objektum,
    input hash, modul- és promptverzió; retry exponenciális
    visszalépéssel, majd operátori figyelmeztetés.

5.  **Adatbázis:** PostgreSQL (Supabase) mint rendszer-nyilvántartás. A
    verzió- és jóváhagyási táblák változtathatatlanok (triggerek tiltják
    az UPDATE és DELETE műveletet); kompozit (version_id, version_hash)
    idegen kulcsok kényszerítik a verziókötést; a pgvector csak
    visszakeresésre szolgál.

6.  **Tárolás:** Supabase Storage, környezetenként külön bucketek,
    content-addressed (sha256) útvonalak, felülírás tiltva.
    Forrásonkénti megőrzési mód: FULL / PERMITTED_EXCERPT /
    METADATA_ONLY.

7.  **Auth / RBAC:** Supabase Auth; user_roles és permissions mátrix;
    szerepkörök: ADMIN, ANALYST, REVIEWER, SECURITY_REVIEWER,
    RELEASE_AUTHORITY, VIEWER; alapból tiltó RLS; konfigurálható
    feladatkör-szétválasztás.

8.  **MI-provider absztrakció:** run_structured_task(module, envelope,
    model_config) provider-adapterekkel; JSON-sémavalidálás, korlátozott
    javítási újrapróbálkozás, majd SCHEMA_VALIDATION_FAILED; minden
    hívásról model_run rekord input- és kontextus-hash-sel.

9.  **Report-renderelés:** kanonikus JSON (RFC 8785 JCS) sha256
    hash-sel; determinisztikus HTML-template, PDF fejetlen Chromiummal.
    A template- és rendererverzió és a PDF hash-e bekerül a manifestbe.

10. **Audit / naplózás:** audit_log UPDATE/DELETE tiltással minden
    alkalmazás- és szolgáltatásszerepkörnek; trigger számolja a
    hash-láncot; a láncfej időszakos külső exportja. Nem állítjuk, hogy
    ez abszolút védelem egy teljes jogú adatbázis-adminisztrátorral
    szemben.

11. **Megfigyelhetőség:** strukturált logok, system_errors és
    collection_runs; mérőszámok a gyűjtésről, jobokról, sémahibákról,
    sorhosszról, késleltetésről, review-hátralékról és költségről;
    konfigurálható riasztások.

12. **DEV / TEST / PROD:** három külön Supabase-projekt, külön storage
    és kulcsok; a promptaktiválás környezetenként auditált emberi
    művelet; a GS-001 csak TEST-ben fut; migrációk a Supabase CLI-vel
    GitHubon.

## D. Adatfolyam és bizalmi határok

A 17 lépéses folyamatban az MI csak javasol; a jogosultsági és kiadási
döntéseket determinisztikus szoftver ellenőrzi, a döntéseket ember
hozza.

| \#  | Lépés                                                                                       | Végrehajtó                                                  |
|-----|---------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| 1   | PUBLIC SOURCE → COLLECTION (API / RSS / HTTP, rate limit, hozzáférés-korlátozás tisztelete) | Determinisztikus                                            |
| 2   | ORIGINAL SNAPSHOT (nyers és tiszta szöveg, hash, időpontok, basis)                          | Determinisztikus                                            |
| 3   | PREPROCESSING (M01: kanonikus URL, nyelv, dátumok, duplikátum 1. réteg)                     | Determinisztikus                                            |
| 4   | CLAIM EXTRACTION (M02) → sémavalidálás → QA-D18 grounding                                   | MI → determinisztikus                                       |
| 5   | TAXONOMY (M03)                                                                              | MI                                                          |
| 6   | LINEAGE (M04 javaslat; korroborációs státusz workflow szerint)                              | MI → determinisztikus; nagy hatásúnál ember                 |
| 7   | EVENT (M05 javaslat; CANDIDATE létrehozás és csatolás; merge / split / supersede)           | MI → determinisztikus; merge / split / supersede csak ember |
| 8   | RELEVANCE (M06; nincs rejtés)                                                               | MI; felülbírálás ember                                      |
| 9   | ASSESSMENT (M07; baseline- és referencia-kontextus jogosultság előtte)                      | Determinisztikus → MI                                       |
| 10  | CHALLENGE (M08)                                                                             | MI                                                          |
| 11  | HUMAN REVIEW (REVIEW_DECISION, végső bizonyosság, flag-kezelés)                             | Ember                                                       |
| 12  | REPORT (jelöltkiválasztás → M09 → kanonikus JSON-verzió)                                    | Ember → MI → determinisztikus                               |
| 13  | QA (M10-D → M10-S → kombinált státusz)                                                      | Determinisztikus + MI                                       |
| 14  | Figyelmeztetés-nyugtázás, tartalmi jóváhagyás                                               | Ember                                                       |
| 15  | SECURITY REVIEW                                                                             | Ember                                                       |
| 16  | Kiadási jogosultság-ellenőrzés                                                              | Determinisztikus                                            |
| 17  | HUMAN RELEASE → manifest → ARCHIVE                                                          | Ember → determinisztikus                                    |

### Bizalmi határok

- **TB-1 Internet → collector:** minden tartalom ellenséges lehet;
  méret- és típuskorlát, nincs aktív tartalom futtatása, nincs
  hozzáférés-korlátozás megkerülése.

- **TB-2 Forrástartalom → LLM:** a forrásszöveg adatként, elhatárolt
  blokkban kerül a promptba; jogosultsági hierarchia a promptban;
  prompt-injection regressziós tesztek.

- **TB-3 LLM-kimenet → adatbázis:** csak sémavalidált, modellfutáshoz
  kötött objektum kerül be; részleges kimenet soha nem authoritative.

- **TB-4 Worker → emberi jogkörű állapotok:** adatbázis-szerepkör és
  függvényjogosultság zárja el; triggerek tiltják a közvetlen
  státuszírást.

- **TB-5 Felhasználó → rendszer:** hitelesítés, szerveroldali
  jogosultság, RLS.

- **TB-6 TEST answer key → értékelő:** fizikailag elkülönítve, a
  pipeline számára elérhetetlenül.

- **TB-7 Rendszer → külső MI-provider:** csak OSINT-adat; kulcsok
  titokkezelőben; QA-14 határellenőrzés.

## E. Provenance-architektúra

A jóváhagyások kompozit (id, hash) idegen kulcsa adatbázis-szinten
lehetetlenné teszi, hogy egy jóváhagyás nem egyező verzióra mutasson; új
verzió új azonosítót és hash-t kap, így nem örököl jóváhagyást.

1.  articles.source_id → sources.id

2.  article_snapshots.article_id → articles.id; egyedi (article_id,
    content_hash); monoton snapshot_version. Revízió = új snapshot, a
    régi megmarad.

3.  text_representations.snapshot_id → snapshot; kanonikus tiszta
    szöveg, preprocessor_version, hash. Az offsetek erre a
    változtathatatlan szövegre vonatkoznak; új preprocessor-verzió új
    reprezentáció.

4.  claims.article_snapshot_id és claims.text_representation_id;
    evidence_span_original (nyelv, exact_text, offsetek, locator_type);
    QA-D18 egyezés- és nyelvellenőrzés; claims.created_by_model_run_id →
    model_runs.

5.  claim_status_history: claim_id, új és régi státusz, ajánló
    model_run, review_id, high-impact újravalidálási jelölő.

6.  claim_lineage: child_claim_id, és parent_claim_id /
    parent_article_id / external_origin_id közül pontosan egy;
    independence_group_id.

7.  event_claims: event_version_id → claim_id, szereppel (supports,
    contradicts, updates, contextualises).

8.  assessment_versions: assessment_id, version_no, content_hash,
    event_version_id, baseline_version_id,
    previous_assessment_version_id, model_run vagy emberi szerző,
    ai_recommended_confidence, final_analytic_confidence (csak emberi
    jóváhagyással).

9.  assessment_statements: assessment_version_id → (változtathatatlan),
    provenance_class, attribution_required (orchestrator által
    származtatva).

10. assessment_statement_evidence: statement_id → claim_id VAGY
    reference_context_version_id VAGY baseline_version_id, szereppel.

11. analytical_approvals: (assessment_version_id,
    assessment_version_hash) kompozit FK, reviewer, decision, végső
    bizonyosság és indoklás.

12. report_versions: report_id, version_no, canonical_json,
    report_version_hash; egyedi (id, hash).

13. report_items → report_version_id; pinned_event_version_id,
    pinned_assessment_version_id.

14. report_item_statements → report_item; author_type (MODEL / HUMAN),
    model_run_id vagy user_id, editorial_transform.

15. report_statement_sources: report_item_statement_id →
    assessment_statement_id; a statement a tétel által rögzített,
    jóváhagyott assessment_version-höz tartozik.

16. qa_runs: (report_version_id, report_version_hash) kompozit FK, kind
    (D / S), model_run_id, prompt_version_id; qa_check_results → qa_run.

17. warning_acknowledgements, content_approvals, security_reviews: mind
    (report_version_id, report_version_hash) kompozit FK-val.

18. release_decisions: (report_version_id, hash), qa_run_id-k,
    security_review_id, released_by.

19. release_manifests: release_decision_id, manifest_json (v1.2.1 11.
    pont + template / renderer verzió + PDF hash), manifest_hash; kiadás
    után változtathatatlan.

## F. Idő- és cutoff-modell

Hat időfogalmat kezelünk külön; a jogosultságot az elérhetőség, LIVE
módban a letöltés és a knowledge_as_of határozza meg, az esemény ideje
soha.

| Idő                      | Jelentés                                           | Tárolás                                           | Jogosultsági szerep        |
|--------------------------|----------------------------------------------------|---------------------------------------------------|----------------------------|
| EVENT_TIME               | Mikor történt a valós fejlemény                    | claims.event_date + confidence; event start / end | Nem jogosultsági kritérium |
| PUBLICATION_TIME         | A forrás által megadott publikálás                 | snapshot.publication_datetime                     | Információ                 |
| PUBLIC_AVAILABILITY_TIME | Mikor vált nyilvánossá; basis és confidence        | snapshot.public_availability\_\*                  | ≤ cutoff (mindkét mód)     |
| SYSTEM_RETRIEVAL_TIME    | Mikor töltöttük le                                 | snapshot.retrieved_at                             | ≤ cutoff csak LIVE módban  |
| KNOWLEDGE_AS_OF          | A baseline vagy referencia-kontextus tudásállapota | baseline_versions / reference_context_versions    | ≤ cutoff                   |
| INFORMATION_CUTOFF       | A jelentés rögzített tudáshatára                   | reports / report_versions + report_mode           | Ehhez mérünk               |

- **LIVE:** jogosult, ha elérhetőség ≤ cutoff ÉS letöltés ≤ cutoff. A
  cutoff után begyűjtött információ a következő ciklusba kerül.

- **REPLAY:** jogosult, ha elérhetőség ≤ historikus cutoff és a basis
  elfogadott (v1.2 8. pont). Feltételes basis csak fagyasztott vagy
  archivált tartalommal; UNKNOWN, INFERRED, CURRENT_PAGE_ONLY → kizárás
  vagy HUMAN_REVIEW_REQUIRED (auditált).

- **Baseline és referencia-kontextus:** knowledge_as_of ≤ cutoff, és
  minden ténybeli komponens forrása jogosult; determinisztikus előszűrés
  az M07 előtt, majd QA-D21 és QA-D22.

- **Késői weboldal-változás elleni védelem:** a bizonyíték mindig egy
  konkrét, hash-elt snapshot, soha nem az élő URL. Változáskor új
  snapshot készül; a replay a cutoff előtti elérhetőséget igazoló
  snapshotot használja. A GS-001 S04 és S08 forrásai erre konkrét
  példák.

## G. Állapotgépek

A RELEASED állapot kizárólag egy jogosult ember által hívott
adatbázis-függvénnyel érhető el; worker, ütemező és
szolgáltatásszerepkör nem juthat oda.

Jelmagyarázat: \[AI\] MI-javaslat · \[D\] determinisztikus
rendszerátmenet · \[H\] csak emberi átmenet.

### CLAIM

- EXTRACTED →\[D\] GROUNDED / GROUNDING_FAILED (QA-D18 + sémavalidálás).

- Korroborációs státusz (UNVERIFIED → PARTIALLY_CORROBORATED /
  CORROBORATED / CONFIRMED_PRIMARY / CONTESTED / DISPROVEN /
  SUPERSEDED): az M04 javasolja \[AI\]; alacsony hatású claimnél
  konfigurált, auditált szabály alkalmazhatja \[D\]; nagy hatású
  claimnél minden átmenet \[H\].

- Alacsony hatásúból nagy hatásúvá vált claim →\[D\]
  HIGH_IMPACT_REVALIDATION_REQUIRED →\[H\] megerősítve vagy elutasítva.

- Review: PENDING →\[H\] VALIDATED / MODIFIED / REJECTED.

### EVENT

- M05 proposal \[AI\]. CREATE_NEW_EVENT →\[D\] CANDIDATE esemény
  AI-eredetűként; UPDATE_EXISTING_EVENT →\[D\] új AI-eredetű
  event_version review-jelzéssel (nagy hatású eseménynél kötelező emberi
  validálás).

- CANDIDATE →\[H\] ACTIVE / DEVELOPING / CONFIRMED / CONTESTED / CLOSED
  / REJECTED.

- MERGE / SPLIT / SUPERSEDE kizárólag \[H\], event_relationships
  rögzítésével; régi azonosító nem törölhető.

### ASSESSMENT

- DRAFT (M07) \[AI\] → CHALLENGED (M08) \[AI\] → IN_REVIEW \[D\].

- IN_REVIEW →\[H\] APPROVE / MODIFY_AND_APPROVE (új jóváhagyott verzió
  végső bizonyossággal) / REJECT / ESCALATE / REQUEST_REPROCESSING.

- APPROVED → SUPERSEDED \[D\], amikor új jóváhagyott verzió készül; a
  régi megmarad.

### REPORT

- CANDIDATE_POOL →\[H\] SELECTION → M09 \[AI\] → DRAFT_VERSION vN
  (kanonikus JSON, hash) \[D\].

- Emberi szerkesztés \[H\] → új DRAFT_VERSION \[D\]; korábbi QA,
  jóváhagyások és security review érvénytelen.

- QA_RUNNING \[D\] → QA_FAILED / QA_PASSED / QA_PASSED_WITH_WARNINGS
  \[D\]; PASS_WITH_WARNINGS →\[H\] nyugtázás.

- →\[H\] CONTENT_APPROVED → SECURITY_REVIEW_PENDING \[D\].

### SECURITY REVIEW (verzióhoz kötve)

- PENDING →\[H\] APPROVED / RETURN_FOR_REVISION / REJECTED.

- Új report-verzió →\[D\] PENDING.

### RELEASE

- RELEASE_ELIGIBILITY_CHECK \[D\]: QA-futás, tartalmi jóváhagyás,
  security review és nyugtázások mind az aktuális (verzió, hash) párra
  mutatnak; nincs CRITICAL hiba.

- →\[H\] APPROVE_FOR_RELEASE / RETURN_FOR_REVISION / REJECT_RELEASE.

- APPROVE_FOR_RELEASE → RELEASED + manifest \[D, egy tranzakcióban\].

### RELEASED-védelem

1.  A RELEASED állapot csak a release_report(version_id, hash)
    adatbázis-függvénnyel érhető el.

2.  A függvény hitelesített felhasználót és RELEASE_AUTHORITY
    jogosultságot követel, és belül újrafuttatja a jogosultsági
    ellenőrzést.

3.  A worker, az ütemező és a szolgáltatásszerepkör nem kap EXECUTE
    jogot.

4.  Trigger tiltja a státuszmező közvetlen írását.

5.  Az RLS tiltja a kiadási táblák írását nem emberi szerepkörnek.

6.  Negatív tesztek igazolják.

## H. QA-architektúra

A 28 ellenőrzésből a strukturált állapotban megválaszolható kérdések
determinisztikusak (D); LLM-et (S) csak a szemantikai ítéletekhez
használunk.

| Check                                               | Mechanizmus                                                                          |
|-----------------------------------------------------|--------------------------------------------------------------------------------------|
| QA-01 Provenance / entailment                       | D: mapping és ID-feloldás · S: entailment, scope, episztemikus erősség               |
| QA-02 Forrás létezése                               | D                                                                                    |
| QA-03 Dátumkonzisztencia                            | D (S csak szöveges értelmezésnél)                                                    |
| QA-04 Cutoff-jogosultság (LIVE / REPLAY)            | D; az event time nem kritérium                                                       |
| QA-05 Függetlenség                                  | D: ismert lineage és csoportok · S: feloldatlan szemantika                           |
| QA-06 Számok                                        | D: egyezés és strukturált származtatás · S: scope és attribúció                      |
| QA-07 Fact / assessment / erősség                   | D: authoritative státusz-konzisztencia · S: szövegezés                               |
| QA-08 Bizonyosság-integritás                        | D                                                                                    |
| QA-09 Ellentmondás megőrzése                        | S                                                                                    |
| QA-10 Jóváhagyott objektumok                        | D                                                                                    |
| QA-11 Verzió-pinning                                | D                                                                                    |
| QA-12 Modell- és prompt-nyomonkövetés               | D                                                                                    |
| QA-13 Félrevezető duplikáció                        | D: ismert ID-k és kapcsolatok · S: szemantikus                                       |
| QA-14 OSINT-határ                                   | D: forrás- és metaadat-szabályok · kétes esetben ember · S csak gyanút jelezhet      |
| QA-15 Security-állapot                              | Nem M10-tartalom; determinisztikus kiadási ellenőrzés a review után                  |
| QA-16 Manifest                                      | D                                                                                    |
| QA-17 Hindsight                                     | D: cutoff, baseline, referencia-kontextus jogosultság · S: nem alátámasztott állítás |
| Report-struktúra                                    | D: darabszám-korlátok, kötelező szekciók, séma, bizonyosságmezők, mappingek          |
| D18 Claim grounding (eredeti nyelv)                 | D                                                                                    |
| D19 Attribúció-elhagyhatóság                        | D                                                                                    |
| D20 Nagy hatású emberi validálás                    | D                                                                                    |
| D21 Baseline-jogosultság                            | D                                                                                    |
| D22 Referencia-kontextus jogosultság                | D                                                                                    |
| D23 Report-hash és QA kötése                        | D                                                                                    |
| D24 Jóváhagyás-verziókötés                          | D                                                                                    |
| D25 Manifest-teljesség                              | D                                                                                    |
| S18 Claim-normalizálási hűség (eredeti nyelvű span) | S                                                                                    |
| S19 Attribúció megőrzése                            | S                                                                                    |
| S20 Referencia-kontextus szemantikai scope          | S                                                                                    |

**Futási rend:** az M10-D előbb fut; CRITICAL hiba esetén az M10-S csak
diagnosztikai céllal fut. Az M10-S megkapja a D-eredményeket; a
kombinált státusz determinisztikusan számolódik. Mindkét futás saját
qa_run rekordot kap ugyanarra a (verzió, hash) párra.

## I. GS-001 tesztarchitektúra

Az answer key fizikailag a pipeline által elérhetetlen tárban van, és
csak a futás lezárása után olvasható; a GS-001 regressziós historikus
replay benchmark, nem vak mérés.

- **Tárolás:** a raw input (eredeti nyelvű snapshotok,
  basis-bizonyítékok, opcionálisan jogosult baseline és
  referencia-kontextus) a TEST környezetbe töltődik standard ingestion
  útvonalon. Az answer key (/expected-\*, /evaluation, a GS-001
  dokumentum) külön, értékelői hozzáférésű tárban van (külön privát repó
  vagy bucket); nem része a worker-image-nek. A /tests/gold-standard a
  worker-buildből kizárt.

- **Jogosultság:** csak az lfhe_evaluator szerepkör olvassa az answer
  keyt, és csak a futás lezárása után.

- **Orchestrator input-whitelist:** a TEST futás envelope-jai csak az
  adott run_id-hez ingestált snapshotokra és az azokból keletkezett
  objektumokra hivatkozhatnak; más forrású objektum esetén a job hibára
  fut.

- **Kontextus-hash:** az input_snapshot_hash és context_snapshot_hash
  minden model_run rekordban; utólag bizonyítható, mi került a modell
  elé.

- **Baseline és referencia-kontextus izoláció:** csak explicit
  jóváhagyott, cutoff-jogosult objektumok; answer-key tartalom nem
  kerülhet beléjük (jóváhagyási ellenőrzőlista).

- **Post-cutoff csapda:** a tesztcsatornát a materializáláskor kell
  eldönteni (K-11); ha a post-cutoff cikk a jelöltkészletben van, a
  QA-04 kizárását teszteljük.

- **Értékelés:** a run_completed után az értékelő összeveti a kimenetet
  az answer keyjel, a GS-001 25. pontja szerinti metrikákkal, két
  szinten: az emberi kapu előtti AI-kimenetek és a kapu utáni jelentés;
  jelölve, ha a bíráló ismerte az answer keyt.

- **Értelmezési keret:** a promptok GS-001-ismerettel készültek, ezért
  prompt- vagy fixture-tartalomba GS-001-specifikus anyag nem kerülhet
  (Handoff 53/P).

## J. Kockázatnyilvántartás

A 26 kockázatból 7 egyszerre magas valószínűségű és magas hatású
(cikkrevízió, fordítás, claim-kinyerés, attribúció, körkörös jelentés,
prompt injection, automatizációs torzítás); mindegyikhez van
determinisztikus vagy QA-alapú detektálás. V = valószínűség, H = hatás
(A alacsony, K közepes, M magas).

| Kockázat                        | V   | H   | Mitigáció                                                                           | Detektálás                                | Felelős réteg         |
|---------------------------------|-----|-----|-------------------------------------------------------------------------------------|-------------------------------------------|-----------------------|
| Forrás törékenysége             | M   | K   | Feed / API előnyben; adapterenkénti hibakezelés; SOURCE_UNAVAILABLE ≠ nincs esemény | collection_runs, kiesési riasztás         | Collector             |
| Cikkrevízió                     | M   | M   | Változtathatatlan snapshotok, revízió = új snapshot                                 | content_hash-változás                     | M01 / Storage         |
| Elérhetőségi bizonytalanság     | K   | M   | basis + confidence; REPLAY basis-szabályok                                          | QA-04, D18                                | M01 / M10-D           |
| Fordítási hiba                  | M   | M   | Eredeti nyelvű span authoritative; TRANSLATION_MATERIAL_MISMATCH                    | S18, emberi review                        | M02 / M10-S           |
| Claim-kinyerési hiba            | M   | M   | Precision \> recall; séma; grounding                                                | D18, S18, korrekciós arány                | M02                   |
| Attribúció elvesztése           | M   | M   | Span-alapú normalizálás; attribution_may_be_omitted                                 | S18, D19, S19                             | M02 / M07 / M09 / M10 |
| Hallucináció                    | K   | M   | Csak kapott bizonyíték; statement-provenance                                        | QA-01, QA-17                              | M07 / M09 / M10       |
| Körkörös jelentés               | M   | M   | Claim-szintű lineage, függetlenségi csoportok                                       | QA-05, M08                                | M04                   |
| Esemény-túlösszevonás           | K   | M   | Konzervatív M05; merge csak ember                                                   | Over-merge arány                          | M05 / ember           |
| Esemény-alulösszevonás          | M   | K   | Szemantikus visszakeresés; SUGGEST_MERGE                                            | Under-merge arány, QA-13                  | M05                   |
| Hibás baseline                  | K   | M   | Verziózott, jogosult baseline; BASELINE_ERROR flag                                  | D21, M08                                  | Orchestrator / M08    |
| Hindsight-szennyezés            | K   | M   | Snapshotok, cutoff-szűrés, evidence-only                                            | QA-04, QA-17, D21–22                      | M10                   |
| Referencia-kontextus szennyezés | K   | M   | Kötelező provenance, knowledge_as_of, jóváhagyás                                    | D22, S20                                  | Ember / M10           |
| Prompt injection                | M   | M   | Adat / utasítás elválasztás; séma; szerepkörkorlát                                  | Adverzariális regresszió                  | Prompt / orchestrator |
| Modell-regresszió               | K   | M   | Verziózott modellkonfig; GS-regresszió                                              | Regressziós metrikák                      | Teszt                 |
| Prompt-regresszió               | K   | M   | Szemantikus verziózás; regressziós kapu                                             | Regressziós metrikák                      | Teszt                 |
| Automatizációs torzítás         | M   | M   | Látható bizonyíték, M08, naplózott döntések                                         | Korrekciós arány (túl alacsony is jelzés) | UI / ember            |
| M06 kapuőr-hatás                | K   | M   | Nincs rejtés; kézi előléptetés                                                      | Kimaradt jelentős események aránya        | M06 / UI              |
| Bizonyosság-inflálódás          | K   | M   | Javasolt és végső bizonyosság elkülönítése; M08                                     | QA-08, egyezési arány                     | M07 / ember           |
| QA utáni szerkesztés            | K   | M   | Kanonikus hash, kompozit FK                                                         | D23, D24                                  | DB / M10-D            |
| Titokszivárgás                  | K   | M   | Titokkezelő, gitleaks CI, .env tiltás                                               | Secret scanning                           | DevOps                |
| MI-provider kiesés              | K   | K   | Retry / backoff; részleges kimenet nem authoritative                                | Job-hibaarány riasztás                    | Orchestrator          |
| Vendorfüggés                    | K   | K   | Provider-absztrakció, modellfüggetlen tárolás                                       | Architektúra-review                       | Architektúra          |
| Költségnövekedés                | K   | K   | Model escalation, determinisztikus előszűrés, költségkövetés                        | Költség modulonként                       | Orchestrator          |
| Adatbázis-kiesés                | A   | M   | Menedzselt PG, PITR                                                                 | Health check                              | Infra                 |
| Backup / restore hiba           | K   | M   | Automatikus backup, tesztelt visszaállítás                                          | Restore-gyakorlat                         | Infra                 |

## K. Döntések és hiányok

A 13 nyitott pont egyike sem blokkoló; mindegyikhez van biztonságos
alapértelmezés vagy későbbi fázisba sorolható.

| ID   | Téma                                                 | Osztály                                                 | Javasolt alapértelmezés / megjegyzés                                                                                                                   |
|------|------------------------------------------------------|---------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| K-01 | Worker-futtatási környezet                           | NON-BLOCKING                                            | Phase 1 helyi Docker; telepítés előtt döntés (Fly.io / Cloud Run / Render), ADR-rel                                                                    |
| K-02 | Ütemező: pg_cron vs. Python scheduler                | NON-BLOCKING                                            | pg_cron csak enqueue-ra (egy ütemezési réteg)                                                                                                          |
| K-03 | Sor: táblaalapú vs. pgmq                             | NON-BLOCKING                                            | processing_jobs + SKIP LOCKED                                                                                                                          |
| K-04 | Forrásonkénti megőrzési jog                          | NON-BLOCKING (séma P1-ben)                              | retention_mode forrásonként; METADATA_ONLY forrás nem adhat lényeges claimet, mert a QA-D18 nem teljesülhet; ilyenkor engedélyezett szövegrészlet kell |
| K-05 | Kezdeti 5–10 forrás listája                          | NON-BLOCKING a kezdéshez; Phase 1 lezárásához szükséges | A Product Owner adja; gyűjtési mód és felhasználási feltételek forrásonként                                                                            |
| K-06 | Feladatkörök szétválasztása                          | NON-BLOCKING                                            | Konfigurálható; prototípusban egy személy több szerepet is betölthet, naplózva és jelölve                                                              |
| K-07 | Supabase / Vercel régió                              | NON-BLOCKING                                            | EU régió                                                                                                                                               |
| K-08 | Kanonikus JSON-szerializálás                         | NON-BLOCKING                                            | RFC 8785 JCS + sha256 (ADR)                                                                                                                            |
| K-09 | Template- és renderer-verzió, PDF-hash a manifestben | DEFER (P5–P6)                                           | A manifest „at minimum” listájának kiegészítése                                                                                                        |
| K-10 | M05 automatikus alkalmazási köre                     | DEFER (P3)                                              | CREATE → CANDIDATE és UPDATE → AI-eredetű verzió \[D\]; MERGE / SPLIT / SUPERSEDE \[H\]                                                                |
| K-11 | GS-001 Patriot-csapda tesztcsatorna                  | DEFER (P4)                                              | Döntés a raw input materializálásakor                                                                                                                  |
| K-12 | Kanonikus mezőnév (evidence_span_original)           | DEFER (P2)                                              | A v1.2.2 név az irányadó                                                                                                                               |
| K-13 | QA-04 elnevezés pontosítása                          | NON-BLOCKING                                            | Dokumentációban: az event time nem jogosultsági kritérium                                                                                              |

## L. Phase 1 megvalósítási terv (csak terv)

A Phase 1 tizenegy kis lépésben épül fel; az F1–F10 elfogadási
kritériumokat a P1-11 automatizált tesztcsomagja ellenőrzi.

| Lépés                          | Cél                                                        | Komponensek                                                                                                    | Fájlok / könyvtárak                                                                                                                                      | DB-objektumok                                                                                                                 | Tesztek                                                                                                           | Elfogadás                                            |
|--------------------------------|------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|------------------------------------------------------|
| P1-01 Repó és keret            | Minimális monorepo, CI, dokumentációs váz                  | Git, CI (lint, teszt, gitleaks), .gitignore, .env.example                                                      | /apps/web, /services/collector, /packages/schemas, /database/migrations, /tests, /docs/SPEC_INDEX.md, /docs/PROJECT_STATUS.md, /CHANGELOG.md, /docs/adr/ | –                                                                                                                             | CI zöld; dummy titok elutasítása                                                                                  | F8 alapja; SPEC_INDEX az aktív verziókkal            |
| P1-02 Környezetek              | DEV / TEST / PROD, titokkezelés                            | Három Supabase-projekt (DEV-vel indulva), konfigurációs séma                                                   | /packages/shared/config, /docs környezetleírás                                                                                                           | –                                                                                                                             | Hibás konfiguráció esetén indulás megtagadva                                                                      | Titok csak env-ben vagy titokkezelőben (F8)          |
| P1-03 DB-alap                  | Verziózott migrációk, enumok, szerepkörök                  | Supabase CLI, pgcrypto, alapból tiltó RLS                                                                      | /database/migrations/0001\_\*, /database/policies                                                                                                        | Kanonikus enumok (REVIEW_DECISION, EVENT_ACTION, RELEASE_DECISION, audit-típusok, basis-értékek); lfhe_worker, lfhe_evaluator | Migrációk lefutnak és visszagörgethetők                                                                           | Nincs manuális sémamódosítás                         |
| P1-04 Auth és RBAC             | Hitelesítés, jogosultsági mátrix, szerveroldali ellenőrzés | Supabase Auth, has_permission(), Next.js szerveroldali őr                                                      | /apps/web/lib/auth, /database/policies/rbac                                                                                                              | user_roles, permissions, role_permissions                                                                                     | Jogosulatlan írás elutasítva API- és DB-szinten; worker nem hívhat emberi függvényt                               | F9                                                   |
| P1-05 Audit-alap               | Csak hozzáfűzhető, hash-láncolt audit                      | Audit-író függvény, lánc-trigger, ellenőrző eljárás, export                                                    | /database/migrations/*audit*, /services/shared/audit                                                                                                     | audit_log                                                                                                                     | UPDATE / DELETE elutasítva admin alkalmazásszerepkörrel is; manipuláció detektálható                              | F7                                                   |
| P1-06 Forrásregiszter          | Források létrehozása, szerkesztése, aktiválása             | Forráskezelő UI, szerveroldali műveletek                                                                       | /apps/web/app/sources/\*                                                                                                                                 | sources (DS 7 + retention_mode, gyűjtési konfiguráció, feltételek)                                                            | Csak jogosult módosíthat; SOURCE\_\* események auditálva; gyűjtési mód nélkül nincs gyűjtés                       | F1, F2                                               |
| P1-07 Jobok és ütemezés        | Idempotens jobfeldolgozás                                  | pg_cron enqueue, Python worker-loop, retry / backoff                                                           | /services/scheduler, /services/shared/jobs                                                                                                               | processing_jobs (egyedi idempotencia-kulcs), system_errors                                                                    | Retry nem duplikál; tartós hibánál figyelmeztetés                                                                 | F5, F6 alapja                                        |
| P1-08 Gyűjtési keret           | Adapteralapú gyűjtés                                       | RSS / Atom, API, HTTP adapterek; rate limit; nincs megkerülés                                                  | /services/collector/\*                                                                                                                                   | collection_runs                                                                                                               | Forráshiba → SOURCE_UNAVAILABLE, a pipeline nem áll le; futás-statisztikák                                        | F3, F6                                               |
| P1-09 Cikk és snapshot         | Provenance-teljes, változtathatatlan snapshotok            | Kanonikus URL, content-addressed tárolás, determinisztikus tiszta szöveg, nyelvfelismerés, időmezők basis-szal | /services/collector/snapshot, /packages/schemas/article                                                                                                  | articles, article_snapshots, text_representations                                                                             | Azonos tartalom nem duplikál; módosult tartalom új snapshot; offset-stabilitás; nem talált dátum → DATE_UNCERTAIN | F4, F5, F10                                          |
| P1-10 Model-run és prompt-alap | Nyomonkövetés élő LLM-pipeline nélkül                      | Provider-interfész fake adapterrel; promptregisztráció Gitből hash-sel                                         | /packages/prompts, /services/ai-orchestrator/provider                                                                                                    | prompt_versions, model_runs, human_reviews (alap)                                                                             | Fake futás teljes rekordot ír; promptaktiválás auditált; sémahibás kimenet nem kerül be                           | G-15 alap                                            |
| P1-11 Biztonság és elfogadás   | F1–F10 automatizált ellenőrzése                            | Integrációs, RLS- és jogosultsági negatív tesztek; backup és restore-próba DEV-ben                             | /tests/integration, /tests/security                                                                                                                      | –                                                                                                                             | Teljes F1–F10 mátrix                                                                                              | Control Gate 1 jelentés a Handoff 52. pontja szerint |

## M–N. Ellentmondásvizsgálat és blokkoló kérdések

**NO MATERIAL SPECIFICATION CONTRADICTION IDENTIFIED.** Két értelmezést
rögzítek, ezek nem ellentmondások:

- **Esemény-létrehozás:** az MS 43 az „initial event clustering”
  automatizálását engedi, a Prompt Pack az emberi EVENT_ACTION-t
  elkülöníti. Konform megoldás: az M05 javaslata determinisztikusan
  CANDIDATE eseményt vagy AI-eredetű verziót hoz létre; a CANDIDATE
  előléptetése és a MERGE, SPLIT, SUPERSEDE emberi döntés (K-10).

- **Megőrzés és grounding:** a DS 10 metadata-only tárolást enged, a
  v1.2.2 viszont a span snapshoton belüli feloldását követeli.
  Következmény: tartalom-megőrzés nélküli forrás lényeges claimet csak
  engedélyezett szövegrészlettel adhat (K-04).

**Blokkoló kérdések: nincs.** Minden nyitott pont biztonságos
alapértelmezéssel indítható vagy későbbi fázisban dönthető (K-01–K-13).
A K-05 forráslistára a Phase 1 lezárásához lesz szükség, a megkezdéséhez
nem.

**CONTROL GATE 0 STATUS: READY FOR PRODUCT OWNER REVIEW** — a Phase 1
csak explicit Product Owner jóváhagyás után kezdődhet.
