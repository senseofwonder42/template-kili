"""Exemple 01 — Triage des déclarations de sinistre (texte).

Besoin métier
    Classer automatiquement les déclarations de sinistre reçues par écrit
    afin de les router vers la bonne équipe de gestion. Un second job,
    conditionnel, précise le sous-type quand il s'agit d'un sinistre auto.

Ce que cet exemple montre
    - un job CLASSIFICATION mono-classe (`input: "radio"`) ;
    - un sous-job déclenché par une catégorie (classification hiérarchique) ;
    - l'import d'assets TEXT (le contenu est le texte lui-même) ;
    - la forme exacte d'une prédiction de classification, y compris pour
      le sous-job (clé `children`).

Usage
    uv run python examples/01_text_classification.py
    uv run python examples/01_text_classification.py --export --project-id <id>
"""

import json
from pathlib import Path

from kili.client import Kili
from loguru import logger

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

PROJECT_TITLE = "01 - Triage des declarations de sinistre"
DECLARATIONS_PATH = DATA_DIR / "samples" / "text" / "declarations.jsonl"
EXPORT_PATH = PROCESSED_DIR / "01_text_classification" / "labels.json"

# Nom du modèle associé aux prédictions. Il apparaît dans l'interface Kili
# et permet de comparer plusieurs versions de modèle sur le même projet.
MODEL_NAME = "triage-sinistres-v0"


# --- 1. Interface d'annotation (ontologie) --------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` du projet de triage.

    Deux jobs :

    - `CLASSIFICATION_SINISTRE` : le type de sinistre. La catégorie
      `SINISTRE_AUTO` déclare `children=["SOUS_TYPE_AUTO"]`, ce qui rend
      le second job visible uniquement lorsqu'elle est sélectionnée.
    - `SOUS_TYPE_AUTO` : sous-job (`isChild=True`) précisant la nature du
      sinistre automobile.

    Returns:
        Le `json_interface` complet, prêt pour `create_project`.
    """
    jobs = {
        "CLASSIFICATION_SINISTRE": build_classification_job(
            instruction="Quel est le type de sinistre déclaré ?",
            categories={
                "SINISTRE_AUTO": build_category(
                    "Sinistre automobile",
                    # C'est ici que se noue la hiérarchie : cocher cette
                    # catégorie fait apparaître le job SOUS_TYPE_AUTO.
                    children=["SOUS_TYPE_AUTO"],
                    color="#472CED",
                ),
                "DEGAT_DES_EAUX": build_category(
                    "Dégât des eaux", color="#3CD876"
                ),
                "VOL": build_category("Vol", color="#D33BCE"),
                "BRIS_DE_GLACE": build_category(
                    "Bris de glace", color="#FFB300"
                ),
            },
            input_type="radio",
        ),
        "SOUS_TYPE_AUTO": build_classification_job(
            instruction="Précisez la nature du sinistre automobile.",
            categories={
                "COLLISION": build_category("Collision avec un tiers"),
                "STATIONNEMENT": build_category("Dommage en stationnement"),
                "VOL_VEHICULE": build_category("Vol du véhicule"),
            },
            input_type="radio",
            # Un sous-job est rarement obligatoire : l'annotateur ne le
            # voit que dans une branche de l'arbre.
            required=False,
            is_child=True,
        ),
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def load_declarations() -> list[dict]:
    """Charger les déclarations synthétiques depuis le JSONL.

    Returns:
        La liste des enregistrements `{"external_id": ..., "text": ...}`.

    Raises:
        FileNotFoundError: Si les données d'exemple n'ont pas été générées.
    """
    if not DECLARATIONS_PATH.exists():
        raise FileNotFoundError(
            f"{DECLARATIONS_PATH} est introuvable. Lancez d'abord : "
            "uv run python scripts/generate_sample_data.py"
        )
    lines = DECLARATIONS_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def upload_assets(kili: Kili, project_id: str) -> list[str]:
    """Importer les déclarations comme assets TEXT.

    Pour un projet TEXT, `content_array` contient directement le texte
    de l'asset (et non un chemin ou une URL comme pour IMAGE/PDF).

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Les `external_id` importés.
    """
    declarations = load_declarations()
    external_ids = [item["external_id"] for item in declarations]

    kili.append_many_to_dataset(
        project_id=project_id,
        content_array=[item["text"] for item in declarations],
        external_id_array=external_ids,
    )
    logger.info("{} déclarations importées", len(external_ids))
    return external_ids


# --- 3. Prédictions -------------------------------------------------------


def predict(asset: dict) -> dict:
    """Prédiction factice — TODO: brancher votre modèle ici.

    La valeur pédagogique de cette fonction est la *forme* du
    dictionnaire renvoyé, pas la qualité de la règle de décision.

    Structure d'une réponse de classification :

        {
          "NOM_DU_JOB": {
            "categories": [
              {"name": "CLE_DE_CATEGORIE", "confidence": 92}
            ]
          }
        }

    - `name` reprend **la clé** de la catégorie dans le json_interface
      (`SINISTRE_AUTO`), pas son libellé affiché ("Sinistre automobile").
    - `confidence` est un entier de 0 à 100. Il est facultatif pour une
      annotation humaine, mais recommandé pour une prédiction : Kili
      l'affiche et permet de filtrer les assets peu sûrs.
    - Pour un job `checkbox` (multi-label), la liste `categories`
      contient simplement plusieurs entrées.

    Args:
        asset: Enregistrement `{"external_id": ..., "text": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie de cet exemple.
    """
    text = asset["text"].lower()

    # Règle factice tenant lieu de modèle.
    if "eau" in text or "infiltration" in text or "inondé" in text:
        category = "DEGAT_DES_EAUX"
    elif "vol" in text:
        category = "VOL"
    elif "pare-brise" in text or "gravillon" in text:
        category = "BRIS_DE_GLACE"
    else:
        category = "SINISTRE_AUTO"

    response = {
        "CLASSIFICATION_SINISTRE": {
            "categories": [{"name": category, "confidence": 90}]
        }
    }

    # Le sous-job ne se remplit que dans la branche « auto ». Un sous-job
    # de classification se loge sous la clé `children` de la catégorie
    # parente qui le déclenche — et non à la racine de la réponse.
    # (Le SDK 2.176.1 sait lire `children` aussi bien sur une catégorie
    # que sur une annotation de détection : voir exemple 09.)
    if category == "SINISTRE_AUTO":
        sous_type = "STATIONNEMENT" if "parking" in text else "COLLISION"
        response["CLASSIFICATION_SINISTRE"]["categories"][0]["children"] = {
            "SOUS_TYPE_AUTO": {
                "categories": [{"name": sous_type, "confidence": 80}]
            }
        }

    return response


def upload_predictions(kili: Kili, project_id: str) -> None:
    """Importer les prédictions factices dans le projet.

    `create_predictions` crée des labels de type PREDICTION : ils
    s'affichent comme pré-annotations que l'annotateur corrige, et ne
    comptent pas comme du travail humain terminé.

    À distinguer des labels de type INFERENCE (via `append_labels(
    label_type="INFERENCE")`), utilisés pour comparer les sorties d'un
    modèle aux annotations humaines sans les proposer à la correction.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    declarations = load_declarations()

    kili.create_predictions(
        project_id=project_id,
        external_id_array=[item["external_id"] for item in declarations],
        json_response_array=[predict(item) for item in declarations],
        # `model_name` s'applique à toutes les prédictions du lot.
        model_name=MODEL_NAME,
    )
    logger.info("{} prédictions importées", len(declarations))


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
            description="Triage automatique des déclarations de sinistre.",
            # Le type d'entrée conditionne l'éditeur affiché dans Kili.
            input_type="TEXT",
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
