# CR7-01 — Modellek, amelyek nem fogadják el a `temperature` paramétert

Állapot: **IMPLEMENTED (B változat) — PO-utasítás alapján; a valós futás igazolása a PO-ra vár.**

PO-utasítás (2026-10-24 16:51, szó szerint): „Ez sem ment jobban, most már találj erre egy olyan megoldást, amely biztosan
működtetni fogja!!!!” — a Haiku 5.5 preflight ugyanazzal a hibával utasítva el (request_id `req_011CgMFRkDWFB1626DoEayML`).
Mivel a Console-ban elérhető összes modell (Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5) ugyanabba a generációba tartozik,
az A változat nem járható; az utasítást a **B változat jóváhagyásaként** értelmeztem.

Megvalósítás: migráció `20261011004200_cr7_01_provider_fixed_sampling.sql` (új, előrefelé; a korábbiak változatlanok) —
új explicit anthropic-beállítás `provider_fixed_sampling: true` (csak `true`; `temperature` / `top_p` mellett tilos; csak
anthropic). Python-tükör `model_settings.py`; `low_variance_problem` ezt a jelölőt elfogadja; az `AnthropicProvider` ilyenkor
nem küld mintavételi paramétert, egyébként a kérés változatlan. A beállítás a konfiguráció-hash része, így minden model_run-on
látszik. Pilot-eszközök: workflow `sampling` bemenet (alapértelmezés `provider_fixed`), preflight azonos kérésalakkal.
Tesztek: `tests/unit/test_cr7_01_sampling.py`, `tests/integration/test_model_settings.py` (SQL / Python paritás, regisztráció),
`tests/pilot/test_p7_trial_flow.py` (a kérésben nincs `temperature`); DEV smoke +1 ellenőrzés.

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
