# CR7-01 (JAVASLAT) — Modellek, amelyek nem fogadják el a `temperature` paramétert

Állapot: **PROPOSED — PO-döntésre vár.** Az érintett pilot-út (valós provider `claude-sonnet-5-5`-tel) a döntésig áll
(PO-felhatalmazás „Closed phase protection”: record → classify → propose CR → STOP → PO decision). Kód nem változott.

## Megállapítás (2026-10-24)

- 1. kísérlet (run 40102872833): minden hívás HTTP 400 `PROVIDER_REQUEST_REJECTED`.
- Preflight (2. futás): `HTTP 400 type=invalid_request_error message='`temperature` is deprecated for this model.'`
  (request_id `req_011CgMEu1j2wTKTuqXkwL11V`, modell `claude-sonnet-5-5`).
- Osztály: **CONFIGURATION_PROBLEM / provider-kompatibilitás**, nem modellminőség és nem LFHÉ-szoftverhiba.

## Miért érinti a lezárt szemantikát

A Phase 2 / 4 / 6 baseline „low-variance model configuration”-t ír elő (Phase 2 Addendum 452. sor, Phase 4 837., Phase 6
627.). A jóváhagyott implementáció ezt **explicit `temperature ≤ 0,2`** beállítással teljesíti
(`lfhe_orchestrator.model_settings.low_variance_problem`, M02–M10), és az `AnthropicProvider` mindig elküldi a
`temperature` mezőt. Olyan modellel, amely a `temperature`-t nem fogadja el, a lezárt szabály szerint egyetlen modul sem
futtatható. Ennek feloldása a lezárt Phase 2–6 viselkedés módosítása, ezért PO-döntés kell.

## Döntési lehetőségek

| Opció | Mit jelent | Lezárt szemantika | Pilot-hatás |
| --- | --- | --- | --- |
| **A — régebbi modell, kódváltozás nélkül** | A pilot olyan Anthropic-modellel fut, amely még elfogadja a `temperature` paramétert (a preflight másodpercek alatt ellenőrzi). | változatlan | azonnal folytatható; a pilot nem a legújabb modellt méri (korlát a findingsben) |
| **B — „provider által vezérelt mintavétel” CR** | Új, explicit modellkonfigurációs jelölés (pl. `"sampling": "PROVIDER_FIXED"`) a `temperature` helyett azoknál a modelleknél, ahol a provider elavultnak jelöli; az adapter ilyenkor nem küld `temperature`-t; a low-variance követelmény ilyenkor a rögzített provider-viselkedéssel + séma-validációval + változatlan QA-val teljesül, és ez minden model_run-ban látható. Új előrefelé migráció a beállítás-allowlisthez; tesztek. | **módosul** (Phase 2–6 low-variance értelmezés) | a pilot a választott legújabb modellel futhat; a variancia-kontroll gyengébb, ezt a findings méri |
| **C — mindkettő** | A most futtatható A-val, a B-t külön CR-ként | A: változatlan; B: módosul | a legkevesebb várakozás |

**Javaslatom: A most** (gyors, nincs zárt változás), **B csak akkor**, ha a PO a legújabb modell mérését a pilot céljához
szükségesnek tartja.
