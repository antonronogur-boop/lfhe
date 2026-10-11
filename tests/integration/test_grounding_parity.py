"""P2-04 — QA-D18: the Python mirror and the authoritative database check agree."""
import pytest

from claims_support import make_text_snapshot
from lfhe_shared.grounding import ground

pytestmark = pytest.mark.db

TEXT = "🛩️ Міністерство оборони повідомило, що бригада отримала 12 дронів. Ще 3 радари очікуються."
EXACT = "бригада отримала 12 дронів"
S = TEXT.index(EXACT)

CASES = [
    ({"exact_text": EXACT, "start": S, "end": S + len(EXACT), "language": "uk"}, EXACT),
    ({"exact_text": EXACT, "start": S + 1, "end": S + 1 + len(EXACT), "language": "uk"}, EXACT),
    ({"exact_text": EXACT, "start": S, "end": S + len(EXACT), "language": "en"}, EXACT),
    ({"exact_text": EXACT, "start": S, "end": 10_000, "language": "uk"}, EXACT),
    ({"exact_text": EXACT, "start": S, "end": S, "language": "uk"}, EXACT),
    ({"exact_text": EXACT, "start": S, "end": S + len(EXACT), "language": "uk",
      "locator_type": "CSS_SELECTOR"}, EXACT),
    ({"exact_text": EXACT, "start": S, "end": S + len(EXACT), "language": "uk"}, "отримала 21 дронів"),
    ({"exact_text": "the brigade received 12 drones", "start": S, "end": S + 30, "language": "en"},
     "the brigade received 12 drones"),
]


@pytest.fixture(scope="module")
def snap(pg):
    return make_text_snapshot(pg, TEXT, language="uk")


@pytest.mark.parametrize("span, original", CASES)
def test_python_and_database_grounding_agree(pg, snap, span, original):
    py = ground(TEXT, "uk", span, original)
    with pg.worker() as c:
        db = c.execute("SELECT lfhe.claim_grounding_problems(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS p",
                       (snap["rep_id"], snap["snapshot_id"], snap["article_id"], snap["source_id"], span["language"],
                        span.get("locator_type", "TEXT_REPRESENTATION_CODE_POINTS"), span["start"], span["end"],
                        span["exact_text"], original)).fetchone()["p"]
    assert set(py.problems) == set(db)
