# P7-BM-02 — az alapverzió emberi ellenőrzése (értékelői jóváhagyás)

> **LEZÁRVA (2026-10-25):** a PO a lenti javaslat helyett saját, végleges alapverziót hagyott jóvá
> (`docs/specs/PO_Decision_2026-10-25_P7-BM-02_Clean_Baseline.md`, SPEC_INDEX 29). Az érvényes alap szó szerint az ott
> rögzített szöveg (`tests/pilot/bm02_fixture.py`). Az alábbi tartalom a **felváltott javaslat**, csak előzményként marad meg.

A P7-BM-02 téves-riasztási mérése csak akkor érvényes, ha az alapverzió ténylegesen hibamentes. Ezt **ember**
(a PO, értékelőként) erősíti meg, nem a modell. Az alábbi szöveg pontosan az, amit a benchmark minden „tiszta” esete
(BM02-Q01, -Q02 parafrázis, -Q24) a modellnek QA-ra ad; a 15 seedelt eset ennek egy-egy szándékos rontása.
Forrás: `tests/pilot/bm02_fixture.py`. Szintetikus anyag ('Northland'), nem valós esemény.

## Forrás-claimek (a nyilvános forrásszöveg szó szerint)

| Claim | Forrásszöveg | Bizonyító szövegrész (span) | Attribúció |
| --- | --- | --- | --- |
| A | „The Northland air force said 4 tanker aircraft arrived at Fort Aster.” | „4 tanker aircraft arrived at Fort Aster” | the Northland air force |
| D | „A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster.” | „denied that any tanker aircraft arrived at Fort Aster” | a Northland defence ministry spokesman |

Esemény: „Reported tanker arrival at Fort Aster” — A és D, D szerepe: CONTRADICTS (cáfolja A-t).

## Jóváhagyott értékelés (M07 → M08 → emberi jóváhagyás, végső bizonyosság: LOW)

| Azonosító | Típus | Szöveg | Bizonyíték |
| --- | --- | --- | --- |
| AS1 | KNOWN_FACT (attribúció kötelező) | „The Northland air force reported that 4 tanker aircraft arrived at Fort Aster.” | támogatja: A; cáfolja: D |
| AS2 | ALTERNATIVE_EXPLANATION | „A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster.” | támogatja: D |
| AS3 | ANALYTIC_JUDGMENT, valószínűség: ROUGHLY_EVEN_CHANCE | „There is a roughly even chance that tanker aircraft arrived at Fort Aster; the two official Northland statements conflict.” | támogatja: A és D; premisszák: AS1, AS2 |
| AS4 | INFORMATION_GAP | „It is unknown whether any aircraft arrived and, if so, how long they would remain.” | — |

Bizonyosság-indoklás: „Two conflicting official statements from the same government; no independent confirmation.”
Valószínűség-indoklás: „One official statement reports the arrival and another official statement denies it; neither is
independently confirmed.”

## A report (M09, szó szerinti átvétel) — egy kulcsítélet-tétel

| Report-állítás | Szerep | Szöveg |
| --- | --- | --- |
| RS1 ← AS1 | CAVEAT (vitatott) | „The Northland air force reported that 4 tanker aircraft arrived at Fort Aster.” |
| RS2 ← AS2 | CAVEAT | „A Northland defence ministry spokesman denied that any tanker aircraft arrived at Fort Aster.” |
| RS3 ← AS3 | KEY_JUDGMENT, ROUGHLY_EVEN_CHANCE, LOW | „There is a roughly even chance that tanker aircraft arrived at Fort Aster; the two official Northland statements conflict.” |
| RS4 ← AS4 | CAVEAT | „It is unknown whether any aircraft arrived and, if so, how long they would remain.” |

Megjegyzés: a lezárt Phase 5 szabály szerint vitatott ítélet nem lehet kulcsítélet, ezért a konfliktust az RS3 saját
szövege és az RS1 / RS2 caveat hordozza (nem a `contested` jelző).

## Kérdés az értékelőhöz

Megerősíti-e, hogy az RS1–RS4 **hibamentes**: minden állítás következik a hivatkozott claimekből, az attribúció pontos, az
ellentmondás megmarad, nincs alá nem támasztott tény, és a bizonyosság / valószínűség nem erősebb a bizonyítéknál?

- Ha igen: a P7-BM-02 valós futásának téves-riasztási értéke a 19. kritérium bizonyítéka lehet.
- Ha nem: jelölje a hibás mondatot; javítom az alapot, és újra ellenőrzésre hozom.

## Ellenőrzés a tesztdublőrrel (regresszió, nem minőségmérés)

A harnessben a determinisztikus M10-D és a szabályalapú M10-S tesztdublőr a 3 tiszta esetet PASS-ra, a többit a várt
állapotra értékelte; a D réteg mind a 13 címkét megtalálta, a tiszta eseteken 0 téves jelzéssel.
