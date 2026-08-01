"""Export des annotations d'un projet Kili.

Deux façons de récupérer les annotations, à choisir selon l'usage.

`kili.labels(...)` — lecture « brute »
    Renvoie les labels tels qu'ils sont stockés : un `jsonResponse` par
    label, exactement dans le format décrit par les exemples de ce dépôt.
    À privilégier pour inspecter, déboguer, ou réinjecter les annotations
    dans un traitement maison. C'est ce que fait `export_labels_to_json`.

`kili.export_labels(...)` — export « format d'entraînement »
    Écrit directement une archive dans un format consommable par les
    frameworks de vision : `yolo_v4`, `yolo_v5`, `yolo_v7`, `yolo_v8`,
    `coco`, `pascal_voc`, `geojson`, plus `kili`/`raw` (le format natif).
    Ces formats ne couvrent que les tâches qu'ils savent représenter :
    COCO et Pascal VOC pour les boîtes et polygones, YOLO pour les
    boîtes. Un job TRANSCRIPTION ou NER n'y a pas d'équivalent — pour
    ces tâches, restez sur le format natif.

Ce dépôt exporte en JSON natif (choix figé) ; les formats ci-dessus sont
mentionnés pour que l'équipe sache où regarder le jour où un modèle de
détection devra être entraîné.
"""

import json
from pathlib import Path
from typing import Any

from kili.client import Kili
from loguru import logger


def export_labels_to_json(
    kili: Kili,
    project_id: str,
    output_path: Path,
) -> list[dict[str, Any]]:
    """Récupérer les labels d'un projet et les écrire sur disque en JSON.

    Utilise `kili.labels(...)`, qui renvoie le format natif Kili — celui
    que les fonctions `predict()` des exemples produisent. On garde donc
    une symétrie exacte entre ce qu'on envoie et ce qu'on relit.

    Args:
        kili: Client Kili authentifié.
        project_id: Identifiant du projet à exporter.
        output_path: Fichier JSON de destination. Les dossiers parents
            sont créés si nécessaire.

    Returns:
        La liste des labels récupérés.
    """
    # `fields` est explicite : par défaut le SDK en renvoie davantage, et
    # nommer les champs documente ce dont on a réellement besoin.
    labels = list(
        kili.labels(
            project_id=project_id,
            fields=[
                "id",
                "jsonResponse",
                "labelType",
                "author.email",
                "assetId",
            ],
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("{} labels exportés vers {}", len(labels), output_path)
    return labels
