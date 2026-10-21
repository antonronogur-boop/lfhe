"""Addendum §15 test 31 / §16 'GS answer-key leakage = 0' (ADR-0007).

Static half: nothing a model can see or a worker image packages carries
Gold-Standard / answer-key material — prompt bundles, fixtures, input
builders, prompt rendering and versioned specs-for-prompts. The runtime half
(no marker in any envelope actually sent) is measured by the Phase 3
acceptance corpus (metric gs_leakage)."""
import re

from conftest import REPO_ROOT

MARKERS = re.compile(r"gs-0\d\d|gold[ _-]?standard|answer[ _-]?key|expected_(claims|events|assessment)|scoring[ _-]notes",
                     re.IGNORECASE)
# Places whose content reaches a model or a worker image.
MODEL_REACHABLE = [
    REPO_ROOT / "packages" / "prompts",
    REPO_ROOT / "services",
    REPO_ROOT / "tests" / "fixtures",
]
# Files that legitimately DESCRIBE the isolation rule (never packaged, never in prompts).
ALLOWED = {
    REPO_ROOT / "tests" / "fixtures" / "phase3_acceptance" / "corpus.json",   # states it is not GS material
    REPO_ROOT / "tests" / "fixtures" / "phase4_acceptance" / "corpus.json",   # states it is not GS material
    REPO_ROOT / "tests" / "fixtures" / "phase5_acceptance" / "corpus.json",   # states it is not GS material
}


def _files(root):
    return [p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
            and p.suffix in {".md", ".json", ".py", ".txt", ".sql", ".html", ".yaml", ".yml", ".toml"}]


def test_no_gold_standard_material_in_model_reachable_tree():
    hits = []
    for root in MODEL_REACHABLE:
        for f in _files(root):
            if f in ALLOWED:
                continue
            for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                if MARKERS.search(line):
                    hits.append(f"{f.relative_to(REPO_ROOT)}:{n}: {line.strip()[:100]}")
    assert hits == []


def test_allowed_files_only_disclaim_and_carry_no_answer_key():
    for f in ALLOWED:
        text = f.read_text()
        assert [m.group(0).lower() for m in MARKERS.finditer(text)] == ["gold standard"]
        assert "Not Gold Standard material" in text


def test_no_gold_standard_tree_inside_repository():
    assert not (REPO_ROOT / "tests" / "gold-standard").exists()
    assert not list(REPO_ROOT.glob("**/gold*standard*")) or all(
        "node_modules" in p.parts or ".git" in p.parts for p in REPO_ROOT.glob("**/gold*standard*"))


def test_input_builders_read_only_the_database():
    """Envelope builders take a DB connection and claim ids; they open no files."""
    for name in ("claim_inputs.py", "event_inputs.py", "assessment_inputs.py", "report_inputs.py"):
        src = (REPO_ROOT / "services" / "ai-orchestrator" / "lfhe_orchestrator" / name).read_text()
        assert not re.search(r"\bopen\(|Path\(|read_text|os\.environ|getenv", src), name
