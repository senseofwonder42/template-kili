"""Tests des helpers d'import et d'export, avec un client Kili simulé.

Le client Kili est remplacé par un double qui enregistre les appels :
aucun réseau n'est sollicité et aucune clé d'API n'est nécessaire.
"""

import json
from pathlib import Path

import pytest

from kili_examples.assets import (
    DEFAULT_BATCH_SIZE,
    external_id_from_path,
    upload_assets_in_batches,
)
from kili_examples.exports import export_labels_to_json


class FakeKili:
    """Double de test enregistrant les appels au SDK."""

    def __init__(self, labels: list[dict] | None = None) -> None:
        self.calls: list[dict] = []
        self._labels = labels or []

    def append_many_to_dataset(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"id": "fake-project"}

    def labels(self, **kwargs) -> list[dict]:
        self.calls.append(kwargs)
        return self._labels


def test_external_id_from_path_drops_the_extension():
    assert external_id_from_path(Path("/tmp/constat_001.pdf")) == "constat_001"


def test_upload_sends_a_single_batch_when_small():
    kili = FakeKili()
    upload_assets_in_batches(
        kili,
        "project-1",
        content_array=["a", "b"],
        external_id_array=["id-a", "id-b"],
    )
    assert len(kili.calls) == 1
    assert kili.calls[0]["content_array"] == ["a", "b"]
    assert kili.calls[0]["project_id"] == "project-1"


def test_upload_splits_into_batches():
    kili = FakeKili()
    count = DEFAULT_BATCH_SIZE + 5
    upload_assets_in_batches(
        kili,
        "project-1",
        content_array=[f"text-{i}" for i in range(count)],
        external_id_array=[f"id-{i}" for i in range(count)],
        batch_size=DEFAULT_BATCH_SIZE,
    )
    assert len(kili.calls) == 2
    assert len(kili.calls[0]["external_id_array"]) == DEFAULT_BATCH_SIZE
    assert len(kili.calls[1]["external_id_array"]) == 5


def test_upload_preserves_metadata_alignment():
    kili = FakeKili()
    upload_assets_in_batches(
        kili,
        "project-1",
        content_array=["a", "b", "c"],
        external_id_array=["id-a", "id-b", "id-c"],
        json_metadata_array=[{"n": 1}, {"n": 2}, {"n": 3}],
        batch_size=2,
    )
    assert kili.calls[0]["json_metadata_array"] == [{"n": 1}, {"n": 2}]
    assert kili.calls[1]["json_metadata_array"] == [{"n": 3}]


def test_upload_rejects_mismatched_lengths():
    kili = FakeKili()
    with pytest.raises(ValueError, match="même longueur"):
        upload_assets_in_batches(
            kili,
            "project-1",
            content_array=["a", "b"],
            external_id_array=["id-a"],
        )


def test_upload_rejects_mismatched_metadata():
    kili = FakeKili()
    with pytest.raises(ValueError, match="json_metadata_array"):
        upload_assets_in_batches(
            kili,
            "project-1",
            content_array=["a", "b"],
            external_id_array=["id-a", "id-b"],
            json_metadata_array=[{"n": 1}],
        )


def test_export_writes_labels_as_json(tmp_path):
    labels = [{"id": "label-1", "jsonResponse": {"JOB": {"text": "42"}}}]
    kili = FakeKili(labels=labels)
    output = tmp_path / "sous-dossier" / "labels.json"

    returned = export_labels_to_json(kili, "project-1", output)

    assert returned == labels
    # Le dossier parent est créé au besoin.
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == labels
