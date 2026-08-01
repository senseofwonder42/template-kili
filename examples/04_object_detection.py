"""Exemple 04 — Détection des zones endommagées (bounding boxes).

Besoin métier
    Localiser précisément les zones abîmées sur les photos de véhicule
    afin de chiffrer les réparations poste par poste.

Ce que cet exemple montre
    - un job OBJECT_DETECTION avec l'outil `rectangle` ;
    - la géométrie Kili : `boundingPoly` → `normalizedVertices`, des
      coordonnées **normalisées entre 0 et 1**, origine en haut à gauche ;
    - les clés `type` et `mid` d'une annotation d'objet.

Usage
    uv run python examples/04_object_detection.py
"""

from pathlib import Path

from kili.client import Kili
from loguru import logger

from kili_examples.assets import external_id_from_path
from kili_examples.cli import build_parser, parse_steps
from kili_examples.client import get_kili
from kili_examples.exports import export_labels_to_json
from kili_examples.interfaces import (
    build_category,
    build_json_interface,
    build_object_detection_job,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR

PROJECT_TITLE = "04 - Detection des zones endommagees"
IMAGE_DIR = DATA_DIR / "samples" / "image"
EXPORT_PATH = PROCESSED_DIR / "04_object_detection" / "labels.json"
MODEL_NAME = "detection-degats-v0"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` de détection.

    Le `mlTask` est OBJECT_DETECTION et `tools=["rectangle"]` restreint
    l'annotateur aux boîtes englobantes. Ajouter `"polygon"` à la liste
    autoriserait aussi les polygones dans le même job (voir exemple 05).

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "ZONES_ENDOMMAGEES": build_object_detection_job(
            instruction="Entourez chaque zone endommagée du véhicule.",
            categories={
                "IMPACT": build_category(
                    "Impact / enfoncement", color="#FF6B6B"
                ),
                "RAYURE": build_category("Rayure", color="#FFB300"),
                "VITRE_BRISEE": build_category(
                    "Vitre brisée", color="#472CED"
                ),
            },
            tools=["rectangle"],
        )
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def list_images() -> list[Path]:
    """Lister les photos de véhicule à annoter.

    Returns:
        Les chemins des images, triés.

    Raises:
        FileNotFoundError: Si aucune image n'a été générée.
    """
    images = sorted(IMAGE_DIR.glob("vehicule_degat_*.jpg"))
    if not images:
        raise FileNotFoundError(
            f"Aucune image dans {IMAGE_DIR}. Lancez d'abord : "
            "uv run python scripts/generate_sample_data.py"
        )
    return images


def upload_assets(kili: Kili, project_id: str) -> list[str]:
    """Importer les photos comme assets IMAGE.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Les `external_id` importés.
    """
    images = list_images()
    external_ids = [external_id_from_path(path) for path in images]

    kili.append_many_to_dataset(
        project_id=project_id,
        content_array=[str(path) for path in images],
        external_id_array=external_ids,
    )
    logger.info("{} images importées", len(external_ids))
    return external_ids


# --- 3. Prédictions -------------------------------------------------------


def build_rectangle(
    *, left: float, top: float, right: float, bottom: float
) -> list[dict]:
    """Construire les `normalizedVertices` d'une boîte englobante.

    Conventions Kili pour les coordonnées :

    - l'origine (0, 0) est le **coin haut-gauche** de l'image ;
    - `x` croît vers la droite, `y` vers le bas ;
    - les valeurs sont **normalisées** dans [0, 1] : elles ne dépendent
      donc pas de la résolution de l'image. Une boîte occupant le quart
      supérieur gauche va de (0, 0) à (0.5, 0.5).

    L'ordre des quatre sommets attendu par Kili est :
    bas-gauche, haut-gauche, haut-droit, bas-droit.
    (Le SDK fournit `kili.utils.labels.bbox.bbox_points_to_normalized_vertices`
    pour convertir depuis des pixels ; on l'écrit ici à la main pour que
    la structure reste visible.)

    Args:
        left: Bord gauche, normalisé.
        top: Bord haut, normalisé.
        right: Bord droit, normalisé.
        bottom: Bord bas, normalisé.

    Returns:
        La liste des quatre sommets `{"x": ..., "y": ...}`.
    """
    return [
        {"x": left, "y": bottom},
        {"x": left, "y": top},
        {"x": right, "y": top},
        {"x": right, "y": bottom},
    ]


def predict(asset: dict) -> dict:
    """Prédiction factice — TODO: brancher votre modèle ici.

    Structure d'une réponse de détection d'objets :

        {
          "NOM_DU_JOB": {
            "annotations": [
              {
                "categories": [{"name": "IMPACT", "confidence": 87}],
                "boundingPoly": [{"normalizedVertices": [...]}],
                "type": "rectangle",
                "mid": "identifiant-unique"
              }
            ]
          }
        }

    - `annotations` (et non `categories`) est la clé racine : un job de
      détection produit **plusieurs objets** par asset.
    - `boundingPoly` est une **liste** : un objet peut être fait de
      plusieurs polygones (trous, formes disjointes — voir exemple 05).
    - `type` reprend l'outil utilisé et doit figurer parmi les `tools`
      déclarés dans le json_interface.
    - `mid` est l'identifiant de l'objet dans l'asset. Il doit être
      unique au sein de l'asset ; Kili le génère pour les annotations
      humaines, à nous de le fournir pour les prédictions.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie.
    """
    return {
        "ZONES_ENDOMMAGEES": {
            "annotations": [
                {
                    "categories": [{"name": "IMPACT", "confidence": 87}],
                    "boundingPoly": [
                        {
                            "normalizedVertices": build_rectangle(
                                left=0.62, top=0.48, right=0.87, bottom=0.70
                            )
                        }
                    ],
                    "type": "rectangle",
                    "mid": "prediction-impact-1",
                },
                {
                    "categories": [{"name": "RAYURE", "confidence": 54}],
                    "boundingPoly": [
                        {
                            "normalizedVertices": build_rectangle(
                                left=0.20, top=0.40, right=0.35, bottom=0.46
                            )
                        }
                    ],
                    "type": "rectangle",
                    "mid": "prediction-rayure-1",
                },
            ]
        }
    }


def upload_predictions(kili: Kili, project_id: str) -> None:
    """Importer les prédictions factices.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    external_ids = [external_id_from_path(path) for path in list_images()]

    kili.create_predictions(
        project_id=project_id,
        external_id_array=external_ids,
        json_response_array=[
            predict({"external_id": external_id})
            for external_id in external_ids
        ],
        model_name=MODEL_NAME,
    )
    logger.info("{} prédictions importées", len(external_ids))


# --- 4. Orchestration -----------------------------------------------------


def main() -> None:
    """Enchaîner les quatre étapes du cycle de vie."""
    setup_logging()
    steps = parse_steps(build_parser(__doc__ or PROJECT_TITLE))
    kili = get_kili()

    project_id = steps.project_id
    if steps.create:
        project = kili.create_project(
            title=PROJECT_TITLE,
            description="Détection des zones endommagées sur photo.",
            input_type="IMAGE",
            json_interface=build_interface(),
        )
        project_id = project["id"]
        logger.info("Projet créé — project_id = {}", project_id)

    if project_id is None:
        raise RuntimeError("Aucun project_id disponible.")

    if steps.upload:
        upload_assets(kili, project_id)
    if steps.predict:
        upload_predictions(kili, project_id)
    if steps.export:
        export_labels_to_json(kili, project_id, Path(EXPORT_PATH))

    logger.info("Terminé. project_id = {}", project_id)


if __name__ == "__main__":
    main()
