"""Exemple 02 — Typage de documents contractuels (PDF).

Besoin métier
    Trier automatiquement les PDF entrants (avenant, attestation,
    résiliation, facture) pour les ranger dans la bonne corbeille du
    service gestion de contrats.

Ce que cet exemple montre
    - les spécificités de l'asset PDF par rapport à l'asset TEXT :
      `input_type="PDF"` et `content_array` contenant des **chemins de
      fichiers locaux** (le SDK se charge de les téléverser) ;
    - un job de classification simple, sans hiérarchie ;
    - l'usage de `json_metadata_array` pour transporter des informations
      métier (ici le nombre de pages) visibles depuis l'interface.

Usage
    uv run python examples/02_pdf_classification.py
"""

from pathlib import Path

import fitz  # pymupdf
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

PROJECT_TITLE = "02 - Typage de documents contractuels"
PDF_DIR = DATA_DIR / "samples" / "pdf"
EXPORT_PATH = PROCESSED_DIR / "02_pdf_classification" / "labels.json"
MODEL_NAME = "typage-documents-v0"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` de typage documentaire.

    Un unique job mono-classe : un document appartient à un seul type.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "TYPE_DOCUMENT": build_classification_job(
            instruction="Quel est le type de ce document ?",
            categories={
                "AVENANT": build_category("Avenant", color="#472CED"),
                "ATTESTATION": build_category("Attestation", color="#3CD876"),
                "RESILIATION": build_category("Résiliation", color="#D33BCE"),
                "CONSTAT": build_category("Constat amiable", color="#FFB300"),
                "FACTURE": build_category(
                    "Facture de réparation", color="#00B5AD"
                ),
            },
            input_type="radio",
        )
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def list_pdfs() -> list[Path]:
    """Lister les PDF d'exemple à importer.

    Returns:
        Les chemins des PDF, triés pour un ordre reproductible.

    Raises:
        FileNotFoundError: Si aucun PDF n'a été généré.
    """
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(
            f"Aucun PDF dans {PDF_DIR}. Lancez d'abord : "
            "uv run python scripts/generate_sample_data.py"
        )
    return pdfs


def upload_assets(kili: Kili, project_id: str) -> list[str]:
    """Importer les PDF comme assets.

    Spécificité PDF : `content_array` reçoit des chemins de fichiers
    locaux (str). Le SDK lit le fichier et le téléverse vers l'instance.
    On pourrait aussi fournir une URL accessible depuis le serveur Kili.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Les `external_id` importés.
    """
    pdfs = list_pdfs()
    external_ids = [external_id_from_path(path) for path in pdfs]

    # Métadonnée métier : le nombre de pages, lu localement avec pymupdf.
    # `json_metadata` est libre ; elle est consultable dans l'interface et
    # ressort à l'export, ce qui aide à filtrer les assets.
    metadata = []
    for path in pdfs:
        with fitz.open(path) as document:
            metadata.append({"nombre_de_pages": document.page_count})

    kili.append_many_to_dataset(
        project_id=project_id,
        content_array=[str(path) for path in pdfs],
        external_id_array=external_ids,
        json_metadata_array=metadata,
    )
    logger.info("{} PDF importés", len(external_ids))
    return external_ids


# --- 3. Prédictions -------------------------------------------------------


def predict(asset: dict) -> dict:
    """Prédiction factice — TODO: brancher votre modèle ici.

    La forme est identique à celle d'une classification de texte : le
    type d'asset (PDF ou TEXT) ne change **rien** au format de la
    réponse pour un job CLASSIFICATION. Ce n'est vrai que pour la
    classification : dès qu'on annote des zones (OCR, NER sur PDF), des
    coordonnées apparaissent — voir les exemples 06 et 09.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie.
    """
    external_id = asset["external_id"]

    # Règle factice : on se fie au nom du fichier synthétique.
    if external_id.startswith("avenant"):
        category = "AVENANT"
    elif external_id.startswith("attestation"):
        category = "ATTESTATION"
    elif external_id.startswith("resiliation"):
        category = "RESILIATION"
    elif external_id.startswith("facture"):
        category = "FACTURE"
    else:
        category = "CONSTAT"

    return {
        "TYPE_DOCUMENT": {"categories": [{"name": category, "confidence": 88}]}
    }


def upload_predictions(kili: Kili, project_id: str) -> None:
    """Importer les prédictions factices.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    external_ids = [external_id_from_path(path) for path in list_pdfs()]

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
            description="Typage automatique des documents contractuels.",
            input_type="PDF",
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
