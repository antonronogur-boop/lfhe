# CR7-02 (JAVASLAT) — A modell nem kapja meg a kötelező kimeneti sémát

Állapot: **PROPOSED — PO-döntésre vár.** Megvalósítás előkészítve a `cr7-02` ágon (a `main` változatlan); a PO a
`pilot-real-provider` workflow-t erről az ágról futtathatja a döntés előtt (bizonyíték a döntéshez).

## Megállapítás (2026-10-24, run 40111028306, `claude-sonnet-5-5`, `provider_fixed_sampling`)

A sémahiba-diagnosztika szerint a valós modell érdemi, de **kitalált szerkezetű** JSON-t ad:

- 1. M07 futás: a mezők a gyökérben vannak (`statements`, `event_id`, …); hiányzik a kötelező burok (`status`, `result`,
  `warnings`, `human_review_required`).
- Javító futás: a burok megvan, de `statements` helyett `assessment_statements` kellene; az azonosítók `S1` helyett
  `AS1` mintájúak; az indikátorokban nem engedélyezett mezők.

**Ok:** a jóváhagyott kérés-összeállítás (`render_messages`, Phase 2, ADR-0004) a modellnek a `system.md`-t, a `task.md`-t és
az envelope-ot küldi, de az `output_schema.json`-t **nem**; a séma csak a válasz ellenőrzésére szolgál. A tesztdublőrök a sémát
ismerték, ezért ez eddig nem látszott. Valós modell a pontos mezőneveket és azonosító-mintákat nem tudhatja → minden modul
(M02–M10) kimenete sémahibás lesz. Osztály: **SOFTWARE_DEFECT a lezárt Phase 2 kérés-összeállításban** (a szemantikát nem
érinti, de lezárt viselkedés), ezért PO-döntés kell.

## Javasolt javítás (a `cr7-02` ágon kész)

- A felhasználói üzenetben a `task.md` után egy **OUTPUT CONTRACT** utasítás és a prompt-verzió regisztrált, hash-ellenőrzött
  `output_schema.json`-ja (`<lfhe_output_schema>` blokk, kanonikus JSON, az envelope-hoz hasonlóan escape-elve), **az
  untrusted-data figyelmeztetés és az envelope előtt**.
- A prompt-csomagok, a prompt-hashek, a prompt lock, a sémavalidáció, az ingestion, a QA és az emberi döntések változatlanok;
  a kérés-hash (`rendered_request_sha256`) a model_run-ban továbbra is rögzül.
- Tesztek: `tests/unit/test_cr7_02_output_contract.py` (mind a 9 modulnál a pontos séma a kérésben, a megfelelő sorrendben;
  az adat nem nyithat / zárhat séma-blokkot); a teljes regresszió.

## Kockázat / alternatíva

- A séma több ezer tokennel növeli a bemenetet (M09 ~24 kB séma) → költség és latencia nő; a pilot ezt méri.
- Alternatíva: a provider „structured output” funkciója — provider-specifikus, a 9 séma kompatibilitása nem igazolt; nem javaslom
  elsőként.
