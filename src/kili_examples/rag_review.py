"""Révision métier d'un jeu d'évaluation RAG (exemple 10).

Le cas d'usage : un LLM-as-judge compare la prédiction d'un RAG à une
réponse validée par les métiers. Son verdict sert à **sélectionner** les
cas à faire relire — mais il n'est jamais montré à l'annotateur, qui
juge à l'aveugle. Le métier répond à deux questions indépendantes :

1. la réponse de référence est-elle correcte ? (elle est présumée bonne,
   mais l'annotation d'origine peut être fautive) ;
2. la nouvelle réponse prédite est-elle correcte ?

Deux champs libres optionnels permettent de corriger la référence et
d'ajouter une formulation valide supplémentaire.

La sortie est une **nouvelle version du dataset** : une banque de
réponses au schéma inchangé, directement consommable par le run de juge
suivant. La traçabilité (ce qui a changé, où le juge s'est trompé) part
dans un rapport séparé pour ne pas polluer les données.

Ce module contient la logique pure de cette boucle — sans appel Kili —
pour qu'elle soit testable et réutilisable hors du script d'exemple.
"""

import json
from pathlib import Path
from typing import Any, Literal

from loguru import logger

# --- Noms des jobs de l'interface d'arbitrage -----------------------------
# Ils sont partagés entre le script d'exemple (qui construit l'ontologie)
# et ce module (qui relit les labels), d'où leur centralisation ici.

REFERENCE_CORRECT_JOB = "REFERENCE_CORRECTE"
PREDICTION_CORRECT_JOB = "PREDICTION_CORRECTE"
REFERENCE_FIX_JOB = "REFERENCE_CORRIGEE"
SECONDARY_ANSWER_JOB = "REPONSE_SECONDAIRE"

# Les deux jugements sont des radios binaires.
YES = "OUI"
NO = "NON"

# Périmètres de revue possibles.
Scope = Literal["rejected", "all", "sample"]

# Verdict du juge marquant un rejet.
REJECTED_VERDICT = "NON_CONFORME"


# --- Lecture des labels exportés ------------------------------------------


def extract_category(
    conversation: dict[str, Any],
    job_name: str,
    *,
    round_index: str = "0",
) -> str | None:
    """Lire la catégorie choisie sur un job de classification.

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
        job_name: Nom du job de classification à lire.
        round_index: Numéro du tour, sous forme de chaîne.

    Returns:
        Le nom de la catégorie choisie, ou `None` si le job n'a pas été
        renseigné.
    """
    first_round = _round_answer(conversation, job_name, round_index)
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


def extract_text(
    conversation: dict[str, Any],
    job_name: str,
    *,
    round_index: str = "0",
) -> str | None:
    """Lire la saisie d'un job de transcription.

    Une saisie vide ou composée uniquement d'espaces est traitée comme
    absente : c'est ce que produit un annotateur qui ouvre le champ sans
    le remplir.

    Args:
        conversation: Une conversation exportée.
        job_name: Nom du job de transcription à lire.
        round_index: Numéro du tour, sous forme de chaîne.

    Returns:
        Le texte saisi, nettoyé de ses espaces de bord, ou `None`.
    """
    first_round = _round_answer(conversation, job_name, round_index)
    text = first_round.get("text")
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    return stripped or None


def _round_answer(
    conversation: dict[str, Any], job_name: str, round_index: str
) -> dict[str, Any]:
    """Isoler la réponse d'un job au niveau `round`, ou un dict vide."""
    label = conversation.get("label") or {}
    round_level = label.get("round") or {}
    job_answer = round_level.get(job_name) or {}
    return job_answer.get(round_index) or {}


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


def is_reviewed(conversation: dict[str, Any]) -> bool:
    """Dire si une conversation porte un arbitrage exploitable.

    Le seul champ qui compte est `PREDICTION_CORRECTE` : il n'est jamais
    pré-rempli, donc sa présence prouve qu'un humain est passé.
    `REFERENCE_CORRECTE`, lui, arrive pré-coché à `OUI` et ne prouve
    rien.

    Args:
        conversation: Une conversation exportée.

    Returns:
        True si le cas a été arbitré.
    """
    return extract_category(conversation, PREDICTION_CORRECT_JOB) is not None


# --- Construction de la nouvelle version du dataset -----------------------


def build_enriched_answer_bank(
    *,
    answer_bank: list[dict[str, Any]],
    conversations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Produire la banque révisée et son rapport de révision.

    Trois choses peuvent arriver à un enregistrement :

    - sa réponse de référence est **remplacée**, si le métier l'a jugée
      fautive et en a saisi une version corrigée ;
    - une **réponse secondaire** lui est ajoutée : soit la réécriture
      saisie par le métier, soit — à défaut — la prédiction elle-même
      lorsqu'elle a été jugée correcte ;
    - rien ne bouge.

    L'opération est **idempotente** : réexporter deux fois n'ajoute pas
    deux fois la même variante, ce qui compte puisque la boucle tourne à
    chaque run. La banque d'entrée n'est pas modifiée sur place.

    Le schéma de sortie est identique au schéma d'entrée
    (`question_id`, `question`, `answer`, `secondary_answers`) : c'est ce
    qui rend le fichier directement consommable par le juge, sans
    adaptation. Toute la traçabilité part dans le rapport.

    Args:
        answer_bank: La banque de réponses actuelle, un enregistrement
            par question.
        conversations: Les conversations exportées de Kili. Les
            questions absentes (hors périmètre de revue) sont reportées
            inchangées.

    Returns:
        Un couple `(banque révisée, rapport de révision)`. Le rapport
        est détaillé dans `build_revision_report`.
    """
    enriched = [
        {
            **item,
            "secondary_answers": list(item.get("secondary_answers") or []),
        }
        for item in answer_bank
    ]
    by_question_id = {item["question_id"]: item for item in enriched}

    corrected_references: list[dict[str, str]] = []
    promoted_predictions: list[str] = []
    manual_rewrites: list[str] = []
    missing_corrections: list[str] = []
    agreement: list[dict[str, Any]] = []

    for conversation in conversations:
        if not is_reviewed(conversation):
            continue

        question_id = _question_id_of(conversation)
        entry = by_question_id.get(question_id) if question_id else None
        if entry is None:
            logger.warning(
                "Conversation sans question correspondante : {}",
                question_id,
            )
            continue

        prediction_ok = (
            extract_category(conversation, PREDICTION_CORRECT_JOB) == YES
        )
        agreement.append(
            {
                "question_id": question_id,
                "judge_verdict": (conversation.get("metadata") or {}).get(
                    "judge_verdict"
                ),
                "prediction_correcte": prediction_ok,
            }
        )

        _apply_reference_fix(
            conversation=conversation,
            entry=entry,
            question_id=question_id,
            corrected_references=corrected_references,
            missing_corrections=missing_corrections,
        )
        _apply_secondary_answer(
            conversation=conversation,
            entry=entry,
            question_id=question_id,
            prediction_ok=prediction_ok,
            promoted_predictions=promoted_predictions,
            manual_rewrites=manual_rewrites,
        )

    report = build_revision_report(
        corrected_references=corrected_references,
        promoted_predictions=promoted_predictions,
        manual_rewrites=manual_rewrites,
        missing_corrections=missing_corrections,
        agreement=agreement,
    )
    return enriched, report


def _apply_reference_fix(
    *,
    conversation: dict[str, Any],
    entry: dict[str, Any],
    question_id: str,
    corrected_references: list[dict[str, str]],
    missing_corrections: list[str],
) -> None:
    """Remplacer la réponse de référence si le métier l'a corrigée.

    Une référence déclarée fautive **sans** texte de remplacement n'est
    pas écrasée : on préfère garder une réponse imparfaite qu'aucune.
    Le cas est signalé dans le rapport, à traiter à la main.
    """
    if extract_category(conversation, REFERENCE_CORRECT_JOB) != NO:
        return

    fixed = extract_text(conversation, REFERENCE_FIX_JOB)
    if fixed is None:
        logger.warning(
            "Référence déclarée fautive sans correction saisie : {}",
            question_id,
        )
        missing_corrections.append(question_id)
        return

    if fixed == entry["answer"]:
        return

    corrected_references.append(
        {
            "question_id": question_id,
            "ancienne_reponse": entry["answer"],
            "nouvelle_reponse": fixed,
        }
    )
    entry["answer"] = fixed
    # La correction peut rendre une variante existante redondante.
    entry["secondary_answers"] = [
        variant for variant in entry["secondary_answers"] if variant != fixed
    ]


def _apply_secondary_answer(
    *,
    conversation: dict[str, Any],
    entry: dict[str, Any],
    question_id: str,
    prediction_ok: bool,
    promoted_predictions: list[str],
    manual_rewrites: list[str],
) -> None:
    """Ajouter une réponse secondaire si l'arbitrage en produit une.

    Deux sources possibles, dans cet ordre de priorité :

    1. la réécriture saisie par le métier — elle prime toujours, y
       compris quand la prédiction a été jugée incorrecte (c'est
       précisément le cas « presque bonne, je l'ai corrigée ») ;
    2. à défaut, la prédiction elle-même, si elle a été jugée correcte.

    Aucune réponse secondaire n'est obligatoire : un cas peut être
    arbitré sans qu'aucune variante n'en sorte.
    """
    rewrite = extract_text(conversation, SECONDARY_ANSWER_JOB)
    if rewrite is not None:
        if _add_variant(entry, rewrite):
            manual_rewrites.append(question_id)
        return

    if not prediction_ok:
        return

    prediction = _prediction_of(conversation)
    if not prediction:
        logger.warning("Aucune prédiction lisible pour {}", question_id)
        return

    if _add_variant(entry, prediction):
        promoted_predictions.append(question_id)


def _add_variant(entry: dict[str, Any], variant: str) -> bool:
    """Ajouter une variante en garantissant l'unicité.

    Returns:
        True si la variante a bien été ajoutée, False si elle était déjà
        connue (doublon ou identique à la réponse principale).
    """
    if not variant or variant == entry["answer"]:
        return False
    if variant in entry["secondary_answers"]:
        return False
    entry["secondary_answers"].append(variant)
    return True


def build_revision_report(
    *,
    corrected_references: list[dict[str, str]],
    promoted_predictions: list[str],
    manual_rewrites: list[str],
    missing_corrections: list[str],
    agreement: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assembler le rapport de révision.

    Le rapport vit à côté du dataset, jamais dedans : il porte tout ce
    qui sert à comprendre le run sans alourdir le fichier que le juge
    doit relire.

    Le croisement juge × métier n'est complet qu'en périmètre `all` ou
    `sample` : en périmètre `rejected`, le juge n'a proposé que des
    rejets, donc ses faux positifs sont hors champ par construction.

    Args:
        corrected_references: Références remplacées, avec ancienne et
            nouvelle valeur.
        promoted_predictions: Questions dont la prédiction a été promue
            telle quelle.
        manual_rewrites: Questions enrichies d'une réécriture manuelle.
        missing_corrections: Références déclarées fautives sans texte de
            remplacement.
        agreement: Un enregistrement par cas arbitré, portant le verdict
            du juge et celui du métier.

    Returns:
        Le rapport, sérialisable en JSON.
    """
    judge_rejected_and_metier_agrees = 0
    judge_rejected_but_metier_accepts = 0
    judge_accepted_and_metier_agrees = 0
    judge_accepted_but_metier_rejects = 0

    for item in agreement:
        rejected = item["judge_verdict"] == REJECTED_VERDICT
        correct = item["prediction_correcte"]
        if rejected and not correct:
            judge_rejected_and_metier_agrees += 1
        elif rejected and correct:
            judge_rejected_but_metier_accepts += 1
        elif not rejected and correct:
            judge_accepted_and_metier_agrees += 1
        else:
            judge_accepted_but_metier_rejects += 1

    reviewed = len(agreement)
    disagreements = (
        judge_rejected_but_metier_accepts + judge_accepted_but_metier_rejects
    )

    return {
        "references_corrigees": corrected_references,
        "predictions_promues": promoted_predictions,
        "reecritures_manuelles": manual_rewrites,
        "references_fautives_sans_correction": missing_corrections,
        "desaccord_juge_metier": {
            "cas_arbitres": reviewed,
            "accords": reviewed - disagreements,
            "desaccords": disagreements,
            # Faux négatif du juge : il a rejeté ce que le métier
            # accepte. C'est le motif d'origine de toute la boucle.
            "faux_negatifs_juge": judge_rejected_but_metier_accepts,
            # Faux positif du juge : il a validé ce que le métier
            # rejette. Invisible en périmètre `rejected`.
            "faux_positifs_juge": judge_accepted_but_metier_rejects,
            "juge_rejette_metier_confirme": judge_rejected_and_metier_agrees,
            "juge_accepte_metier_confirme": judge_accepted_and_metier_agrees,
        },
    }


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
