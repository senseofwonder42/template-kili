"""Tests du générateur de données d'exemple.

On vérifie que les fichiers attendus sont produits et que la génération
est bien déterministe (même graine → mêmes octets), condition nécessaire
pour que les exemples référencent des `external_id` stables.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_data.py"
)


def load_generator() -> ModuleType:
    """Charger le script de génération comme module.

    Returns:
        Le module chargé.
    """
    spec = importlib.util.spec_from_file_location(
        "generate_sample_data", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return load_generator()


def test_claims_are_deterministic(generator):
    """Deux tirages avec la même graine donnent le même résultat."""
    import random

    first = generator._generate_claims(random.Random(42), 5)
    second = generator._generate_claims(random.Random(42), 5)
    assert first == second


def test_claims_have_stable_external_ids(generator):
    import random

    claims = generator._generate_claims(random.Random(42), 3)
    assert [c["external_id"] for c in claims] == [
        "declaration_000",
        "declaration_001",
        "declaration_002",
    ]
    assert all(c["text"] for c in claims)


def test_emails_are_deterministic(generator):
    import random

    first = generator._generate_emails(random.Random(7), 4)
    second = generator._generate_emails(random.Random(7), 4)
    assert first == second


def test_write_jsonl_roundtrip(tmp_path, generator):
    """Le JSONL écrit doit être relisible ligne par ligne."""
    rows = [{"external_id": "a", "text": "un accident à Lyon"}]
    path = tmp_path / "out" / "rows.jsonl"

    generator._write_jsonl(path, rows)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == rows


def test_write_pdf_creates_a_readable_file(tmp_path, generator):
    """Le PDF produit doit être ouvrable et contenir son titre."""
    import fitz

    path = tmp_path / "doc.pdf"
    generator._write_pdf(path, "CONSTAT AMIABLE", ["Ligne 1", "Ligne 2"])

    assert path.exists()
    with fitz.open(path) as document:
        assert document.page_count == 1
        text = document[0].get_text()
    assert "CONSTAT AMIABLE" in text
    assert "Ligne 1" in text
