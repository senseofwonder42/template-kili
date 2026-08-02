"""Options de ligne de commande communes aux dix exemples.

Chaque exemple expose le même cycle en quatre étapes :

    --create    créer le projet et son interface d'annotation
    --upload    importer les assets
    --predict   importer les prédictions (pré-annotations)
    --export    exporter les annotations

Sans aucun de ces drapeaux, les quatre étapes s'enchaînent.

`--project-id` permet de rejouer une étape sur un projet existant plutôt
que d'en créer un nouveau à chaque exécution : c'est ce qui rend les
scripts ré-exécutables sans polluer l'instance de projets jetables.

L'exemple 10 ajoute deux options qui lui sont propres (`--scope` et
`--sample-size`) via `with_scope=True` : elles ne concernent que la
revue d'un jeu d'évaluation RAG, pas les neuf autres exemples.
"""

import argparse
from dataclasses import dataclass

# Périmètres de revue proposés par `--scope`.
# - rejected : uniquement les cas rejetés par le LLM-as-judge
# - all      : toutes les questions, pour auditer aussi ses validations
# - sample   : les rejets, plus un échantillon de cas validés
SCOPE_CHOICES = ("rejected", "all", "sample")
DEFAULT_SAMPLE_SIZE = 10


@dataclass(frozen=True)
class Steps:
    """Étapes du cycle de vie à exécuter."""

    create: bool
    upload: bool
    predict: bool
    export: bool
    project_id: str | None


@dataclass(frozen=True)
class ReviewScope:
    """Périmètre de revue d'un jeu d'évaluation (exemple 10)."""

    scope: str
    sample_size: int


def build_parser(
    description: str, *, with_scope: bool = False
) -> argparse.ArgumentParser:
    """Construire le parseur d'arguments commun aux exemples.

    Args:
        description: Description de l'exemple, affichée par `--help`.
        with_scope: True pour ajouter `--scope` et `--sample-size`,
            propres à la revue d'un jeu d'évaluation.

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
    if with_scope:
        parser.add_argument(
            "--scope",
            choices=SCOPE_CHOICES,
            default="rejected",
            help=(
                "Questions à faire relire : les cas rejetés par le juge "
                "(rejected, défaut), toutes les questions (all), ou les "
                "rejets plus un échantillon de cas validés (sample)."
            ),
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=DEFAULT_SAMPLE_SIZE,
            help=(
                "Nombre de cas validés à échantillonner. "
                "Utilisé uniquement avec --scope sample."
            ),
        )
    return parser


def parse_review_scope(parser: argparse.ArgumentParser) -> ReviewScope:
    """Lire le périmètre de revue demandé.

    À appeler sur un parseur construit avec `with_scope=True`.

    Args:
        parser: Parseur construit par `build_parser(with_scope=True)`.

    Returns:
        Le périmètre demandé.

    Raises:
        SystemExit: Si `--sample-size` est négatif.
    """
    args = parser.parse_args()
    if args.sample_size < 0:
        parser.error("--sample-size doit être positif ou nul.")
    return ReviewScope(scope=args.scope, sample_size=args.sample_size)


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
