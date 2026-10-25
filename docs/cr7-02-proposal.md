# CR7-02 — A modell nem kapja meg a kötelező kimeneti sémát

Állapot: **APPROVED (PO, 2026-10-25, `docs/specs/PO_Decision_2026-10-25_CR7-02.md`, SPEC_INDEX 28) — a `main`-be olvasztva**
(merge `25043c2`; a `cr7-02` ág commitja `30beb54`). Igazolva az ágon: run 40112066517 (M07 → M08 → emberi jóváhagyás → M09 →
M10-D + M10-S valós `claude-sonnet-5-5`-tel, 4 / 4 sémahelyes, 0 javító futás, QA PASS_WITH_WARNINGS). A CR7-02 nem nyitja újra a
CG2-t / Phase 2-t; a CG7 nyitva marad; a 19. kritérium csak a teljes valós P7-BM-01 benchmarkból lehet PASS.

## Érintett lezárt viselkedés (pontosan)

- **Egyetlen** módosított lezárt viselkedés: `services/ai-orchestrator/lfhe_orchestrator/providers.py` → `render_messages`
  (Phase 2, ADR-0004), vagyis a providernek küldött felhasználói üzenet összeállítása.
  - Előtte: `task.md` + untrusted-data figyelmeztetés + `<lfhe_task_envelope>` blokk.
  - Utána: `task.md` + **OUTPUT CONTRACT utasítás** + **`<lfhe_output_schema>` blokk** (a prompt-verzió regisztrált,
    hash-ellenőrzött `output_schema.json`-ja, kanonikus JSON, `<` `>` `&` escape-elve) + untrusted-data figyelmeztetés +
    `<lfhe_task_envelope>` blokk (változatlan, továbbra is utolsó).
- Változatlan: a `system.md` (system prompt), a prompt-csomagok fájljai, verzióazonosítói és hashei (prompt lock OK), az
  envelope és annak escape-elése, a sémavalidáció, a javító-futás szabálya, az ingestion, a QA, az emberi hatáskörök, a
  provenancia és a kiadás. A `FakeProvider` / tesztdublőrök viselkedése nem változott.
- Új teszt: `tests/unit/test_cr7_02_output_contract.py`.
- Merge utáni ellenőrzés (2026-10-25): teljes készlet 581 passed + 1 skipped (valós-provider teszt, kulcs nélkül), web 44 / 44, TypeScript és build PASS, prompt lock OK, secret scan és gitleaks tiszta.

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
