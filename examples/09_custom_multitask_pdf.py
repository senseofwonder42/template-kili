"""Exemple 09 — Interface personnalisée multi-tâches sur PDF de sinistre.

Besoin métier
    Traiter un PDF de sinistre en une seule passe d'annotation : typer le
    document, en extraire les entités, relever les champs clés et
    localiser les zones d'intérêt — plutôt que de faire circuler le même
    document dans quatre projets successifs.

Ce que cet exemple montre — c'est l'exemple de référence du dépôt
    1. Une interface Kili n'est **rien d'autre qu'un arbre JSON de
       jobs**. On peut en combiner autant que nécessaire dans un projet,
       de types différents, du moment que le type d'asset les supporte.
    2. Un **job conditionnel** : `SOUS_TYPE_SINISTRE` n'apparaît que si
       l'annotateur classe le document en `DECLARATION_SINISTRE`.
    3. Une **prédiction unique adresse plusieurs jobs à la fois** : le
       `json_response` envoyé à `create_predictions` est un dictionnaire
       dont les clés de premier niveau sont les noms de jobs. Chaque job
       y suit la forme propre à son `mlTask` — celle des exemples 01 à 08.

Les quatre jobs combinés ici :

    TYPE_DOCUMENT       CLASSIFICATION      → exemple 02
      └ SOUS_TYPE_SINISTRE  (conditionnel)  → exemple 01
    ENTITES_DOCUMENT    NAMED_ENTITIES_...  → exemple 08 (variante PDF)
    MONTANT_TOTAL       TRANSCRIPTION       → exemple 07
    ZONES_CLES          OBJECT_DETECTION    → exemples 04 et 06

Usage
    uv run python examples/09_custom_multitask_pdf.py
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
    build_ner_job,
    build_object_detection_job,
    build_transcription_job,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR

PROJECT_TITLE = "09 - Traitement multi-taches d'un PDF de sinistre"
PDF_DIR = DATA_DIR / "samples" / "pdf"
EXPORT_PATH = PROCESSED_DIR / "09_custom_multitask_pdf" / "labels.json"
MODEL_NAME = "multitache-sinistre-v0"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` multi-tâches.

    Quatre jobs racines plus un sous-job conditionnel. Rien ne les relie
    entre eux : Kili affiche simplement les quatre panneaux dans
    l'interface, et la réponse d'annotation portera une clé par job
    effectivement rempli.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        # --- Job 1 : classification, avec branche conditionnelle -------
        "TYPE_DOCUMENT": build_classification_job(
            instruction="Quel est le type de ce document ?",
            categories={
                "DECLARATION_SINISTRE": build_category(
                    "Déclaration de sinistre",
                    # Seule cette catégorie ouvre le sous-job.
                    children=["SOUS_TYPE_SINISTRE"],
                    color="#472CED",
                ),
                "FACTURE": build_category(
                    "Facture de réparation", color="#3CD876"
                ),
                "ATTESTATION": build_category("Attestation", color="#FFB300"),
                "AUTRE": build_category("Autre", color="#9E9E9E"),
            },
            input_type="radio",
        ),
        "SOUS_TYPE_SINISTRE": build_classification_job(
            instruction="Nature du sinistre déclaré ?",
            categories={
                "AUTO": build_category("Automobile"),
                "HABITATION": build_category("Habitation"),
                "SANTE": build_category("Santé"),
            },
            input_type="radio",
            required=False,
            # `isChild=True` : ce job ne s'affiche jamais seul.
            is_child=True,
        ),
        # --- Job 2 : entités nommées sur le texte du PDF ---------------
        "ENTITES_DOCUMENT": build_ner_job(
            instruction="Surlignez les entités clés du document.",
            categories={
                "NUMERO_CONTRAT": build_category(
                    "Numéro de contrat", color="#00B5AD"
                ),
                "DATE_ACCIDENT": build_category(
                    "Date de l'accident", color="#FF6B6B"
                ),
                "NOM_ASSURE": build_category(
                    "Nom de l'assuré", color="#D33BCE"
                ),
            },
            required=False,
        ),
        # --- Job 3 : transcription d'un champ unique -------------------
        "MONTANT_TOTAL": build_transcription_job(
            instruction="Montant total mentionné, en euros.",
            required=False,
        ),
        # --- Job 4 : zones d'intérêt sur la page -----------------------
        "ZONES_CLES": build_object_detection_job(
            instruction="Entourez les zones à vérifier manuellement.",
            categories={
                "SIGNATURE": build_category("Signature", color="#472CED"),
                "TABLEAU_MONTANTS": build_category(
                    "Tableau des montants", color="#FFB300"
                ),
                "MENTION_MANUSCRITE": build_category(
                    "Mention manuscrite", color="#3CD876"
                ),
            },
            tools=["rectangle"],
            required=False,
        ),
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def list_pdfs() -> list[Path]:
    """Lister tous les PDF de sinistre à traiter.

    On prend ici l'ensemble des PDF d'exemple : l'intérêt d'une interface
    multi-tâches est justement d'absorber des documents hétérogènes.

    Returns:
        Les chemins des PDF, triés.

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
    logger.info("{} PDF importés", len(external_ids))
    return external_ids


# --- 3. Prédictions -------------------------------------------------------


def _pdf_zone(
    *, left: float, top: float, right: float, bottom: float, page: int
) -> dict:
    """Construire la géométrie d'une zone sur une page de PDF.

    Identique à l'exemple 06 : sur un PDF, la géométrie s'exprime avec
    `boundingPoly`, `polys` et `pageNumberArray`.

    Args:
        left: Bord gauche, normalisé.
        top: Bord haut, normalisé.
        right: Bord droit, normalisé.
        bottom: Bord bas, normalisé.
        page: Numéro de page (1 pour la première).

    Returns:
        Le dictionnaire de géométrie.
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

    Le point clé de cet exemple : **une seule** réponse adresse les
    quatre jobs. Le dictionnaire renvoyé a une clé par job rempli, et
    chaque valeur suit la forme du `mlTask` correspondant :

        {
          "TYPE_DOCUMENT":    {"categories": [...]},   # + children
          "ENTITES_DOCUMENT": {"annotations": [...]},  # entités
          "MONTANT_TOTAL":    {"text": "..."},         # transcription
          "ZONES_CLES":       {"annotations": [...]},  # boîtes
        }

    Les jobs qu'un modèle ne sait pas remplir sont simplement absents du
    dictionnaire — il n'est pas nécessaire d'envoyer une clé vide.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Une réponse d'annotation couvrant les quatre jobs.
    """
    external_id = asset["external_id"]
    is_constat = external_id.startswith("constat")

    # --- Job 1 : classification (+ sous-job conditionnel) -------------
    if is_constat:
        type_document = "DECLARATION_SINISTRE"
    elif external_id.startswith("facture"):
        type_document = "FACTURE"
    elif external_id.startswith("attestation"):
        type_document = "ATTESTATION"
    else:
        type_document = "AUTRE"

    categorie_principale: dict = {"name": type_document, "confidence": 84}
    if type_document == "DECLARATION_SINISTRE":
        # Le sous-job se loge dans `children`, sous la catégorie qui le
        # déclenche. Le remplir alors que le parent vaut une autre
        # catégorie produirait une réponse incohérente avec l'interface.
        categorie_principale["children"] = {
            "SOUS_TYPE_SINISTRE": {
                "categories": [{"name": "AUTO", "confidence": 79}]
            }
        }

    response: dict = {"TYPE_DOCUMENT": {"categories": [categorie_principale]}}

    # --- Job 2 : entités nommées --------------------------------------
    # Sur un PDF, une entité porte en plus sa position dans la page ; le
    # couple (beginOffset, content) de l'exemple 08 reste valable pour la
    # partie textuelle.
    response["ENTITES_DOCUMENT"] = {
        "annotations": [
            {
                "categories": [{"name": "NUMERO_CONTRAT", "confidence": 92}],
                "content": "AUTO-2024-1187",
                "mid": "entite-contrat-1",
                "annotations": [
                    _pdf_zone(
                        left=0.30, top=0.30, right=0.62, bottom=0.34, page=1
                    )
                ],
            }
        ]
    }

    # --- Job 3 : transcription ----------------------------------------
    if external_id.startswith("facture"):
        response["MONTANT_TOTAL"] = {"text": "816.00"}

    # --- Job 4 : détection de zones -----------------------------------
    response["ZONES_CLES"] = {
        "annotations": [
            {
                "categories": [{"name": "SIGNATURE", "confidence": 70}],
                "mid": "zone-signature-1",
                "type": "rectangle",
                "content": "",
                "annotations": [
                    _pdf_zone(
                        left=0.60, top=0.80, right=0.90, bottom=0.90, page=1
                    )
                ],
            }
        ]
    }

    return response


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
            description="Traitement multi-tâches d'un PDF de sinistre.",
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
