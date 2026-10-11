# LFHÉ — CG1-08A FINAL PATCH REPORT

**Dátum:** 2026-10-11
**Hatókör:** kizárólag a CG1-08A javítás, a hozzá tartozó tesztek és dokumentáció. A CG1-01…07 változatlan. Phase 2 nem kezdődött el.

## STATUS

**RESOLVED.** Ezzel a CG1-08 teljes egészében lezárul.

## FILES CHANGED

- **`database/migrations/20261011001400_url_canonicalisation_and_source_urls.sql`** (új)
- **`services/shared/lfhe_shared/credentials.py`**
  - `url_inspection_form`
  - kanonizáló `url_credential_problems`
  - `is_canonical_http_url`
  - `source_config_problems`
- **`services/collector/lfhe_collector/adapters.py`**: a `build_adapter` ugyanazt a forrás-URL szabályt alkalmazza, és a hibaüzenetekben nem jelennek meg értékek.
- **`apps/web/lib/credentials.ts`**: `urlInspectionForm`, kanonizáló `urlCredentialProblems`
- **Tesztek:**
  - `tests/security/test_url_canonicalisation.py` (új)
  - `tests/fixtures/url_canonicalisation_cases.json` (új, közös paritás-fixture)
  - `apps/web/tests/sources.test.ts`
  - `tests/security/test_credential_keys.py`, `test_credential_urls.py`: a backstop-tesztek most mindkét guard triggert letiltják; egy elvárás frissítve a szándékolt viselkedésváltozás miatt.
- **`scripts/supabase_dev_smoke.py`**: új CG1-08A ellenőrzés
- **Dokumentáció:** `docs/permission-matrix.md`, `docs/PROJECT_STATUS.md`

## MIGRATION

`20261011001400_url_canonicalisation_and_source_urls.sql`

1. **`lfhe.url_inspection_form`**: azt a formát állítja elő, ahogyan egy URL-parser (WHATWG / Pydantic `HttpUrl`) a szöveget olvassa:
   - a TAB, LF és CR karaktereket mindenhol eltávolítja;
   - az elejéről és a végéről levágja a vezérlő- és szóközkaraktereket (U+0001–U+0020);
   - a `\` karaktert `/`-ként kezeli.
2. **`lfhe.url_credential_problems`**: mostantól ezen a formán ellenőriz.
   - **Userinfo** (felhasználónév/jelszó az URL-ben) ellenőrzése: `scheme://` alakban; a http/https/ws/wss/ftp/file sémáknál tetszőleges számú perjellel (pl. `https:user:pw@host`); valamint `//authority` alakban.
   - **Paraméternevek** ellenőrzése **minden** olyan szövegben, amelyben `?` vagy `#` van, relatív hivatkozásokban is.
3. **`lfhe.source_config_problems` + `sources_validate_config` trigger** (`SOURCE_CONFIG_INVALID`) és **CHECK backstop**. Az ismert URL-mezők:
   - `feed_url` (RSS_ATOM), `sitemap_url` (STRUCTURED_FEED), `endpoint` (OFFICIAL_API), `urls[]` (HTTP_FETCH);
   - kötelezők és JSON stringek; az `urls` nem üres tömb;
   - kanonikus abszolút http(s) URL-ek: nincs bennük whitespace, vezérlőkarakter, backslash vagy userinfo;
   - és nincs bennük hitelesítő paraméter.

   Mindez **sor létrehozása, módosítása és bármilyen audit bejegyzés előtt** fut le. A hibaüzenet csak mezőútvonalat és kódot tartalmaz, értéket nem.
4. A meglévő URL-credential CHECK constraint-eket a szigorított szabállyal **újravalidáltam**. Ez DEV-en is hiba nélkül lefutott.

## TESTS ADDED

`tests/security/test_url_canonicalisation.py` (26 teszt), valamint 1 új vitest teszt a webes paritásra. A PO által kért esetek lefedettsége:

| # | Eset | Lefedés |
|---|---|---|
| A | szóköz az elején + `?api_key=` | ✔ |
| B | szóköz a végén + `?token=` | ✔ |
| C | TAB/újsor az URL körül + userinfo | ✔ (plusz TAB a paraméternévben is) |
| D | relatív `feed_url` + `?api_key=` | ✔ |
| E | relatív `sitemap_url` + `?token=` | ✔ |
| F | relatív OFFICIAL_API `endpoint` + `?access_token=` | ✔ |
| G | relatív URL az HTTP_FETCH `urls[]`-ben | ✔ |
| H | tiszta abszolút URL-ek ártalmatlan query-vel: elfogadva (4 módszer) | ✔ |
| I | közvetlen RPC (create, update, collection_method-váltás) | ✔ |
| J | a szintetikus titok nincs a `sources` táblában, az `audit_log`-ban és a hibában; nem jön létre se sor, se audit bejegyzés | ✔ |
| K | PostgreSQL = Python = TypeScript, közös fixture alapján (17 eset, a kanonizáló formával együtt) | ✔ |

További esetek:
- séma perjel nélkül (`https:user:pw@…`);
- backslash-változat;
- protokoll-relatív `//user:pw@…`;
- szerkezetileg hibás mezők: hiányzik, nem string, nem abszolút, `ftp:`, üres vagy nem tömb `urls`.

## TESTS ACTUALLY RUN

- Teljes Python csomag helyben, a lockból épített Python 3.13 környezetben is, és a CI-ben.
- Web: `tsc`, vitest.
- gitleaks a teljes git-előzményen.
- DEV Supabase: migráció és smoke teszt.

## RESULTS

Mind PASS.

## UPDATED TEST TOTAL

**Python: 234/234.** Megoszlás: unit 74, integration 97, security 53, acceptance 10. A CG1-08 után 208 volt, tehát +26.
**Web:** vitest 15/15, `tsc` hibátlan.

## GITHUB CI STATUS

**PASS** a `4f707cb` commitra (run 38152191536): secret-scan (gitleaks), python-tests és web is sikeres. A jelentés-commit CI-eredménye a delivery reportban szerepel.

## DEV SUPABASE MIGRATION/SMOKE STATUS

**PASS** (2026-10-11 17:51, a PO gépéről):
- 15/15 migráció. A `20261011001400_…` hiba nélkül lefutott, a meglévő DEV-sorok megfeleltek az újravalidált constraint-eknek.
- **Smoke 18/18 PASS**, köztük az új `CG1-08A: whitespace/relative credential URL rejected via RPC, not echoed, not audited` (HTTP 400).
- Az audit hash-lánc 15 bejegyzéssel ellenőrizve. A pg_cron sikeresen futott 15:50 UTC-kor.

## REMAINING LIMITATIONS

- **Szándékos viselkedésváltozás:** paraméterneveket bármely `?`/`#`-et tartalmazó konfigurációs szövegben vizsgálok, nem csak URL-ekben. Ritka esetben ez hamis pozitívot adhat, például egy `?token=` részletet tartalmazó szabad szöveges megjegyzésre. Ez szándékosan a szigorúbb oldalra téved.
- **Csak ASCII-szóköz:** a kanonikus URL-szabály az ASCII whitespace- és vezérlőkaraktereket tiltja. Unicode-szóközt (pl. U+00A0) a három implementáció egységesen nem tilt.
- **Változatlanul nyitott:**
  - L-14: szabad szöveges értékben vagy URL-útvonalszegmensben elhelyezett titkot a szabály nem ismer fel;
  - L-13: Phase 2 előtt providerenként engedélyezőlistás modellbeállítás-séma szükséges;
  - ha a tulajdonos letiltja a guard triggereket, a CHECK backstop hiba-részlete visszaidézheti a sort.
- **K-05: OPEN.** A végső Control Gate 1 lezárásához még kell a valós forrásokon történő validálás.

**STOP.**
