"""Tests des charges utiles de prédiction des neuf exemples.

Chaque `predict()` doit produire un `json_response` cohérent avec
l'ontologie du même exemple. On s'appuie sur le parseur du SDK Kili
(`ParsedJobs`), qui applique les mêmes règles de validation que la
plateforme : c'est la vérification la plus fidèle possible sans instance.

Aucun appel réseau n'est effectué : `ParsedJobs` travaille hors ligne.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from kili.services.label_data_parsing.json_response import ParsedJobs
from kili.services.label_data_parsing.types import Project

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"

# Pour chaque exemple : le type d'asset du projet et un asset d'entrée
# minimal accepté par `predict`.
EXAMPLE_CASES = [
    (
        "01_text_classification",
        "TEXT",
        {"external_id": "d0", "text": "collision sur le parking"},
    ),
    ("02_pdf_classification", "PDF", {"external_id": "facture_x"}),
    ("03_image_classification", "IMAGE", {"external_id": "v0"}),
    ("04_object_detection", "IMAGE", {"external_id": "v0"}),
    ("05_segmentation", "IMAGE", {"external_id": "e0"}),
    ("06_pdf_ocr", "PDF", {"external_id": "c0"}),
    ("07_vlm_text_extraction", "PDF", {"external_id": "f0"}),
    (
        "08_ner_text",
        "TEXT",
        {
            "external_id": "e0",
            "text": "Contrat AUTO-2024-1187 du 12/03/2025.",
        },
    ),
    (
        "09_custom_multitask_pdf",
        "PDF",
        {"external_id": "constat_amiable_001"},
    ),
    # L'exemple 10 est volontairement absent : un projet LLM_STATIC
    # n'utilise pas le format `jsonResponse` validé ici (le label est
    # indexé par niveau, et `categories` est une liste de chaînes).
    # Il est couvert par tests/test_rag_review.py.
]


def load_example(name: str) -> ModuleType:
    """Charger un script d'exemple comme module Python.

    Args:
        name: Nom du fichier sans extension (ex. `01_text_classification`).

    Returns:
        Le module chargé.
    """
    path = EXAMPLES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("name", "input_type", "asset"), EXAMPLE_CASES)
def test_prediction_matches_its_interface(name, input_type, asset):
    """La prédiction doit être lisible par le parseur du SDK.

    `ParsedJobs` rejette notamment : un nom de job inconnu, une catégorie
    absente de l'ontologie, un outil non déclaré dans `tools`, ou une
    clé incompatible avec le `mlTask` du job.
    """
    module = load_example(name)
    json_interface = module.build_interface()
    json_response = module.predict(asset)

    parsed = ParsedJobs(
        json_response=json_response,
        project_info=Project(
            jsonInterface=json_interface["jobs"], inputType=input_type
        ),
    )

    # Toute clé de la réponse doit correspondre à un job déclaré.
    assert set(json_response) <= set(json_interface["jobs"])
    assert parsed is not None


@pytest.mark.parametrize(("name", "input_type", "asset"), EXAMPLE_CASES)
def test_prediction_is_not_empty(name, input_type, asset):
    """Une prédiction factice doit remplir au moins un job."""
    module = load_example(name)
    assert module.predict(asset), f"{name} ne prédit rien"


def test_ner_offsets_match_the_asset_text():
    """`beginOffset` et `content` doivent rester cohérents.

    C'est l'erreur la plus fréquente en NER : un offset décalé déplace
    le surlignage dans l'interface sans lever d'erreur à l'import.
    """
    module = load_example("08_ner_text")
    text = (
        "Bonjour, je suis assuré sous le contrat AUTO-2024-1187 "
        "depuis le 12/03/2025. Contactez M. Lambert."
    )
    response = module.predict({"external_id": "e0", "text": text})

    annotations = response["ENTITES_EMAIL"]["annotations"]
    assert annotations, "aucune entité détectée sur ce texte"
    for annotation in annotations:
        begin = annotation["beginOffset"]
        content = annotation["content"]
        assert text[begin : begin + len(content)] == content


def test_classification_child_job_is_nested_under_its_category():
    """Le sous-job doit se trouver sous `children` de la catégorie."""
    module = load_example("01_text_classification")
    response = module.predict(
        {"external_id": "d0", "text": "collision au rond-point"}
    )

    category = response["CLASSIFICATION_SINISTRE"]["categories"][0]
    assert category["name"] == "SINISTRE_AUTO"
    assert "SOUS_TYPE_AUTO" in category["children"]


def test_multitask_prediction_addresses_several_jobs():
    """L'exemple 09 doit remplir plusieurs jobs en une seule réponse."""
    module = load_example("09_custom_multitask_pdf")
    response = module.predict({"external_id": "constat_amiable_001"})

    assert len(response) >= 3
    # Chaque type de job a sa propre forme de réponse.
    assert "categories" in response["TYPE_DOCUMENT"]
    assert "annotations" in response["ENTITES_DOCUMENT"]
    assert "annotations" in response["ZONES_CLES"]


def test_every_example_is_covered_by_a_test():
    """Aucun exemple ne doit échapper à la validation.

    Les exemples classiques sont couverts ici ; l'exemple 10
    (LLM_STATIC) l'est par `test_rag_review.py`. Ajouter un exemple sans
    test doit faire échouer cette assertion.
    """
    on_disk = {path.stem for path in EXAMPLES_DIR.glob("[0-9]*.py")}
    covered = {name for name, _, _ in EXAMPLE_CASES}
    covered.add("10_llm_judge_ab_testing")  # cf. test_rag_review.py

    assert on_disk == covered


def test_vlm_omits_fields_the_model_could_not_read():
    """Un champ non extrait ne doit pas produire de job vide."""
    module = load_example("07_vlm_text_extraction")
    response = module.predict({"external_id": "f0"})

    # `franchise` vaut None dans la sortie factice du modèle.
    assert "MONTANT_FRANCHISE" not in response
    assert response["MONTANT_TTC"]["text"] == "816.00"
