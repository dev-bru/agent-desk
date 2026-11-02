"""Check teaching docstrings, source references, and honest delivery wording."""

import ast
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_module_and_public_function_docstrings():
    """Check source and lesson functions, including methods and nested tools."""
    paths = sorted((ROOT / "src" / "agent_desk").rglob("*.py"))
    assert paths
    paths += sorted((ROOT / "lessons").glob("*.py"))
    missing = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not ast.get_docstring(tree, clean=True):
            missing.append(f"{path.relative_to(ROOT)}:1 module")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_") and not ast.get_docstring(node, clean=True):
                    missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    assert not missing, "Missing plain-English docstrings:\n" + "\n".join(missing)


def delivery_claims_without_denial(text):
    """Return sentences that use the delivery claim without the word not."""
    sentences = re.split(r"\n\s*\n|(?<=[.!?])\s+", text)
    return [sentence for sentence in sentences
            if "exactly-once" in sentence.lower() and not re.search(r"\bnot\b", sentence, re.IGNORECASE)]


@pytest.mark.parametrize("text,invalid", [
    ("Delivery is at-least-once; exactly-once is not claimed.", False),
    ("Exactly-once is\nnot claimed.", False),
    ("We guarantee exactly-once.", True),
    ("This is not slow. We guarantee exactly-once.", True),
    ("No exactly-once claim.", True),
])
def test_delivery_wording_check(text, invalid):
    """Make sure a denial must be in the same sentence as the claim."""
    assert bool(delivery_claims_without_denial(text)) is invalid


def test_docs_deny_exactly_once():
    """Scan README, docs, and lessons, including the offline HTML diagram."""
    paths = [ROOT / "README.md"]
    for folder in ("docs", "lessons"):
        paths.extend(path for path in (ROOT / folder).rglob("*") if path.suffix in {".md", ".html", ".py"})
    failures = []
    for path in paths:
        for sentence in delivery_claims_without_denial(path.read_text(encoding="utf-8")):
            failures.append(f"{path.relative_to(ROOT)}: {sentence.strip()}")
    assert not failures, "Delivery claims need an explicit denial:\n" + "\n".join(failures)


def test_teaching_source_references_exist():
    """Keep path and line references in the README and new lessons usable."""
    paths = [ROOT / "README.md", *sorted((ROOT / "lessons").glob("[0-9][0-9]-*.md"))]
    for path in paths:
        for relative, line in re.findall(r"((?:src/agent_desk|tests|lessons)/[\w/-]+\.py):(\d+)",
                                         path.read_text(encoding="utf-8")):
            source = ROOT / relative
            assert source.is_file(), f"{path.name}: missing {relative}"
            assert 1 <= int(line) <= len(source.read_text(encoding="utf-8").splitlines()), (path, relative, line)
