"""Options de ligne de commande communes aux neuf exemples.

Chaque exemple expose le même cycle en quatre étapes :

    --create    créer le projet et son interface d'annotation
    --upload    importer les assets
    --predict   importer les prédictions (pré-annotations)
    --export    exporter les annotations

Sans aucun de ces drapeaux, les quatre étapes s'enchaînent.

`--project-id` permet de rejouer une étape sur un projet existant plutôt
que d'en créer un nouveau à chaque exécution : c'est ce qui rend les
scripts ré-exécutables sans polluer l'instance de projets jetables.
"""

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Steps:
    """Étapes du cycle de vie à exécuter."""

    create: bool
    upload: bool
    predict: bool
    export: bool
    project_id: str | None


def build_parser(description: str) -> argparse.ArgumentParser:
    """Construire le parseur d'arguments commun aux exemples.

    Args:
        description: Description de l'exemple, affichée par `--help`.

    Returns:
        Le parseur configuré.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--create", action="store_true", help="Créer le projet Kili."
    )
    parser.add_argument(
        "--upload", action="store_true", help="Importer les assets."
    )
    parser.add_argument(
        "--predict",
        action="store_true",
        help="Importer les prédictions factices.",
    )
    parser.add_argument(
        "--export", action="store_true", help="Exporter les annotations."
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help=(
            "Réutiliser un projet existant au lieu d'en créer un. "
            "Obligatoire si --create n'est pas demandé."
        ),
    )
    return parser


def parse_steps(parser: argparse.ArgumentParser) -> Steps:
    """Lire les arguments et en déduire les étapes à exécuter.

    Args:
        parser: Parseur construit par `build_parser`.

    Returns:
        Les étapes demandées. Si aucun drapeau d'étape n'est fourni, les
        quatre étapes sont activées.

    Raises:
        SystemExit: Si une étape a besoin d'un projet sans que
            `--create` ni `--project-id` ne soit fourni.
    """
    args = parser.parse_args()
    no_flag = not (args.create or args.upload or args.predict or args.export)

    steps = Steps(
        create=args.create or no_flag,
        upload=args.upload or no_flag,
        predict=args.predict or no_flag,
        export=args.export or no_flag,
        project_id=args.project_id,
    )

    if not steps.create and steps.project_id is None:
        parser.error(
            "Sans --create, il faut fournir --project-id pour indiquer sur "
            "quel projet travailler."
        )
    return steps
