"""Exemple 05 — Polygones et masques de zones sinistrées (dégât des eaux).

Besoin métier
    Délimiter finement les surfaces touchées par un dégât des eaux afin
    d'estimer la surface à reprendre (peinture, plafond) — une boîte
    rectangulaire serait trop grossière pour un chiffrage au m².

Ce que cet exemple montre
    - le même `mlTask` OBJECT_DETECTION que l'exemple 04, mais avec les
      outils `semantic` et `polygon` ;
    - un contour libre : `normalizedVertices` contient autant de points
      que nécessaire, et non plus exactement quatre ;
    - un `boundingPoly` à **plusieurs** entrées, pour une zone en deux
      morceaux disjoints.

Différence entre les deux outils
    - `polygon`  : un contour fermé, dessiné point par point ;
    - `semantic` : un masque de segmentation sémantique, que l'interface
      Kili propose avec des outils de type pinceau. Le format de sortie
      reste une liste de sommets normalisés.

Usage
    uv run python examples/05_segmentation.py
"""

import math
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

PROJECT_TITLE = "05 - Segmentation des zones sinistrees"
IMAGE_DIR = DATA_DIR / "samples" / "image"
EXPORT_PATH = PROCESSED_DIR / "05_segmentation" / "labels.json"
MODEL_NAME = "segmentation-degats-eaux-v0"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` de segmentation.

    On autorise deux outils dans le même job : l'annotateur choisit le
    plus adapté à la forme à détourer. La réponse portera alors
    `"type": "semantic"` ou `"type": "polygon"` selon son choix.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "ZONES_SINISTREES": build_object_detection_job(
            instruction=(
                "Détourez les surfaces touchées par le dégât des eaux."
            ),
            categories={
                "AUREOLE": build_category(
                    "Auréole d'humidité", color="#00B5AD"
                ),
                "PEINTURE_CLOQUEE": build_category(
                    "Peinture cloquée", color="#FFB300"
                ),
                "MOISISSURE": build_category("Moisissure", color="#3CD876"),
            },
            tools=["semantic", "polygon"],
        )
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def list_images() -> list[Path]:
    """Lister les photos de dégât des eaux à annoter.

    Returns:
        Les chemins des images, triés.

    Raises:
        FileNotFoundError: Si aucune image n'a été générée.
    """
    images = sorted(IMAGE_DIR.glob("degat_des_eaux_*.jpg"))
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


def _ellipse_vertices(
    center_x: float, center_y: float, radius_x: float, radius_y: float
) -> list[dict]:
    """Approximer une ellipse par un polygone de 12 sommets.

    Tient lieu de sortie d'un modèle de segmentation : ce qui compte est
    la forme du résultat (une liste ordonnée de sommets normalisés), pas
    la façon dont on l'obtient.

    Args:
        center_x: Abscisse du centre, normalisée.
        center_y: Ordonnée du centre, normalisée.
        radius_x: Demi-axe horizontal, normalisé.
        radius_y: Demi-axe vertical, normalisé.

    Returns:
        Les sommets du polygone, dans le sens trigonométrique.
    """
    points = []
    for step in range(12):
        angle = 2 * math.pi * step / 12
        points.append(
            {
                "x": round(center_x + radius_x * math.cos(angle), 4),
                "y": round(center_y + radius_y * math.sin(angle), 4),
            }
        )
    return points


def predict(asset: dict) -> dict:
    """Prédiction factice — TODO: brancher votre modèle ici.

    Deux différences par rapport à l'exemple 04 :

    1. `normalizedVertices` contient ici 12 sommets — un contour libre
       n'est pas limité à quatre points ;
    2. la seconde annotation a un `boundingPoly` de **deux** entrées :
       c'est ainsi qu'on décrit une zone en plusieurs morceaux disjoints
       (ou une forme trouée) sous une seule et même annotation, donc un
       seul `mid`.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie.
    """
    return {
        "ZONES_SINISTREES": {
            "annotations": [
                {
                    "categories": [{"name": "AUREOLE", "confidence": 82}],
                    "boundingPoly": [
                        {
                            "normalizedVertices": _ellipse_vertices(
                                0.50, 0.48, 0.22, 0.17
                            )
                        }
                    ],
                    "type": "semantic",
                    "mid": "prediction-aureole-1",
                },
                {
                    "categories": [
                        {"name": "PEINTURE_CLOQUEE", "confidence": 61}
                    ],
                    # Zone en deux taches distinctes : deux polygones,
                    # une seule annotation.
                    "boundingPoly": [
                        {
                            "normalizedVertices": _ellipse_vertices(
                                0.28, 0.30, 0.06, 0.05
                            )
                        },
                        {
                            "normalizedVertices": _ellipse_vertices(
                                0.72, 0.66, 0.05, 0.04
                            )
                        },
                    ],
                    "type": "polygon",
                    "mid": "prediction-cloquage-1",
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
            description="Segmentation des surfaces touchées par l'eau.",
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
