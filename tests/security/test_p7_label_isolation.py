"""Phase 7 Baseline §19, §23, §25 tests 9 / 19 — static half of benchmark-label and pilot-data isolation.

The runtime half (no label content in any rendered provider input; labels invisible to the analyst and
the worker; aggregate-only export) is tests/pilot/test_p7_benchmark.py."""
import json
import re

from conftest import REPO_ROOT

MODEL_PATH = [REPO_ROOT / "packages" / "prompts", REPO_ROOT / "services" / "ai-orchestrator", REPO_ROOT / "services" / "collector",
              REPO_ROOT / "services" / "shared", REPO_ROOT / "tests" / "fixtures"]
PILOT_REF = re.compile(r"pilot_|lfhe_pilot|evaluation/|P7-BM-", re.IGNORECASE)
BENCHES = sorted((REPO_ROOT / "evaluation").glob("p7-bm-*/benchmark.json"))


def _files(root):
    return [p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
            and p.suffix in {".md", ".json", ".py", ".txt", ".sql", ".html", ".yaml", ".yml", ".toml"}]


def test_model_path_never_references_pilot_data_or_benchmark_material():
    hits = [f"{f.relative_to(REPO_ROOT)}:{n}" for root in MODEL_PATH for f in _files(root)
            for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1) if PILOT_REF.search(line)]
    assert hits == []


def test_benchmark_labels_live_only_in_the_evaluator_tree():
    assert len(BENCHES) >= 2
    notes, codes = set(), set()
    for b in BENCHES:
        doc = json.loads(b.read_text())
        assert doc["material"] == "SYNTHETIC"
        notes |= {lb["note"] for c in doc["cases"] for lb in c["labels"]}
        codes |= {c["case_code"].split("-")[0] + "-" for c in doc["cases"]}
    assert notes
    for root in MODEL_PATH + [REPO_ROOT / "services" / "pilot"]:
        for f in _files(root):
            text = f.read_text(errors="replace")
            assert not any(n in text for n in notes), f
            assert not any(c in text for c in codes), f


def test_pilot_package_is_not_imported_by_the_worker_or_collector():
    for root in (REPO_ROOT / "services" / "ai-orchestrator", REPO_ROOT / "services" / "collector", REPO_ROOT / "services" / "shared"):
        for f in root.rglob("*.py"):
            assert "lfhe_pilot" not in f.read_text(), f
