"""Exemple 07 — Extraction de champs d'une facture de réparation (VLM).

Besoin métier
    Extraire automatiquement les champs clés d'une facture de garage
    (numéro, date, immatriculation, montant TTC, franchise) pour
    rapprocher la facture du dossier de sinistre.

Ce que cet exemple montre
    - le passage **sortie de modèle → JSON Kili** : un VLM (ou un moteur
      d'OCR) renvoie typiquement un dictionnaire plat
      `{"montant_ttc": "816.00", ...}` ; tout l'enjeu est de le traduire
      dans la structure attendue par Kili ;
    - un job TRANSCRIPTION par champ, sans zone : quand seule la valeur
      compte et pas sa position, inutile de faire dessiner des boîtes.
      C'est plus simple à annoter et à corriger que l'exemple 06 ;
    - la gestion des champs que le modèle n'a pas su lire : on n'émet
      **pas** de clé pour ces jobs plutôt que d'envoyer une chaîne vide.

Usage
    uv run python examples/07_vlm_text_extraction.py
"""

from pathlib import Path

from kili.client import Kili
from loguru import logger

from kili_examples.assets import external_id_from_path
from kili_examples.cli import build_parser, parse_steps
from kili_examples.client import get_kili
from kili_examples.exports import export_labels_to_json
from kili_examples.interfaces import (
    build_json_interface,
    build_transcription_job,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR

PROJECT_TITLE = "07 - Extraction des champs de facture"
PDF_DIR = DATA_DIR / "samples" / "pdf"
EXPORT_PATH = PROCESSED_DIR / "07_vlm_text_extraction" / "labels.json"
MODEL_NAME = "vlm-extraction-facture-v0"

# Correspondance entre les clés que renvoie le modèle et les noms de jobs
# Kili. Isoler cette table rend explicite le contrat d'interface entre le
# modèle et l'ontologie : c'est le seul endroit à modifier si l'un des
# deux évolue.
FIELD_TO_JOB = {
    "numero_facture": "NUMERO_FACTURE",
    "date_facture": "DATE_FACTURE",
    "immatriculation": "IMMATRICULATION",
    "montant_ttc": "MONTANT_TTC",
    "franchise": "MONTANT_FRANCHISE",
}


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` d'extraction de champs.

    Un job TRANSCRIPTION par champ à relever. Tous sont à la racine :
    aucun n'est conditionnel, l'annotateur voit un formulaire complet.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "NUMERO_FACTURE": build_transcription_job(
            instruction="Numéro de la facture"
        ),
        "DATE_FACTURE": build_transcription_job(
            instruction="Date de la facture (JJ/MM/AAAA)"
        ),
        "IMMATRICULATION": build_transcription_job(
            instruction="Immatriculation du véhicule"
        ),
        "MONTANT_TTC": build_transcription_job(
            instruction="Montant total TTC en euros"
        ),
        "MONTANT_FRANCHISE": build_transcription_job(
            instruction="Montant de la franchise déduite",
            # Toutes les factures ne mentionnent pas de franchise.
            required=False,
        ),
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def list_pdfs() -> list[Path]:
    """Lister les factures à traiter.

    Returns:
        Les chemins des factures, triés.

    Raises:
        FileNotFoundError: Si aucune facture n'a été générée.
    """
    pdfs = sorted(PDF_DIR.glob("facture_reparation_*.pdf"))
    if not pdfs:
        raise FileNotFoundError(
            f"Aucune facture dans {PDF_DIR}. Lancez d'abord : "
            "uv run python scripts/generate_sample_data.py"
        )
    return pdfs


def upload_assets(kili: Kili, project_id: str) -> list[str]:
    """Importer les factures comme assets PDF.

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
    logger.info("{} factures importées", len(external_ids))
    return external_ids


# --- 3. Prédictions -------------------------------------------------------


def run_vlm(asset: dict) -> dict[str, str | None]:
    """Sortie factice d'un VLM — TODO: brancher votre modèle ici.

    Simule ce que renvoie un modèle vision-langage interrogé sur la
    facture : un dictionnaire plat, avec `None` pour les champs non
    trouvés. C'est le format « naturel » d'un modèle, volontairement
    différent de celui attendu par Kili.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Les champs extraits, indexés par les clés de `FIELD_TO_JOB`.
    """
    return {
        "numero_facture": "F-2025-0481",
        "date_facture": "12/03/2025",
        "immatriculation": "AB-274-CD",
        "montant_ttc": "816.00",
        # Champ que le modèle n'a pas su lire.
        "franchise": None,
    }


def predict(asset: dict) -> dict:
    """Convertir la sortie du modèle en réponse Kili.

    C'est la fonction à lire en priorité dans cet exemple : elle montre
    la traduction d'un dictionnaire plat de modèle vers l'arbre de jobs
    attendu par Kili.

    Règles appliquées :

    - un job TRANSCRIPTION répond `{"text": "<valeur>"}` ;
    - les champs non extraits (`None`) sont **omis** : Kili n'affiche
      alors simplement aucune pré-annotation pour ce job, ce qui se
      distingue clairement d'une valeur lue comme vide ;
    - les valeurs sont converties en `str`, le champ `text` n'acceptant
      pas de nombre.

    Args:
        asset: Enregistrement `{"external_id": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie.
    """
    model_output = run_vlm(asset)

    response = {}
    for field_name, job_name in FIELD_TO_JOB.items():
        value = model_output.get(field_name)
        if value is None:
            continue
        response[job_name] = {"text": str(value)}
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
            description="Extraction des champs clés d'une facture.",
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
