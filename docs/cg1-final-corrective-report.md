# LFHÉ — CG1 FINAL CORRECTIVE REPORT

**Phase / gate:** Phase 1 / Control Gate 1. A Control Gate 1 még **nincs jóváhagyva**.
**Dátum:** 2026-10-11
**Hatókör:** csak a CG1-07 és a CG1-08 javítás, valamint a kiszállítási metaadatok (CG1-PKG-01).
- A CG1-01…06 nem lett újratervezve.
- Phase 2 nem kezdődött el; M02/M03 nincs.

A tesztszámok kumulatívak. „Lefuttatva” csak ténylegesen végrehajtott futást jelent.

---

## CG1-07 — robots.txt fail-closed működés, nem mérgeződő cache

**STATUS:** RESOLVED

**FILES CHANGED:**
- `services/collector/lfhe_collector/http.py`
  - `_robots_state`, `_fetch_robots`, `_robots_allows`;
  - új paraméterek: `robots_cache_ttl` (24 h) és `robots_failure_ttl` (60 s).
- `docs/collection-semantics.md` (robots.txt fejezet)

**MIGRATIONS:** nincs.

**Szemantika:**

| robots.txt válasz | Eredmény | A céldokumentumot lekéri? |
| --- | --- | --- |
| 2xx | értelmezi, a szabályok érvényesek | csak ha engedélyezett |
| 401 / 403 | mindent tilt (`ROBOTS_DISALLOWED`) | nem |
| 404 / 410 | nincs szabály, minden engedélyezett (RFC 9309) | igen |
| egyéb 4xx | mindent tilt (konzervatív, dokumentált eltérés) | nem |
| 429 / 5xx / hálózati hiba / időtúllépés | `SOURCE_UNAVAILABLE`, újrapróbálható | **nem** |
| 3xx | legfeljebb 5 lépést követ, mindegyiket ugyanazzal a cél- (SSRF-) ellenőrzéssel | csak végső válasz után |
| Location nélküli 3xx, hurok, >5 lépés | `SOURCE_UNAVAILABLE`, soha nem „minden engedélyezett” | nem |
| redirect tiltott sémára vagy privát címre | `DESTINATION_REFUSED` | nem |
| `max_bytes`-nál nagyobb törzs | mindent tilt | nem |

**Cache-elés:**
- A sikeres szabályokat 24 óráig tárolja.
- Az átmeneti hibát legfeljebb 60 másodpercig jegyzi meg. Ez rövidebb, mint a job-backoff minimuma (1 perc), így a következő kísérlet **ugyanazzal a klienssel** is helyreáll.

**TESTS ADDED:** `tests/unit/test_robots.py` (22 teszt), `tests/integration/test_robots_collection.py` (1 teszt). A tesztek a PO által kért 10 esetet így fedik le:
1. 200 Allow
2. 200 Disallow
3. 401
4. 403
5. 404 (és 410)
6. 429
7. 500, 502, 503
8. hálózati hiba, majd helyreállás ugyanazzal a klienssel
9. redirect: érvényes, Location nélküli, hurok, tiltott séma, privát cím
10. minden tiltó vagy átmenetileg elérhetetlen esetben ellenőrizve, hogy a cikk URL-jét **soha nem kéri le**

Plusz esetek:
- egyéb 4xx (400, 405, 451);
- a hiba-cache TTL-je;
- a sikeres szabály cache-elése;
- túl nagy robots.txt;
- kollektor-szintű teszt: robots 503 esetén a futás `SOURCE_UNAVAILABLE` és újrapróbálható, a cikket nem kéri le; a következő kísérlet ugyanazzal a klienssel `SUCCESS`.

**TESTS ACTUALLY RUN:** a teljes Python csomag, helyben és a CI-ben.

**RESULTS:** mind PASS.

**REMAINING LIMITATIONS:**
- Az „egyéb 4xx → mindent tilt” szabály szigorúbb az RFC 9309-nél. Dokumentált, konzervatív döntés.
- A cache folyamatonként él. Phase 1-ben egy collector fut.

## CG1-08 — Hitelesítő adat URL-értékekben

**STATUS:** RESOLVED

**FILES CHANGED:**
- `services/shared/lfhe_shared/credentials.py`: `url_credential_problems`, `credential_url_paths`
- `services/collector/lfhe_collector/adapters.py`: Pydantic-tükör; a hibák nem idézik vissza a bemeneti értékeket
- `apps/web/lib/credentials.ts`, `apps/web/lib/sources.ts`: TypeScript-tükör
- `scripts/supabase_dev_smoke.py`: új CG1-08 ellenőrzés
- `docs/permission-matrix.md`, `docs/runbooks/dev-supabase-smoke.md`, `docs/PROJECT_STATUS.md`

**MIGRATIONS:** `20261011001300_credential_urls.sql`
- `lfhe.percent_decode`, `lfhe.url_credential_problems`, `lfhe.credential_url_paths`.
- Minden abszolút URL-szöveget ellenőriz, tetszőleges mélységben.
- Elutasít:
  - URL-ben lévő felhasználónevet/jelszót (`@` vagy `%40` az authority részben);
  - olyan query- vagy fragment-paramétert, amelynek dekódolt **neve** a CG1-03 szótára szerint hitelesítő adatra utal (token, api_key, apikey, key, secret, password, auth, authorization, credential, bearer, access_token, client_secret, X-Api-Key stb.).
- A BEFORE trigger kódja `CREDENTIAL_URL_REJECTED`. A hibaüzenet csak a JSON-útvonalat és a paraméter **nevét** tartalmazza, az értéket soha. Mögötte CHECK backstop áll.
- Hatókör: `sources.collection_config` (feed_url, sitemap_url, endpoint, urls[], és bármely más URL), `model_configurations.settings`, `processing_jobs.payload`.

**TESTS ADDED:** `tests/security/test_credential_urls.py` (11 teszt; a 7 elutasítási eset paraméterezett), valamint 2 új vitest teszt a webes rész tükrére:
1. RSS URL felhasználónévvel és jelszóval;
2. RSS `?api_key=`;
3. sitemap `?token=`;
4. OFFICIAL_API endpoint felhasználónévvel és jelszóval;
5. HTTP_FETCH `urls[]`-ben `?secret=`;
6. fragment `#access_token=`;
7. kódolt név: `API%5FKEY`;
8. ártalmatlan query-k elfogadva;
9. közvetlen RPC create és update;
10. tulajdonosi (owner) UPDATE;
11. CHECK backstop letiltott triggerrel;
12. modellbeállítás és job payload;
13. Python és DB paritás.

Minden elutasított esetben ellenőrizve: nincs új forrássor, és a szintetikus titok nem szerepel a `sources` táblában, az audit logban és a visszaadott hibában sem.

**TESTS ACTUALLY RUN:**
- Python teljes csomag, helyben és a CI-ben.
- vitest 14/14, `tsc`.
- DEV Supabase: a migráció lefutott, és a smoke teszt új CG1-08 ellenőrzése is PASS (HTTP 400; a titok nincs a válaszban, és nincs az auditban).

**RESULTS:** mind PASS.

**REMAINING LIMITATIONS:**
- **L-14:** szabad szöveges értékben, ártalmatlan kulcs alatt, vagy URL útvonal-szegmensben elhelyezett titkot nem ismer fel.
- Ha a trigger le van tiltva, a CHECK backstop hibaüzenet-részlete a sort visszaidézheti. A triggert csak tulajdonos tilthatja le.
- Ha direkt SQL-ben, literálként küldenek be titkot, az a PostgreSQL szervernaplóba kerülhet. A PostgREST paraméterezett hívásait ez nem érinti.
- **L-13 (Phase 2 előfeltétel):** a valódi providerek bevezetése előtt kell egy providerenkénti, engedélyezőlistás, titok-mentes beállítás-séma; a provider kulcsok csak jóváhagyott titokkezelőből jöhetnek.

## CG1-PKG-01 — Kiszállítás nyomonkövethetősége

**STATUS:** RESOLVED
- Az archívum mellé **külön, az archívumon kívüli** `DELIVERY-REPORT.txt` készül: GIT_COMMIT, GIT_STATUS, UNTRACKED_FILES, ARCHIVE_FILENAME, ARCHIVE_SHA256.
- Az archívum `git archive` kimenete, determinisztikus `gzip -n` tömörítéssel. Így ugyanabból a commitból bárki ellenőrizheti:

```
git archive --format=tar --prefix=lfhe/ <commit> | gzip -n -9 | sha256sum
```

---

## UPDATED TEST TOTAL

- **Python: 208 teszt, mind sikeres.** Megoszlás: unit 74, integration 97, security 27, acceptance 10. A CG1 javító kör végén 174 volt, tehát +34.
  - Lefutott a lockból épített Python 3.13 környezetben is.
- **Web:** vitest 14/14, `tsc` hibátlan.

## GITHUB CI STATUS

- **PASS** a `cfaa2fc` commitra (run 38149286557): secret-scan, python-tests és web is `success`.
- Előzmény, őszintén: a `f3be020` commit CI-futása (38149203508) **failure** lett. A secret-scan lépés gitleaks-szabálya hamis pozitívként jelezte a CG1-08 teszt szintetikus konstansát.
  - Ezt `.gitleaksignore` fingerprint-bejegyzéssel és inline `gitleaks:allow` jelöléssel kezeltem. Az előzményt nem írtam át.
  - A python-tests és a web job már abban a futásban is sikeres volt.
- A jelentés-commit CI-eredménye a delivery reportban szerepel.

## GITLEAKS STATUS

- **8.24.3, helyben, `gitleaks git` a teljes előzményen: nincs szivárgás.** Egyetlen dokumentált, ellenőrzött hamis pozitívot zártam ki fingerprinttel.
- A CI-ben is lefutott: `success` (`cfaa2fc`).
- A munkakönyvtár (`dir` mód) 6 találata csak a nem verziókezelt `.next/` build-kimenetben van. Ezek a Next.js által generált preview-kulcsok, nincsenek az archívumban.

## DEV SUPABASE MIGRATION/SMOKE STATUS

**PASS** (2026-10-11 17:21, a PO futtatta a Windows gépén):
- **14/14 migráció.** A `20261011001300_credential_urls.sql` hiba nélkül lefutott.
- **Smoke: 17/17 PASS**: Auth, RLS, HUMAN_ONLY (anon / viewer / service_role), CG1-03, **CG1-08**, a forrás életciklusa, audit és hash-lánc (11 bejegyzés), pg_cron ütemezés és sikeres futás (15:20 UTC).

**Biztonsági megjegyzés:** a beállítás közben a DEV adatbázis-jelszó egyszer bekerült a beszélgetésbe. Javasoltam a jelszó cseréjét. A csere megtörténtét a PO-nak kell megerősítenie. A DEV adatbázis csak szintetikus tesztadatokat tartalmaz.

## GIT_COMMIT / GIT_STATUS / UNTRACKED_FILES / ARCHIVE_FILENAME / ARCHIVE_SHA256

Lásd a külön `DELIVERY-REPORT.txt`-t. Ez a jelentés az archívumon belül van, ezért nem hordozhatja a saját archívumának hash-ét.

## SPECIFICATION DEVIATIONS

| ID | Leírás |
| --- | --- |
| D-10 | robots.txt: a 404/410-en kívüli egyéb 4xx válaszra mindent tilt; az RFC 9309 ilyenkor engedne. Konzervatív, dokumentált döntés. |
| D-11 | Új hibakód: `CREDENTIAL_URL_REJECTED`. Additív. |

## CHANGE REQUESTS

Nincs.

## K-05

**OPEN.** Nem találtam ki forrásokat.

A végső Control Gate 1 lezárásához még hátra van a valós forrásokon történő validálás. Ennek ki kell terjednie:
- a letöltésre;
- a publikációs és nyilvános elérhetőségi metaadatokra;
- az eredeti nyelvű snapshotra;
- a revízió- és duplikátumkezelésre;
- a robots- és hozzáférés-kezelésre;
- a provenance megőrzésére;
- a gyűjtési futások és hibák naplózására.

**STOP.**
