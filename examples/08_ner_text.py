"""Exemple 08 — Entités nommées dans un email client (NER, texte).

Besoin métier
    Repérer dans les emails entrants les informations structurantes
    (numéro de contrat, montant, date, nom du conseiller) afin de
    pré-remplir la fiche de traitement du courrier.

Ce que cet exemple montre
    - un job NAMED_ENTITIES_RECOGNITION sur un asset TEXT ;
    - le repérage par **offsets de caractères** : `beginOffset` +
      `content`, et non des coordonnées géométriques ;
    - le piège des offsets : ils se comptent en caractères Python sur le
      texte exact envoyé à Kili. Un décalage d'un caractère (accent mal
      encodé, espace en trop) déplace le surlignage. On calcule donc les
      offsets avec `str.find`, jamais à la main.

Usage
    uv run python examples/08_ner_text.py
"""

import json
import re
from pathlib import Path

from kili.client import Kili
from loguru import logger

from kili_examples.cli import build_parser, parse_steps
from kili_examples.client import get_kili
from kili_examples.exports import export_labels_to_json
from kili_examples.interfaces import (
    build_category,
    build_json_interface,
    build_ner_job,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR

PROJECT_TITLE = "08 - Entites nommees dans les emails clients"
EMAILS_PATH = DATA_DIR / "samples" / "text" / "emails.jsonl"
EXPORT_PATH = PROCESSED_DIR / "08_ner_text" / "labels.json"
MODEL_NAME = "ner-emails-v0"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` de reconnaissance d'entités.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "ENTITES_EMAIL": build_ner_job(
            instruction="Surlignez les entités utiles au traitement.",
            categories={
                "NUMERO_CONTRAT": build_category(
                    "Numéro de contrat", color="#472CED"
                ),
                "MONTANT": build_category("Montant", color="#3CD876"),
                "DATE_SINISTRE": build_category(
                    "Date de sinistre", color="#FFB300"
                ),
                "NOM_CONSEILLER": build_category(
                    "Nom du conseiller", color="#D33BCE"
                ),
            },
        )
    }
    return build_json_interface(jobs)


# --- 2. Assets ------------------------------------------------------------


def load_emails() -> list[dict]:
    """Charger les emails synthétiques.

    Returns:
        La liste des enregistrements `{"external_id": ..., "text": ...}`.

    Raises:
        FileNotFoundError: Si les données d'exemple n'ont pas été générées.
    """
    if not EMAILS_PATH.exists():
        raise FileNotFoundError(
            f"{EMAILS_PATH} est introuvable. Lancez d'abord : "
            "uv run python scripts/generate_sample_data.py"
        )
    lines = EMAILS_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def upload_assets(kili: Kili, project_id: str) -> list[str]:
    """Importer les emails comme assets TEXT.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Les `external_id` importés.
    """
    emails = load_emails()
    external_ids = [item["external_id"] for item in emails]

    kili.append_many_to_dataset(
        project_id=project_id,
        content_array=[item["text"] for item in emails],
        external_id_array=external_ids,
    )
    logger.info("{} emails importés", len(external_ids))
    return external_ids


# --- 3. Prédictions -------------------------------------------------------

# Motifs factices tenant lieu de modèle NER. Un vrai modèle renverrait
# directement des spans ; ces expressions régulières produisent la même
# information (catégorie + position) sans dépendance lourde.
ENTITY_PATTERNS = [
    ("NUMERO_CONTRAT", re.compile(r"\b(?:AUTO|MRH)-\d{4}-\d{4}\b")),
    ("MONTANT", re.compile(r"\b\d+\s*euros\b")),
    ("DATE_SINISTRE", re.compile(r"\b\d{2}/\d{2}/\d{4}\b")),
    ("NOM_CONSEILLER", re.compile(r"\b(?:M\.|Mme)\s+[A-ZÉÈ][a-zéèêàç]+")),
]


def build_entity_annotation(
    *, category: str, text: str, begin_offset: int, index: int
) -> dict:
    """Construire une annotation d'entité nommée.

    Structure attendue par Kili pour une entité sur asset TEXT :

        {
          "categories": [{"name": "NUMERO_CONTRAT", "confidence": 95}],
          "beginOffset": 42,
          "content": "AUTO-2024-1187",
          "mid": "entite-0"
        }

    - `beginOffset` est l'index du **premier caractère** de l'entité dans
      le texte de l'asset, compté à partir de 0 ;
    - `content` est le texte exact surligné. Sa longueur détermine la fin
      de l'entité — il n'y a pas de `endOffset` à fournir à l'import ;
    - `content` doit correspondre exactement à
      `texte[beginOffset:beginOffset + len(content)]`, sans quoi le
      surlignage sera décalé dans l'interface.

    Args:
        category: Clé de la catégorie dans le json_interface.
        text: Texte exact de l'entité.
        begin_offset: Position du premier caractère dans l'asset.
        index: Rang de l'entité, pour fabriquer un `mid` unique.

    Returns:
        Le dictionnaire de l'annotation.
    """
    return {
        "categories": [{"name": category, "confidence": 90}],
        "beginOffset": begin_offset,
        "content": text,
        "mid": f"entite-{index}",
    }


def predict(asset: dict) -> dict:
    """Prédiction factice — TODO: brancher votre modèle ici.

    Les offsets sont calculés par `re.finditer` sur le texte exact de
    l'asset : c'est la seule façon fiable de garantir la cohérence entre
    `beginOffset` et `content`.

    Args:
        asset: Enregistrement `{"external_id": ..., "text": ...}`.

    Returns:
        Une réponse d'annotation conforme à l'ontologie.
    """
    text = asset["text"]

    annotations = []
    for category, pattern in ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            annotations.append(
                build_entity_annotation(
                    category=category,
                    text=match.group(0),
                    begin_offset=match.start(),
                    index=len(annotations),
                )
            )

    return {"ENTITES_EMAIL": {"annotations": annotations}}


def upload_predictions(kili: Kili, project_id: str) -> None:
    """Importer les prédictions factices.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    emails = load_emails()

    kili.create_predictions(
        project_id=project_id,
        external_id_array=[item["external_id"] for item in emails],
        json_response_array=[predict(item) for item in emails],
        model_name=MODEL_NAME,
    )
    logger.info("{} prédictions importées", len(emails))


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
            description="Extraction d'entités dans les emails clients.",
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
