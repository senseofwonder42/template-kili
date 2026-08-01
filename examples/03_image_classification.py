"""Exemple 03 — Gravité des dégâts sur photo de véhicule (image).

Besoin métier
    Estimer la gravité des dégâts à partir des photos envoyées par
    l'assuré, pour orienter le dossier vers une expertise sur place ou un
    règlement simplifié.

Ce que cet exemple montre
    - un projet `input_type="IMAGE"` ;
    - un job mono-classe pour la gravité et un second job multi-label
      (`input: "checkbox"`) pour les parties touchées — deux jobs
      indépendants, sans hiérarchie ;
    - la forme d'une prédiction multi-label (plusieurs entrées dans
      `categories`).

Usage
    uv run python examples/03_image_classification.py
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
    build_classification_job,
    build_json_interface,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR

PROJECT_TITLE = "03 - Gravite des degats vehicule"
IMAGE_DIR = DATA_DIR / "samples" / "image"
EXPORT_PATH = PROCESSED_DIR / "03_image_classification" / "labels.json"
MODEL_NAME = "gravite-degats-v0"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` d'évaluation des dégâts.

    Deux jobs indépendants :

    - `GRAVITE_DEGATS` : une seule réponse possible (`radio`) ;
    - `PARTIES_TOUCHEES` : plusieurs réponses possibles (`checkbox`).

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "GRAVITE_DEGATS": build_classification_job(
            instruction="Quelle est la gravité des dégâts visibles ?",
            categories={
                "LEGER": build_category("Léger (rayure)", color="#3CD876"),
                "MODERE": build_category(
                    "Modéré (tôle froissée)", color="#FFB300"
                ),
                "IMPORTANT": build_category("Important", color="#FF6B6B"),
                "EPAVE": build_category(
                    "Véhicule irréparable", color="#D33BCE"
                ),
            },
            input_type="radio",
        ),
        "PARTIES_TOUCHEES": build_classification_job(
            instruction="Quelles parties du véhicule sont touchées ?",
            categories={
                "PARE_CHOCS": build_category("Pare-chocs"),
                "PORTIERE": build_category("Portière"),
                "CAPOT": build_category("Capot"),
                "VITRAGE": build_category("Vitrage"),
                "OPTIQUE": build_category("Bloc optique"),
            },
            # `checkbox` : l'annotateur peut cocher plusieurs cases.
            input_type="checkbox",
            required=False,
        ),
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def list_images() -> list[Path]:
    """Lister les photos de véhicule à importer.

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

    Comme pour le PDF, `content_array` accepte des chemins locaux.

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


def predict(asset: dict) -> dict:
    """Prédiction factice — TODO: brancher votre modèle ici.

    Illustre la différence entre mono-classe et multi-label :

    - `GRAVITE_DEGATS` (radio) → **une seule** entrée dans `categories` ;
    - `PARTIES_TOUCHEES` (checkbox) → **plusieurs** entrées, chacune avec
      son propre `confidence`.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie.
    """
    return {
        "GRAVITE_DEGATS": {
            "categories": [{"name": "MODERE", "confidence": 76}]
        },
        "PARTIES_TOUCHEES": {
            "categories": [
                {"name": "PARE_CHOCS", "confidence": 91},
                {"name": "PORTIERE", "confidence": 63},
            ]
        },
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
            description="Évaluation de la gravité des dégâts sur photo.",
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
