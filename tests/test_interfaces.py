"""Tests des constructeurs de `json_interface`.

On vérifie la *forme* des dictionnaires produits, puisque c'est le
contrat avec l'API Kili. Aucun appel réseau n'est effectué.
"""

import pytest

from kili_examples.interfaces import (
    build_category,
    build_classification_job,
    build_json_interface,
    build_ner_job,
    build_object_detection_job,
    build_transcription_job,
)


def test_build_category_defaults():
    category = build_category("Sinistre auto")
    assert category == {"children": [], "name": "Sinistre auto"}


def test_build_category_with_children_and_color():
    category = build_category(
        "Sinistre auto", children=["SOUS_JOB"], color="#472CED"
    )
    assert category["children"] == ["SOUS_JOB"]
    assert category["color"] == "#472CED"


def test_classification_job_shape():
    job = build_classification_job(
        instruction="Type ?",
        categories={"A": build_category("A")},
        input_type="checkbox",
    )
    assert job["mlTask"] == "CLASSIFICATION"
    assert job["content"]["input"] == "checkbox"
    assert job["instruction"] == "Type ?"
    # `required` est bien un entier 0/1 et non un booléen : Kili attend
    # un entier dans le json_interface.
    assert job["required"] == 1
    assert isinstance(job["required"], int)
    assert job["isChild"] is False


def test_classification_job_optional_and_child():
    job = build_classification_job(
        instruction="Sous-type ?",
        categories={"A": build_category("A")},
        required=False,
        is_child=True,
    )
    assert job["required"] == 0
    assert job["isChild"] is True


def test_transcription_job_has_no_categories():
    job = build_transcription_job(instruction="Montant ?")
    assert job["mlTask"] == "TRANSCRIPTION"
    assert job["content"]["categories"] == {}
    assert job["content"]["input"] == "textarea"


def test_object_detection_job_carries_tools():
    job = build_object_detection_job(
        instruction="Entourez",
        categories={"IMPACT": build_category("Impact")},
        tools=["rectangle"],
    )
    assert job["mlTask"] == "OBJECT_DETECTION"
    assert job["tools"] == ["rectangle"]


def test_ner_job_shape():
    job = build_ner_job(
        instruction="Surlignez",
        categories={"MONTANT": build_category("Montant")},
    )
    assert job["mlTask"] == "NAMED_ENTITIES_RECOGNITION"
    assert "MONTANT" in job["content"]["categories"]


def test_build_json_interface_wraps_jobs():
    jobs = {"JOB": build_transcription_job(instruction="x")}
    assert build_json_interface(jobs) == {"jobs": jobs}


@pytest.mark.parametrize("input_type", ["radio", "checkbox", "dropdown"])
def test_classification_accepts_documented_inputs(input_type):
    job = build_classification_job(
        instruction="x",
        categories={"A": build_category("A")},
        input_type=input_type,
    )
    assert job["content"]["input"] == input_type
