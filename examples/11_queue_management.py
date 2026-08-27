"""Exemple 11 — Préparer et piloter la file d'annotation.

Besoin métier
    Le service sinistres reçoit un lot de déclarations. Avant de lancer
    l'équipe dessus, il faut : rendre chaque dossier lisible d'un coup
    d'oeil, faire remonter les urgences en tête de file, et répartir le
    travail entre les gestionnaires plutôt que de les laisser piocher
    dans le même tas.

Ce que cet exemple montre
    - la **métadonnée d'asset** dans ses deux temps : à l'import via
      `json_metadata_array`, puis après coup via
      `update_properties_in_assets(json_metadatas=...)` ;
    - les trois clés réservées (`imageUrl`, `text`, `url`) que Kili
      affiche en tête du panneau de métadonnées ;
    - la **priorisation de file** : `priorities`, un entier par asset,
      plus grand = servi en premier ;
    - l'**assignation à un annotateur**, par les deux voies du SDK :
      `assign_assets_to_labelers` (identifiants) et
      `update_properties_in_assets(to_be_labeled_by_array=...)` (emails) ;
    - la relecture de la file avec `kili.assets(metadata_where=...)`.

    L'interface d'annotation n'est pas le sujet ici : elle se réduit à un
    job de triage. Pour les ontologies, voir les exemples 01 à 09.

Usage
    uv run python examples/11_queue_management.py
    uv run python examples/11_queue_management.py --assign \\
        --project-id <id> --labeler-email gestionnaire@exemple.fr
"""

import json

from kili.client import Kili
from loguru import logger

from kili_examples.cli import build_workflow_parser, parse_workflow_steps
from kili_examples.client import get_kili
from kili_examples.interfaces import (
    build_category,
    build_classification_job,
    build_json_interface,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR
from kili_examples.workflow import (
    BRANCH_AUTO,
    build_claim_metadata,
    claim_priority,
    merge_metadata,
    round_robin_assignment,
)

PROJECT_TITLE = "11 - Pilotage de la file d'annotation"
DECLARATIONS_PATH = DATA_DIR / "samples" / "text" / "declarations.jsonl"
EXPORT_PATH = PROCESSED_DIR / "11_queue_management" / "file.json"

# Étapes de cet exemple. Elles remplacent le cycle create/upload/predict/
# export des exemples d'annotation : on ne produit pas de label ici, on
# prépare le terrain pour ceux qui en produiront.
# Rôles d'un membre de projet : ADMIN, TEAM_MANAGER, REVIEWER, LABELER.
# Les deux derniers annotent, les deux premiers pilotent — on ne charge
# donc pas ces derniers de dossiers.
ANNOTATING_ROLES = ("LABELER", "REVIEWER")

STEPS = {
    "create": "Créer le projet Kili.",
    "upload": "Importer les assets avec leurs métadonnées.",
    "enrich": "Compléter les métadonnées après import.",
    "prioritize": "Fixer la priorité de file des assets.",
    "assign": "Répartir les assets entre les annotateurs.",
    "inspect": "Relire la file et l'écrire sur disque.",
}


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire une interface de triage minimale.

    Réduite à sa plus simple expression : cet exemple porte sur la file,
    pas sur l'ontologie.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "TYPE_SINISTRE": build_classification_job(
            instruction="Quel est le type de sinistre déclaré ?",
            categories={
                "SINISTRE_AUTO": build_category(
                    "Sinistre automobile", color="#472CED"
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
    }
    return build_json_interface(jobs)


# --- 2. Assets et métadonnées ---------------------------------------------


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
    """Importer les déclarations avec leurs métadonnées métier.

    Premier des deux temps de la métadonnée : ce qu'on sait **au moment
    de l'import**. `build_claim_metadata` y place un extrait sous la clé
    réservée `text` (affichée en tête du panneau), la branche et la
    priorité calculée, toutes deux filtrables par la suite.

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
        json_metadata_array=[
            build_claim_metadata(item) for item in declarations
        ],
    )
    logger.info("{} déclarations importées", len(external_ids))
    return external_ids


def _fetch_backoffice_records(external_ids: list[str]) -> dict[str, dict]:
    """Simuler la remontée d'informations du back-office contrats.

    Tient lieu d'appel au système de gestion : dans la vraie vie, c'est
    une requête à la base contrats, arrivée après l'import des assets.
    """
    return {
        external_id: {
            "numero_contrat": f"AUTO-2025-{index:04d}",
            "segment_client": "PARTICULIER" if index % 3 else "PROFESSIONNEL",
        }
        for index, external_id in enumerate(external_ids)
    }


def enrich_metadata(kili: Kili, project_id: str) -> None:
    """Compléter la métadonnée des assets déjà importés.

    Second temps de la métadonnée. Le point à retenir :
    `update_properties_in_assets(json_metadatas=...)` reçoit la
    métadonnée **entière** de l'asset — n'envoyer que les nouvelles clés
    effacerait les précédentes. On relit donc l'existant avant de
    fusionner (`merge_metadata`) et de réécrire.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    assets = list(
        kili.assets(
            project_id=project_id,
            fields=["externalId", "jsonMetadata"],
        )
    )
    external_ids = [asset["externalId"] for asset in assets]
    backoffice = _fetch_backoffice_records(external_ids)

    kili.update_properties_in_assets(
        project_id=project_id,
        external_ids=external_ids,
        json_metadatas=[
            merge_metadata(
                asset.get("jsonMetadata"), backoffice[asset["externalId"]]
            )
            for asset in assets
        ],
    )
    logger.info("Métadonnées complétées sur {} assets", len(external_ids))


# --- 3. Priorité de file --------------------------------------------------


def prioritize(kili: Kili, project_id: str) -> None:
    """Fixer la priorité de traitement des assets.

    La priorité est un entier, **plus grand = servi en premier**, les ex
    aequo étant départagés en FIFO sur la date de création. Par défaut,
    tous les assets valent 0.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    declarations = load_declarations()
    priorities = [claim_priority(item["text"]) for item in declarations]

    kili.update_properties_in_assets(
        project_id=project_id,
        external_ids=[item["external_id"] for item in declarations],
        priorities=priorities,
    )
    logger.info(
        "Priorités fixées : {} urgences sur {} assets",
        sum(1 for value in priorities if value > 0),
        len(priorities),
    )


# --- 4. Assignation aux annotateurs ---------------------------------------


def assign(kili: Kili, project_id: str, labeler_emails: list[str]) -> None:
    """Répartir les assets entre les annotateurs du projet.

    Le SDK offre deux chemins, et ils n'attendent **pas** la même chose :

    - `assign_assets_to_labelers(to_be_labeled_by_array=...)` attend des
      **identifiants** d'utilisateurs (`user.id`) ;
    - `update_properties_in_assets(to_be_labeled_by_array=...)` attend
      des **emails**.

    D'où les deux branches ci-dessous : sans `--labeler-email`, on lit
    les membres du projet et on passe par les identifiants ; avec, on
    passe par les emails fournis. Dans les deux cas, le tableau attendu
    est une liste **par asset** des annotateurs autorisés ; une liste
    vide remet l'asset à disposition de toute l'équipe.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
        labeler_emails: Emails imposés en ligne de commande. Vide pour
            répartir sur tous les membres du projet.
    """
    external_ids = [item["external_id"] for item in load_declarations()]

    if labeler_emails:
        kili.update_properties_in_assets(
            project_id=project_id,
            external_ids=external_ids,
            to_be_labeled_by_array=round_robin_assignment(
                external_ids, labeler_emails
            ),
        )
        logger.info(
            "{} assets répartis par email sur {} annotateurs",
            len(external_ids),
            len(labeler_emails),
        )
        return

    members = kili.project_users(
        project_id=project_id,
        fields=["id", "role", "user.id", "user.email"],
    )
    labelers = [
        member for member in members if member["role"] in ANNOTATING_ROLES
    ]
    if not labelers:
        logger.warning(
            "Aucun membre annotant sur ce projet : rien à assigner. "
            "Passez --labeler-email pour forcer un destinataire."
        )
        return

    logger.info(
        "Annotateurs trouvés : {}",
        [member["user"]["email"] for member in labelers],
    )
    kili.assign_assets_to_labelers(
        project_id=project_id,
        external_ids=external_ids,
        to_be_labeled_by_array=round_robin_assignment(
            external_ids, [member["user"]["id"] for member in labelers]
        ),
    )
    logger.info(
        "{} assets répartis sur {} annotateurs",
        len(external_ids),
        len(labelers),
    )


# --- 5. Relecture de la file ----------------------------------------------


def inspect_queue(kili: Kili, project_id: str) -> list[dict]:
    """Relire la file telle que la verront les annotateurs.

    Montre au passage `metadata_where`, le filtre qui donne tout leur
    intérêt aux métadonnées : trois formes acceptées, `{"cle": "valeur"}`
    pour une égalité, `{"cle": ["a", "b"]}` pour un choix, et
    `{"cle": [2, 10]}` pour un intervalle numérique.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Les assets de la branche automobile, triés par priorité
        décroissante.
    """
    assets = list(
        kili.assets(
            project_id=project_id,
            fields=[
                "externalId",
                "priority",
                "jsonMetadata",
                "toBeLabeledBy.user.email",
            ],
            metadata_where={"branche": BRANCH_AUTO},
        )
    )
    assets.sort(key=lambda asset: asset.get("priority", 0), reverse=True)

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(
        json.dumps(assets, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        "{} assets de la branche {} écrits dans {}",
        len(assets),
        BRANCH_AUTO,
        EXPORT_PATH,
    )
    return assets


# --- 6. Orchestration -----------------------------------------------------


def main() -> None:
    """Enchaîner les étapes de préparation de la file."""
    setup_logging()
    parser = build_workflow_parser(__doc__ or PROJECT_TITLE, STEPS)
    parser.add_argument(
        "--labeler-email",
        action="append",
        default=[],
        help=(
            "Email d'un annotateur destinataire. Répétable. Sans cette "
            "option, les assets sont répartis sur les membres du projet."
        ),
    )
    steps, args = parse_workflow_steps(parser, STEPS)

    if not steps["create"] and args.project_id is None:
        parser.error(
            "Sans --create, il faut fournir --project-id pour indiquer sur "
            "quel projet travailler."
        )

    kili = get_kili()
    project_id = args.project_id
    if steps["create"]:
        project = kili.create_project(
            title=PROJECT_TITLE,
            description="Préparation de la file de traitement sinistres.",
            input_type="TEXT",
            json_interface=build_interface(),
        )
        project_id = project["id"]
        logger.info("Projet créé : {}", project_id)

    if project_id is None:
        raise RuntimeError("Aucun project_id disponible.")

    if steps["upload"]:
        upload_assets(kili, project_id)
    if steps["enrich"]:
        enrich_metadata(kili, project_id)
    if steps["prioritize"]:
        prioritize(kili, project_id)
    if steps["assign"]:
        assign(kili, project_id, args.labeler_email)
    if steps["inspect"]:
        inspect_queue(kili, project_id)

    logger.info("Terminé. project_id = {}", project_id)


if __name__ == "__main__":
    main()
