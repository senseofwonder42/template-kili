"""Exemple 06 — Transcription d'un constat amiable (OCR sur PDF).

Besoin métier
    Relever les champs manuscrits d'un constat amiable (date, lieu,
    immatriculation) pour alimenter l'outil de gestion sans ressaisie.

Ce que cet exemple montre
    - un job TRANSCRIPTION : l'annotateur saisit du texte libre, il n'y a
      pas de catégories ;
    - la combinaison « zone + texte » : un job OBJECT_DETECTION sur le
      PDF, dont chaque boîte porte un **sous-job TRANSCRIPTION** ; c'est
      le montage classique pour de l'OCR assisté ;
    - la géométrie propre au PDF : en plus de `boundingPoly`, une
      annotation PDF porte `polys` et `pageNumberArray` (le numéro de
      page, indexé à partir de 1).

Usage
    uv run python examples/06_pdf_ocr.py
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
    build_transcription_job,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR

PROJECT_TITLE = "06 - OCR du constat amiable"
PDF_DIR = DATA_DIR / "samples" / "pdf"
EXPORT_PATH = PROCESSED_DIR / "06_pdf_ocr" / "labels.json"
MODEL_NAME = "ocr-constat-v0"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` d'OCR.

    Montage en deux niveaux :

    - `CHAMPS_CONSTAT` (OBJECT_DETECTION, outil `rectangle`) : chaque
      catégorie correspond à un champ du formulaire. Toutes déclarent
      `children=["TRANSCRIPTION_CHAMP"]`.
    - `TRANSCRIPTION_CHAMP` (TRANSCRIPTION, `isChild=True`) : la valeur
      lue dans la zone entourée.

    Résultat pour l'annotateur : il entoure la case « date », puis saisit
    la valeur qu'il y lit.

    Returns:
        Le `json_interface` complet.
    """
    child_jobs = ["TRANSCRIPTION_CHAMP"]
    jobs = {
        "CHAMPS_CONSTAT": build_object_detection_job(
            instruction="Entourez chaque champ renseigné du constat.",
            categories={
                "DATE_ACCIDENT": build_category(
                    "Date de l'accident",
                    children=child_jobs,
                    color="#472CED",
                ),
                "LIEU_ACCIDENT": build_category(
                    "Lieu de l'accident",
                    children=child_jobs,
                    color="#3CD876",
                ),
                "IMMATRICULATION": build_category(
                    "Immatriculation",
                    children=child_jobs,
                    color="#FFB300",
                ),
                "NUMERO_CONTRAT": build_category(
                    "Numéro de contrat",
                    children=child_jobs,
                    color="#D33BCE",
                ),
            },
            tools=["rectangle"],
        ),
        "TRANSCRIPTION_CHAMP": build_transcription_job(
            instruction="Recopiez la valeur lue dans la zone entourée.",
            is_child=True,
        ),
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def list_pdfs() -> list[Path]:
    """Lister les constats à annoter.

    Returns:
        Les chemins des constats, triés.

    Raises:
        FileNotFoundError: Si aucun constat n'a été généré.
    """
    pdfs = sorted(PDF_DIR.glob("constat_amiable_*.pdf"))
    if not pdfs:
        raise FileNotFoundError(
            f"Aucun constat dans {PDF_DIR}. Lancez d'abord : "
            "uv run python scripts/generate_sample_data.py"
        )
    return pdfs


def upload_assets(kili: Kili, project_id: str) -> list[str]:
    """Importer les constats comme assets PDF.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Les `external_id` importés.
    """
    pdfs = list_pdfs()
    external_ids = [external_id_from_path(path) for path in pdfs]

    kili.append_many_to_dataset(
        project_id=project_id,
        content_array=[str(path) for path in pdfs],
        external_id_array=external_ids,
    )
    logger.info("{} constats importés", len(external_ids))
    return external_ids


# --- 3. Prédictions -------------------------------------------------------


def _pdf_zone(
    *,
    left: float,
    top: float,
    right: float,
    bottom: float,
    page: int,
) -> dict:
    """Construire la géométrie d'une zone sur une page de PDF.

    Une annotation PDF se distingue d'une annotation image par deux clés
    supplémentaires :

    - `polys` : les contours effectifs de la zone. Quand une annotation
      court sur plusieurs lignes, `polys` contient un rectangle par
      ligne, alors que `boundingPoly` reste l'enveloppe globale.
    - `pageNumberArray` : la ou les pages concernées, **indexées à
      partir de 1**.

    Args:
        left: Bord gauche, normalisé.
        top: Bord haut, normalisé.
        right: Bord droit, normalisé.
        bottom: Bord bas, normalisé.
        page: Numéro de page (1 pour la première).

    Returns:
        Le dictionnaire de géométrie, à placer dans `annotations`.
    """
    vertices = [
        {"x": left, "y": bottom},
        {"x": left, "y": top},
        {"x": right, "y": top},
        {"x": right, "y": bottom},
    ]
    return {
        "boundingPoly": [{"normalizedVertices": vertices}],
        "polys": [{"normalizedVertices": vertices}],
        "pageNumberArray": [page],
    }


def predict(asset: dict) -> dict:
    """Prédiction factice — TODO: brancher votre modèle ici.

    Structure d'une réponse « zone + transcription » sur PDF :

        {
          "CHAMPS_CONSTAT": {
            "annotations": [
              {
                "categories": [{"name": "DATE_ACCIDENT"}],
                "mid": "...",
                "type": "rectangle",
                "content": "",
                "annotations": [ {boundingPoly, polys, pageNumberArray} ],
                "children": {
                  "TRANSCRIPTION_CHAMP": {"text": "12/03/2025"}
                }
              }
            ]
          }
        }

    Points à retenir :

    - la géométrie PDF est dans une liste `annotations` **imbriquée**
      dans l'annotation, et non directement à sa racine ;
    - `children` porte la réponse du sous-job, ici la valeur transcrite ;
    - un job TRANSCRIPTION répond avec la clé `text` (et non
      `categories`) ;
    - `content` de l'annotation parente reste vide pour de l'OCR : c'est
      le sous-job qui porte le texte.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie.
    """
    champs = [
        ("DATE_ACCIDENT", "12/03/2025", 0.30, 0.15, 0.55, 0.19),
        ("LIEU_ACCIDENT", "Lyon", 0.30, 0.20, 0.55, 0.24),
        ("NUMERO_CONTRAT", "AUTO-2024-1187", 0.30, 0.30, 0.62, 0.34),
    ]

    annotations = []
    for index, (categorie, valeur, left, top, right, bottom) in enumerate(
        champs
    ):
        annotations.append(
            {
                "categories": [{"name": categorie, "confidence": 85}],
                "mid": f"prediction-champ-{index}",
                "type": "rectangle",
                "content": "",
                "annotations": [
                    _pdf_zone(
                        left=left,
                        top=top,
                        right=right,
                        bottom=bottom,
                        page=1,
                    )
                ],
                # Réponse du sous-job TRANSCRIPTION pour cette zone.
                "children": {"TRANSCRIPTION_CHAMP": {"text": valeur}},
            }
        )

    return {"CHAMPS_CONSTAT": {"annotations": annotations}}


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
            description="Relevé des champs d'un constat amiable.",
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
