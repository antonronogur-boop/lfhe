"""QA-S18 foundation — normalisation fidelity against the ORIGINAL-language span.

Two layers, both conservative (they can only ADD review flags):

1. The model's own normalisation_check (M02 output): every dimension reported
   CHANGED, a translation_material_mismatch or a source-language
   interpretation problem becomes a review flag.
2. Deterministic checks of claim_text_normalised (English) against the
   original-language evidence span:
     * quantities — every digit-number in the span must appear in the
       normalised text, and no digit-number may appear that the span lacks;
     * negation, uncertainty/modality, attribution/reporting language and
       conditionality — if the span contains a marker of the dimension (closed
       per-language lexicons below) the normalised text must contain an
       English marker of the same dimension; negation introduced by the
       normalisation is a material mismatch as well.
   Lexicons exist for en, uk, pl, hu, ru, de, fr; for any other language only
   the quantity check runs and a warning says so (the model self-check and
   human review remain).

Every flag forces human_review_required (enforced again by the database).
These checks are a safety net, not a semantic oracle: passing them does not
prove fidelity; failing them always routes the claim to a human.
"""
from __future__ import annotations

import re
import unicodedata

DIMENSION_FLAGS = {
    "actor": "NORMALISATION_ACTOR_MISMATCH",
    "action": "NORMALISATION_ACTION_MISMATCH",
    "attribution": "NORMALISATION_ATTRIBUTION_LOSS",
    "uncertainty": "NORMALISATION_UNCERTAINTY_LOSS",
    "modality": "NORMALISATION_MODALITY_LOSS",
    "quantity": "NORMALISATION_QUANTITY_MISMATCH",
    "unit": "NORMALISATION_UNIT_MISMATCH",
    "time": "NORMALISATION_TIME_MISMATCH",
    "location": "NORMALISATION_LOCATION_MISMATCH",
    "negation": "NORMALISATION_NEGATION_LOSS",
    "conditionality": "NORMALISATION_CONDITIONALITY_LOSS",
    "source_assessment_language": "NORMALISATION_SOURCE_ASSESSMENT_LOSS",
}

# Closed lexicons (lower-case; single tokens, or phrases matched on token boundaries).
NEGATION = {
    "en": {"not", "no", "never", "none", "nor", "without", "denied", "denies", "deny", "n't", "cannot", "neither"},
    "uk": {"не", "ні", "ніколи", "без", "жоден", "жодних", "заперечив", "заперечує", "немає"},
    "ru": {"не", "нет", "никогда", "без", "ни", "отрицает", "опроверг"},
    "pl": {"nie", "nigdy", "bez", "żaden", "żadnych", "zaprzeczył", "brak"},
    "hu": {"nem", "nincs", "nincsenek", "sem", "soha", "nélkül", "cáfolta", "tagadta"},
    "de": {"nicht", "kein", "keine", "keinen", "nie", "niemals", "ohne", "dementierte"},
    "fr": {"ne", "pas", "jamais", "aucun", "aucune", "sans", "démenti", "nié"},
}
UNCERTAINTY = {
    "en": {"may", "might", "could", "possibly", "possible", "likely", "unlikely", "probably", "reportedly",
           "allegedly", "alleged", "expected", "expects", "plans", "planned", "intends", "would", "unconfirmed",
           "estimated", "approximately", "about", "around", "up to", "suspected", "believed", "appears", "seems"},
    "uk": {"може", "можуть", "міг", "могли", "ймовірно", "можливо", "нібито", "очікується", "планує", "планують",
           "орієнтовно", "приблизно", "близько", "імовірно", "вірогідно", "мабуть"},
    "ru": {"может", "могут", "вероятно", "возможно", "якобы", "ожидается", "планирует", "примерно", "около"},
    "pl": {"może", "mogą", "prawdopodobnie", "możliwe", "rzekomo", "ma zostać", "mają zostać", "planuje",
           "oczekuje się", "około", "szacunkowo", "podobno"},
    "hu": {"lehet", "lehetséges", "valószínűleg", "állítólag", "várhatóan", "tervezi", "tervezik", "mintegy",
           "körülbelül", "nagyjából", "feltehetően"},
    "de": {"könnte", "könnten", "kann", "möglicherweise", "wahrscheinlich", "angeblich", "soll", "sollen",
           "voraussichtlich", "geplant", "etwa", "rund", "ungefähr"},
    "fr": {"pourrait", "pourraient", "peut", "probablement", "possible", "prétendument", "selon", "prévu",
           "devrait", "environ", "quelque"},
}
ATTRIBUTION = {
    "en": {"said", "says", "according to", "reported", "reports", "stated", "states", "announced", "announces",
           "claimed", "claims", "told", "confirmed", "noted", "wrote", "published", "informed", "declared"},
    "uk": {"повідомив", "повідомила", "повідомили", "повідомляє", "за словами", "заявив", "заявила", "заявили",
           "за даними", "інформує", "зазначив", "наголосив", "оголосив", "підтвердив"},
    "ru": {"сообщил", "сообщила", "сообщили", "по словам", "заявил", "заявила", "по данным", "сообщает"},
    "pl": {"poinformował", "poinformowało", "poinformowała", "według", "przekazał", "oświadczył", "ogłosił",
           "podał", "podało", "zapowiedział", "potwierdził"},
    "hu": {"közölte", "szerint", "jelentette", "bejelentette", "tájékoztatott", "nyilatkozta", "megerősítette",
           "írta", "mondta"},
    "de": {"sagte", "teilte mit", "laut", "berichtete", "erklärte", "kündigte an", "bestätigte", "zufolge"},
    "fr": {"a déclaré", "selon", "a annoncé", "a indiqué", "a confirmé", "a affirmé", "d'après"},
}
CONDITIONALITY = {
    "en": {"if", "unless", "provided that", "subject to", "on condition", "conditional", "in case", "should"},
    "uk": {"якщо", "за умови", "у разі", "в разі", "якби"},
    "ru": {"если", "при условии", "в случае"},
    "pl": {"jeśli", "jeżeli", "o ile", "pod warunkiem", "w przypadku"},
    "hu": {"ha", "amennyiben", "feltéve", "abban az esetben"},
    "de": {"wenn", "falls", "sofern", "unter der bedingung"},
    "fr": {"si", "à condition", "sous réserve", "au cas où"},
}
SUPPORTED_LANGUAGES = frozenset(NEGATION)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _base(language: str | None) -> str | None:
    return language.split("-")[0].lower() if language else None


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).casefold().replace("’", "'")
    return re.findall(r"[\w']+", text)


def _has_marker(text: str, lexicon: set[str]) -> bool:
    toks = _tokens(text)
    joined = " " + " ".join(toks) + " "
    for marker in lexicon:
        if " " in marker or "'" in marker and marker != "n't":
            if " " + marker + " " in joined:
                return True
        elif marker == "n't":
            if any(t.endswith("n't") for t in toks):
                return True
        elif marker in toks:
            return True
    return False


def _numbers(text: str) -> set[str]:
    # thousands separators (space / NBSP / thin space between digit groups) are removed first
    compact = re.sub(r"(?<=\d)[\s  ](?=\d{3}\b)", "", text)
    return {n.replace(",", ".") for n in _NUMBER.findall(compact)}


def deterministic_flags(span_text: str, language: str | None, normalised: str) -> tuple[set[str], list[str]]:
    """(flags, warnings) from the deterministic layer."""
    flags: set[str] = set()
    warnings: list[str] = []
    if _numbers(span_text) != _numbers(normalised):
        flags.add("NORMALISATION_QUANTITY_MISMATCH")
    lang = _base(language)
    if lang not in SUPPORTED_LANGUAGES:
        warnings.append(f"QA-S18: no deterministic marker lexicon for language {language!r}; "
                        "only the quantity check ran (model self-check and human review remain)")
        return flags, warnings
    for lexicon, flag in ((NEGATION, "NORMALISATION_NEGATION_LOSS"), (UNCERTAINTY, "NORMALISATION_UNCERTAINTY_LOSS"),
                          (ATTRIBUTION, "NORMALISATION_ATTRIBUTION_LOSS"),
                          (CONDITIONALITY, "NORMALISATION_CONDITIONALITY_LOSS")):
        if _has_marker(span_text, lexicon[lang]) and not _has_marker(normalised, lexicon["en"]):
            flags.add(flag)
    if _has_marker(normalised, NEGATION["en"]) and not _has_marker(span_text, NEGATION[lang]):
        flags.add("TRANSLATION_MATERIAL_MISMATCH")      # negation introduced by the normalisation
    return flags, warnings


def model_flags(check: dict | None) -> set[str]:
    flags: set[str] = set()
    if not isinstance(check, dict):
        return flags
    for dim, flag in DIMENSION_FLAGS.items():
        if check.get(dim) == "CHANGED":
            flags.add(flag)
    if check.get("translation_material_mismatch"):
        flags.add("TRANSLATION_MATERIAL_MISMATCH")
    if check.get("source_language_interpretation_uncertain"):
        flags.add("SOURCE_LANGUAGE_INTERPRETATION_UNCERTAIN")
    return flags


_INSTRUCTION_LIKE = re.compile("|".join([
    r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|earlier|all)\b.{0,20}\b(instructions?|prompts?|rules)\b",
    r"\bnew instructions?\b", r"\byou are now\b", r"(^|[\n.!?\]>]\s*)(system|assistant|developer|user)\s*:", r"</?\s*lfhe_task_envelope",
    r"\b(admin|developer|jailbreak)\s+mode\b", r"\bas an (ai|llm|language model)\b", r"\bprompt injection\b",
    r"ігноруй\w*\s+(усі|всі|попередні)", r"zignoruj\w*\s+(wszystkie|poprzednie)", r"hagyd figyelmen kívül",
    r"игнорируй\w*\s+(все|предыдущие)",
]), re.IGNORECASE | re.DOTALL)


def instruction_like(text: str) -> bool:
    """Source text that addresses an AI / tries to issue instructions (TB-2).
    Such text is still only data; every claim from it goes to a human."""
    return bool(_INSTRUCTION_LIKE.search(unicodedata.normalize("NFKC", text)))


def review_flags(claim: dict, span_text: str, language: str | None, *, high_impact: bool) -> tuple[list[str], list[str]]:
    """All QA-S18 review flags for one grounded candidate, plus warnings."""
    det, warnings = deterministic_flags(span_text, language, claim.get("claim_text_normalised") or "")
    flags = det | model_flags(claim.get("normalisation_check"))
    if claim.get("human_review_required"):
        flags.add("MODEL_REQUESTED_HUMAN_REVIEW")
    if high_impact and claim.get("potential_contradiction"):
        flags.add("HIGH_IMPACT_POTENTIAL_CONTRADICTION")
    return sorted(flags), warnings
