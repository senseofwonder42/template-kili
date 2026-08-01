"""Import d'assets dans un projet Kili.

Deux besoins reviennent dans plusieurs exemples :

1. envoyer une longue liste d'assets sans saturer l'API (découpage en lots) ;
2. fabriquer un `external_id` stable à partir d'un chemin de fichier.

Le reste (quel `content_array` pour quel type d'asset) reste dans les
exemples, car c'est justement ce que le lecteur doit apprendre.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from kili.client import Kili
from loguru import logger

# Taille de lot par défaut.
#
# Pourquoi 100 ? C'est la valeur qu'utilise le SDK Kili lui-même pour ses
# propres mutations (`MUTATION_BATCH_SIZE` dans kili/core/constants.py,
# version 2.176.1). S'aligner dessus évite d'envoyer des requêtes GraphQL
# trop lourdes (timeouts côté serveur on-premise) sans multiplier les
# allers-retours réseau.
#
# À noter : `append_many_to_dataset` gère déjà un découpage interne. Ce
# helper reste utile pour (a) journaliser la progression lot par lot sur
# de gros imports, et (b) garder une trace explicite des identifiants
# créés, ce qui aide au diagnostic lors du premier run sur le serveur.
DEFAULT_BATCH_SIZE = 100


def external_id_from_path(path: Path) -> str:
    """Dériver un `external_id` lisible depuis un chemin de fichier.

    L'`external_id` est l'identifiant métier d'un asset dans Kili : c'est
    lui qui permet de réimporter des prédictions sans connaître l'ID
    interne Kili. On retient le nom du fichier sans extension, ce qui
    reste lisible dans l'interface et stable entre deux exécutions.

    Args:
        path: Chemin du fichier source.

    Returns:
        Le nom du fichier sans son extension (ex. `constat_001`).
    """
    return path.stem


def _batches(items: list[Any], size: int) -> Iterator[list[Any]]:
    """Découper une liste en lots de taille `size`."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def upload_assets_in_batches(
    kili: Kili,
    project_id: str,
    *,
    content_array: list[Any],
    external_id_array: list[str],
    json_metadata_array: list[dict] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[str]:
    """Importer des assets par lots dans un projet Kili.

    Enveloppe fine autour de `kili.append_many_to_dataset(...)` : elle
    n'ajoute que le découpage en lots et la journalisation. Les exemples
    appellent la méthode du SDK directement quand la liste est courte.

    Args:
        kili: Client Kili authentifié.
        project_id: Identifiant du projet cible.
        content_array: Contenus des assets. Selon le type de projet, il
            s'agit d'URLs, de chemins locaux (IMAGE, PDF) ou du texte
            lui-même (TEXT).
        external_id_array: Identifiants métier, un par asset. Doit avoir
            la même longueur que `content_array`.
        json_metadata_array: Métadonnées libres, une entrée par asset.
        batch_size: Nombre d'assets envoyés par requête.

    Returns:
        La liste des `external_id` effectivement envoyés.

    Raises:
        ValueError: Si les listes fournies n'ont pas la même longueur.
    """
    if len(content_array) != len(external_id_array):
        raise ValueError(
            "content_array et external_id_array doivent avoir la même "
            f"longueur ({len(content_array)} != {len(external_id_array)})."
        )
    if json_metadata_array is not None and len(json_metadata_array) != len(
        content_array
    ):
        raise ValueError(
            "json_metadata_array doit avoir la même longueur que "
            f"content_array ({len(json_metadata_array)} != "
            f"{len(content_array)})."
        )

    indices = list(range(len(content_array)))
    for batch_number, batch_indices in enumerate(
        _batches(indices, batch_size), start=1
    ):
        logger.info(
            "Import du lot {} ({} assets)", batch_number, len(batch_indices)
        )
        kili.append_many_to_dataset(
            project_id=project_id,
            content_array=[content_array[i] for i in batch_indices],
            external_id_array=[external_id_array[i] for i in batch_indices],
            json_metadata_array=(
                [json_metadata_array[i] for i in batch_indices]
                if json_metadata_array is not None
                else None
            ),
        )

    logger.info("{} assets importés au total", len(external_id_array))
    return external_id_array
