-- LFHÉ Phase 4 — CR4-01 resolution: canonical likelihood vocabulary.
-- Source: docs/specs/PO_Decision_2026-10-20_CG4_PreClosure_CR4-01.md (explicit Product Owner
-- decision; NOT recovered from an earlier specification). Closed, ordered set, ranks 1–7.
-- No numeric probability bands, no UNKNOWN term. Forward-only; migrations 2700–3300 unchanged.
-- Existing rules stay authoritative: likelihood ≠ analytic confidence; optional (null when not
-- justified); only on ANALYTIC_JUDGMENT / IMPLICATION; rationale mandatory;
-- final_analytic_confidence HUMAN_ONLY.
INSERT INTO lfhe.likelihood_terms (code, rank, description, spec_source) VALUES
  ('REMOTE_CHANCE',       1, 'Possible, but judged exceptionally unlikely.',                        'PO Decision 2026-10-20 CR4-01'),
  ('HIGHLY_UNLIKELY',     2, 'Judged very unlikely.',                                              'PO Decision 2026-10-20 CR4-01'),
  ('UNLIKELY',            3, 'Judged less likely than not.',                                       'PO Decision 2026-10-20 CR4-01'),
  ('ROUGHLY_EVEN_CHANCE', 4, 'Competing outcomes are judged approximately equally plausible.',     'PO Decision 2026-10-20 CR4-01'),
  ('LIKELY',              5, 'Judged more likely than not.',                                       'PO Decision 2026-10-20 CR4-01'),
  ('HIGHLY_LIKELY',       6, 'Judged very likely.',                                                'PO Decision 2026-10-20 CR4-01'),
  ('ALMOST_CERTAIN',      7, 'Judged overwhelmingly likely.',                                      'PO Decision 2026-10-20 CR4-01');
