"""Exemple 12 — Boucle qualité : questions et issues.

Besoin métier
    Un gestionnaire bute sur une déclaration ambiguë et veut l'avis d'un
    référent : c'est une **question**. Un relecteur, lui, conteste une
    annotation précise — la mauvaise zone de dégât a été encadrée : c'est
    une **issue**. Le responsable qualité veut à tout moment l'état de
    cette boucle, et clôturer ce qui a été traité.

Ce que cet exemple montre
    - la différence de rattachement : une **question** vise un *asset*
      (`create_questions`), une **issue** vise un *label*, voire un objet
      précis de ce label via son `mid` (`create_issues`) ;
    - que `kili.issues(...)` renvoie **les deux** — le champ `type`
      (`ISSUE` / `QUESTION`) les sépare, d'où le résumé produit ici ;
    - le cycle de vie d'une issue : `OPEN`, `SOLVED`, `CANCELLED`, piloté
      par `update_issue_status` ;
    - le filtre `kili.assets(issue_type=..., issue_status=...)`, qui
      ramène les assets restant à traiter.

    À noter : la documentation Kili décrit cette boucle côté interface
    seulement. Tout ce qui suit est lu dans le SDK 2.176.1.

Usage
    Cet exemple travaille sur un projet **déjà annoté** : une boucle
    qualité n'a pas de sens sans label à contester. Prenez le projet
    d'un exemple précédent — le 04 est idéal, ses labels contiennent des
    objets avec des `mid`.

    uv run python examples/12_issues_and_questions.py --project-id <id>
    uv run python examples/12_issues_and_questions.py --resolve \\
        --project-id <id>
"""

import json

from kili.client import Kili
from loguru import logger

from kili_examples.cli import build_workflow_parser, parse_workflow_steps
from kili_examples.client import get_kili
from kili_examples.logging import setup_logging
from kili_examples.paths import PROCESSED_DIR
from kili_examples.workflow import first_object_mid, summarize_issues

PROJECT_TITLE = "12 - Boucle qualité"
REPORT_PATH = PROCESSED_DIR / "12_issues_and_questions" / "qualite.json"

# Nombre d'assets et de labels sur lesquels l'exemple intervient. Il
# s'agit d'une démonstration : on ne saisit pas une question sur toute la
# base.
SAMPLE_SIZE = 3

# `--resolve` écrit sur la plateforme (il clôt des issues ouvertes) : il
# est volontairement tenu hors du chemin par défaut.
STEPS = {
    "ask": "Poser des questions sur des assets.",
    "flag": "Ouvrir des issues sur des labels existants.",
    "list": "Lister questions et issues, et écrire le rapport.",
    "resolve": "Clôturer les issues ouvertes (non joué par défaut).",
}
DEFAULT_STEPS = ("ask", "flag", "list")


# --- 1. Questions : rattachées à un asset ---------------------------------


def ask_questions(kili: Kili, project_id: str) -> None:
    """Poser des questions sur les premiers assets du projet.

    Une question part de l'annotateur et remonte vers un référent. Elle
    se rattache à un **asset**, pas à un label : on peut la poser avant
    même d'avoir annoté quoi que ce soit.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    assets = list(
        kili.assets(
            project_id=project_id,
            fields=["id", "externalId"],
            first=SAMPLE_SIZE,
        )
    )
    if not assets:
        logger.warning("Projet sans asset : aucune question à poser.")
        return

    kili.create_questions(
        project_id=project_id,
        asset_id_array=[asset["id"] for asset in assets],
        text_array=[
            f"Dossier {asset['externalId']} : le sinistre semble relever "
            "de deux garanties. Laquelle retenir ?"
            for asset in assets
        ],
    )
    logger.info("{} questions posées", len(assets))


# --- 2. Issues : rattachées à un label, voire à un objet ------------------


def flag_labels(kili: Kili, project_id: str) -> None:
    """Ouvrir une issue sur les premiers labels du projet.

    Une issue part du relecteur et vise un **label**. Elle peut viser
    plus finement un objet de ce label — une boîte, un polygone, une
    entité — en passant son `mid` dans `object_mid_array` : c'est ce qui
    fait apparaître le signalement directement sur l'objet dans
    l'interface. `first_object_mid` renvoie `None` pour un label de pure
    classification, et l'issue porte alors sur le label entier.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    labels = list(
        kili.labels(
            project_id=project_id,
            fields=["id", "assetId", "jsonResponse", "labelType"],
            first=SAMPLE_SIZE,
        )
    )
    if not labels:
        logger.warning(
            "Projet sans label : rien à contester. Annotez d'abord un "
            "asset, ou lancez cet exemple sur le projet de l'exemple 04."
        )
        return

    mids = [first_object_mid(label["jsonResponse"]) for label in labels]
    kili.create_issues(
        project_id=project_id,
        label_id_array=[label["id"] for label in labels],
        object_mid_array=mids,
        text_array=[
            "La zone encadrée ne correspond pas au dégât décrit dans la "
            "déclaration. À reprendre."
            if mid
            else "Le type de sinistre retenu contredit la déclaration."
            for mid in mids
        ],
    )
    logger.info(
        "{} issues ouvertes, dont {} visant un objet précis",
        len(labels),
        sum(1 for mid in mids if mid),
    )


# --- 3. Lecture : questions et issues arrivent ensemble -------------------


def list_issues(kili: Kili, project_id: str) -> dict:
    """Dresser l'état de la boucle qualité.

    `kili.issues(...)` ne distingue pas les deux objets : un `Issue`
    représente aussi bien une issue qu'une question, et c'est `type` qui
    tranche. On peut soit tout lire et trier après coup (ce que fait
    `summarize_issues`), soit demander un seul type au serveur via
    `issue_type=`.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Le rapport écrit sur disque.
    """
    issues = list(
        kili.issues(
            project_id=project_id,
            fields=["id", "type", "status", "assetId", "objectMid"],
        )
    )
    report = summarize_issues(issues)

    # Deux compteurs serveur, pour montrer le filtre côté API plutôt que
    # côté client.
    report["questions_ouvertes"] = kili.count_issues(
        project_id=project_id, issue_type="QUESTION", status="OPEN"
    )
    report["issues_ouvertes"] = kili.count_issues(
        project_id=project_id, issue_type="ISSUE", status="OPEN"
    )

    # Le même filtre existe côté assets : c'est la requête à donner à un
    # relecteur qui veut sa liste de reprises.
    blocked = list(
        kili.assets(
            project_id=project_id,
            fields=["externalId"],
            issue_type="ISSUE",
            issue_status="OPEN",
        )
    )
    report["assets_bloques"] = [asset["externalId"] for asset in blocked]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        "{} éléments ({} issues ouvertes, {} questions ouvertes). "
        "Rapport écrit dans {}",
        report["total"],
        report["issues_ouvertes"],
        report["questions_ouvertes"],
        REPORT_PATH,
    )
    return report


# --- 4. Clôture -----------------------------------------------------------


def resolve_issues(kili: Kili, project_id: str) -> None:
    """Clôturer les issues ouvertes du projet.

    Trois statuts existent : `OPEN`, `SOLVED` (le signalement a été
    traité) et `CANCELLED` (il n'avait pas lieu d'être). On ne touche pas
    aux questions : y répondre relève de l'interface, pas d'un script.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    issues = list(
        kili.issues(
            project_id=project_id,
            fields=["id"],
            issue_type="ISSUE",
            status="OPEN",
        )
    )
    for issue in issues:
        kili.update_issue_status(issue_id=issue["id"], status="SOLVED")
    logger.info("{} issues clôturées", len(issues))


# --- 5. Orchestration -----------------------------------------------------


def main() -> None:
    """Enchaîner les étapes de la boucle qualité."""
    setup_logging()
    parser = build_workflow_parser(
        __doc__ or PROJECT_TITLE, STEPS, require_project_id=True
    )
    steps, args = parse_workflow_steps(
        parser, STEPS, default_steps=DEFAULT_STEPS
    )

    kili = get_kili()
    project_id = args.project_id

    if steps["ask"]:
        ask_questions(kili, project_id)
    if steps["flag"]:
        flag_labels(kili, project_id)
    if steps["list"]:
        list_issues(kili, project_id)
    if steps["resolve"]:
        resolve_issues(kili, project_id)

    logger.info("Terminé. project_id = {}", project_id)


if __name__ == "__main__":
    main()
