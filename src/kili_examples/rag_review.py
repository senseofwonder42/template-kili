"""Boucle d'amélioration du LLM-as-judge (exemple 10).

Le cas d'usage : un LLM-as-judge compare la prédiction d'un RAG à une
réponse validée par les métiers. Trop sévère, il rejette des prédictions
en réalité acceptables. Les métiers arbitrent ces rejets dans Kili ; les
prédictions qu'ils valident deviennent des `secondary_answers`, et le
juge reçoit ensuite **toutes** les réponses valides.

Ce module contient la logique pure de cette boucle — sans appel Kili —
pour qu'elle soit testable et réutilisable hors du script d'exemple.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

# Catégorie du job VERDICT_METIER qui déclenche la promotion en
# réponse secondaire.
ACCEPTABLE_CATEGORY = "ACCEPTABLE"
VERDICT_JOB_NAME = "VERDICT_METIER"


def extract_business_verdict(
    conversation: dict[str, Any],
    *,
    job_name: str = VERDICT_JOB_NAME,
) -> str | None:
    """Lire le verdict métier d'une conversation exportée.

    Le format de label LLM_STATIC est indexé par niveau puis, au niveau
    `round`, par numéro de tour (une chaîne). On ne lit que le tour
    `"0"` : dans cet exemple, une conversation ne porte qu'un échange.

    La fonction est volontairement tolérante : une conversation non
    annotée, ou annotée sur un autre job, renvoie `None` plutôt que de
    lever une exception — un export contient normalement un mélange de
    cas traités et non traités.

    Args:
        conversation: Une conversation telle que renvoyée par
            `kili.llm.export(...)`.
        job_name: Nom du job portant le verdict.

    Returns:
        Le nom de la catégorie choisie, ou `None` si le cas n'a pas été
        arbitré.
    """
    label = conversation.get("label") or {}
    round_level = label.get("round") or {}
    job_answer = round_level.get(job_name) or {}

    first_round = job_answer.get("0") or {}
    categories = first_round.get("categories") or []
    if not categories:
        return None

    # Au niveau LLM, `categories` est une liste de chaînes. On accepte
    # aussi la forme `[{"name": ...}]` au cas où l'export la renverrait,
    # pour ne pas casser sur une variation de format.
    first = categories[0]
    if isinstance(first, dict):
        return first.get("name")
    return str(first)


def _question_id_of(conversation: dict[str, Any]) -> str | None:
    """Retrouver la question d'origine d'une conversation exportée."""
    metadata = conversation.get("metadata") or {}
    return metadata.get("question_id") or conversation.get("externalId")


def _prediction_of(conversation: dict[str, Any]) -> str | None:
    """Retrouver le texte de la prédiction dans une conversation.

    On privilégie la métadonnée, écrite à l'import ; à défaut on relit
    le dernier `chatItem` de rôle ASSISTANT.
    """
    metadata = conversation.get("metadata") or {}
    if metadata.get("prediction"):
        return metadata["prediction"]

    assistant_items = [
        item
        for item in conversation.get("chatItems") or []
        if item.get("role") == "ASSISTANT"
    ]
    if not assistant_items:
        return None
    return assistant_items[-1].get("content")


def build_enriched_answer_bank(
    *,
    answer_bank: list[dict[str, Any]],
    conversations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Ajouter à la banque les prédictions validées par le métier.

    Pour chaque conversation arbitrée `ACCEPTABLE`, la prédiction est
    ajoutée aux `secondary_answers` de sa question. L'opération est
    **idempotente** : réexporter deux fois n'ajoute pas deux fois la
    même variante, ce qui compte puisque la boucle tourne à chaque run.

    La banque d'entrée n'est pas modifiée sur place.

    Args:
        answer_bank: La banque de réponses actuelle, un enregistrement
            par question (`question_id`, `question`, `answer`,
            `secondary_answers`).
        conversations: Les conversations exportées de Kili.

    Returns:
        Un couple `(banque enrichie, identifiants des questions
        effectivement enrichies)`.
    """
    enriched = [
        {
            **item,
            "secondary_answers": list(item.get("secondary_answers") or []),
        }
        for item in answer_bank
    ]
    by_question_id = {item["question_id"]: item for item in enriched}

    promoted: list[str] = []
    for conversation in conversations:
        if extract_business_verdict(conversation) != ACCEPTABLE_CATEGORY:
            continue

        question_id = _question_id_of(conversation)
        entry = by_question_id.get(question_id) if question_id else None
        if entry is None:
            logger.warning(
                "Conversation sans question correspondante : {}",
                question_id,
            )
            continue

        prediction = _prediction_of(conversation)
        if not prediction:
            logger.warning("Aucune prédiction lisible pour {}", question_id)
            continue

        # Idempotence : ni doublon d'une variante, ni variante
        # identique à la réponse principale.
        if prediction in entry["secondary_answers"] or prediction == entry.get(
            "answer"
        ):
            continue

        entry["secondary_answers"].append(prediction)
        promoted.append(question_id)

    return enriched, promoted


def write_answer_bank(path: Path, answer_bank: list[dict[str, Any]]) -> None:
    """Écrire la banque de réponses au format JSONL.

    Args:
        path: Fichier de destination. Les dossiers parents sont créés.
        answer_bank: Les enregistrements à écrire.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False) for item in answer_bank]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("{} questions écrites dans {}", len(answer_bank), path)


def build_judge_prompt_context(entry: dict[str, Any]) -> str:
    """Formater les réponses valides d'une question pour le juge.

    C'est le point d'arrivée de la boucle : au run suivant, le juge ne
    reçoit plus une seule réponse de référence mais **toutes** les
    formulations acceptées. Le rendu explicite qu'aucune n'est
    supérieure aux autres.

    Args:
        entry: Un enregistrement de la banque de réponses.

    Returns:
        Le bloc de texte à insérer dans le prompt du juge.
    """
    answers = [entry["answer"], *(entry.get("secondary_answers") or [])]
    if len(answers) == 1:
        return f"Réponse de référence :\n{answers[0]}"

    formatted = "\n".join(
        f"{index}. {answer}" for index, answer in enumerate(answers, start=1)
    )
    return (
        "Réponses de référence acceptables (toutes équivalentes — la "
        "prédiction est conforme si elle correspond à l'une "
        f"d'elles) :\n{formatted}"
    )
