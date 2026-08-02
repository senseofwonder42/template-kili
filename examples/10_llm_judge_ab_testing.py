"""Exemple 10 — Arbitrage métier d'un LLM-as-judge (RAG assurance auto).

Besoin métier
    On évalue un RAG métier en comparant sa prédiction à une réponse
    validée par les experts. Un LLM-as-judge classe automatiquement
    chaque prédiction en conforme / non conforme, mais il est trop
    sévère : il ignore ce qui, dans la réponse de référence, est
    *essentiel* et ce qui n'est qu'*optionnel*. Les cas qu'il rejette
    doivent donc repasser devant les métiers.

    Quand le métier estime finalement une prédiction acceptable, on
    l'ajoute comme `secondary_answer` : une seconde formulation valide.
    Aux runs suivants, le juge reçoit **toutes** les réponses valides,
    ce qui réduit mécaniquement ses faux négatifs.

Ce que cet exemple montre
    - un projet `input_type="LLM_STATIC"`, conçu pour comparer des
      sorties de modèles — et non les cinq types vus jusqu'ici ;
    - l'import par `kili.llm.import_conversations(...)`, qui remplace
      `append_many_to_dataset` : un asset est une **conversation**
      (`chatItems`), pas un fichier ;
    - la réponse validée et la prédiction présentées comme les **deux
      ASSISTANT** d'un même tour, donc côte à côte dans l'éditeur ;
    - des jobs portant un `level` (`round`, `completion`) : une clé
      propre aux projets LLM ;
    - le pré-remplissage du verdict du juge, pour que le métier
      *arbitre* au lieu de repartir de zéro ;
    - un export qui referme la boucle en écrivant la banque de réponses
      enrichie.

Ce que cet exemple remplace
    Le fichier Excel de revue : traçabilité par annotateur, file de
    travail, et surtout une sortie directement réutilisable par le run
    suivant.

Usage
    uv run python examples/10_llm_judge_ab_testing.py
    uv run python examples/10_llm_judge_ab_testing.py --export \\
        --project-id <id>
"""

import json
from pathlib import Path

from kili.client import Kili
from loguru import logger

from kili_examples.cli import build_parser, parse_steps
from kili_examples.client import get_kili
from kili_examples.interfaces import (
    build_category,
    build_json_interface,
    build_llm_classification_job,
    build_llm_transcription_job,
)
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR, PROCESSED_DIR
from kili_examples.rag_review import (
    build_enriched_answer_bank,
    write_answer_bank,
)

PROJECT_TITLE = "10 - Arbitrage metier du LLM-as-judge (RAG auto)"
RAG_DIR = DATA_DIR / "samples" / "rag"
ANSWER_BANK_PATH = RAG_DIR / "answer_bank.jsonl"
JUDGE_RUN_PATH = RAG_DIR / "judge_run.jsonl"

EXPORT_DIR = PROCESSED_DIR / "10_llm_judge_ab_testing"
EXPORT_LABELS_PATH = EXPORT_DIR / "labels.json"
EXPORT_BANK_PATH = EXPORT_DIR / "answer_bank_enrichie.jsonl"

# Les `modelName` des deux ASSISTANT. Ils s'affichent dans l'éditeur :
# autant qu'ils disent explicitement laquelle est la référence.
REFERENCE_MODEL_NAME = "reference-metier"
CANDIDATE_MODEL_NAME = "rag-assurance-auto-v2"


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` d'arbitrage.

    Trois jobs, tous au niveau `round` (l'échange question + ses deux
    réponses), car c'est bien l'échange que le métier arbitre :

    - `VERDICT_METIER` : la décision qui fait autorité. C'est elle qui
      pilote la boucle.
    - `MOTIF_ECART` : pourquoi le juge s'est trompé (ou non). Ces motifs
      sont la matière première pour corriger le prompt du juge.
    - `COMMENTAIRE_METIER` : texte libre, pour les cas limites.

    Le `level` est la seule nouveauté par rapport aux interfaces des
    exemples 01 à 09.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        "VERDICT_METIER": build_llm_classification_job(
            instruction=(
                "La prédiction est-elle acceptable d'un point de vue métier ?"
            ),
            categories={
                "ACCEPTABLE": build_category(
                    "Acceptable — à promouvoir en réponse secondaire",
                    color="#3CD876",
                ),
                "NON_ACCEPTABLE": build_category(
                    "Non acceptable — le juge avait raison",
                    color="#FF6B6B",
                ),
                "REPONSE_REFERENCE_A_CORRIGER": build_category(
                    "C'est la réponse de référence qui est fautive",
                    color="#FFB300",
                ),
            },
            level="round",
            input_type="radio",
        ),
        "MOTIF_ECART": build_llm_classification_job(
            instruction=(
                "Pourquoi le juge et le métier divergent-ils ? "
                "(plusieurs choix possibles)"
            ),
            categories={
                "INFO_OPTIONNELLE_MANQUANTE": build_category(
                    "Le juge exige une information optionnelle"
                ),
                "REFORMULATION": build_category(
                    "Simple reformulation, sens identique"
                ),
                "INFO_ESSENTIELLE_MANQUANTE": build_category(
                    "Une information essentielle manque vraiment"
                ),
                "CONTRESENS": build_category(
                    "La prédiction contredit la référence"
                ),
                "HORS_SUJET": build_category("La prédiction est hors sujet"),
            },
            level="round",
            # `checkbox` : plusieurs motifs peuvent se cumuler.
            input_type="checkbox",
            required=False,
        ),
        "COMMENTAIRE_METIER": build_llm_transcription_job(
            instruction=(
                "Commentaire libre (cas limite, précision à apporter au "
                "prompt du juge…)"
            ),
            level="round",
        ),
    }
    return build_json_interface(jobs)


# --- 2. Assets (conversations) --------------------------------------------


def _load_jsonl(path: Path) -> list[dict]:
    """Charger un fichier JSONL.

    Args:
        path: Chemin du fichier.

    Returns:
        La liste des enregistrements.

    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{path} est introuvable. Lancez d'abord : "
            "uv run python scripts/generate_sample_data.py"
        )
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_review_cases() -> list[dict]:
    """Assembler les cas à faire arbitrer par le métier.

    On joint la banque de réponses et le run du juge sur `question_id`,
    puis on **ne garde que les cas rejetés par le juge** : les cas qu'il
    accepte n'ont pas besoin d'un arbitrage humain. C'est ce filtre qui
    fait tout l'intérêt de la boucle — le métier ne relit que les
    désaccords potentiels, pas l'intégralité du jeu d'évaluation.

    Returns:
        Les cas à arbitrer, enrichis de la question, de la réponse
        validée, de ses variantes connues et du verdict du juge.
    """
    bank = {
        item["question_id"]: item for item in _load_jsonl(ANSWER_BANK_PATH)
    }
    judge_run = _load_jsonl(JUDGE_RUN_PATH)

    cases = []
    for run_item in judge_run:
        if run_item["judge_verdict"] != "NON_CONFORME":
            continue
        reference = bank.get(run_item["question_id"])
        if reference is None:
            logger.warning(
                "question_id inconnue dans la banque : {}",
                run_item["question_id"],
            )
            continue
        cases.append({**reference, **run_item})

    logger.info(
        "{} cas rejetés par le juge sur {} évalués",
        len(cases),
        len(judge_run),
    )
    return cases


def build_conversation(case: dict) -> dict:
    """Construire la conversation Kili d'un cas à arbitrer.

    Structure d'un asset LLM_STATIC — très différente des autres types :
    l'asset **est** une liste de `chatItems`, chacun portant un `role`
    (`SYSTEM`, `USER` ou `ASSISTANT`).

    Le montage retenu ici :

    - `SYSTEM` : le contexte, dont le verdict du juge et sa
      justification. L'annotateur voit donc *pourquoi* le cas lui est
      soumis.
    - `USER` : la question métier.
    - `ASSISTANT` n°1 : la **réponse validée** (la référence).
    - `ASSISTANT` n°2 : la **prédiction** du RAG.

    Kili attend exactement deux ASSISTANT par tour, ce qui correspond
    précisément à notre comparaison référence / prédiction et donne un
    affichage côte à côte dans l'éditeur.

    Args:
        case: Un cas produit par `load_review_cases`.

    Returns:
        Le dictionnaire de conversation attendu par
        `kili.llm.import_conversations`.
    """
    question_id = case["question_id"]

    # Les variantes déjà validées lors des runs précédents sont
    # rappelées au relecteur : sans cela il risque de re-valider une
    # formulation déjà connue.
    known_variants = case.get("secondary_answers") or []
    variants_block = (
        "\n\nVariantes déjà acceptées :\n"
        + "\n".join(f"- {variant}" for variant in known_variants)
        if known_variants
        else ""
    )

    system_content = (
        "Arbitrage métier d'une évaluation RAG (assurance auto).\n\n"
        f"Verdict du LLM-as-judge : {case['judge_verdict']}\n"
        f"Justification du juge : {case['judge_reason']}\n\n"
        "Votre rôle : confirmer ou infirmer ce verdict. Si la "
        "prédiction est acceptable, elle sera ajoutée comme réponse "
        "secondaire et le juge en tiendra compte aux prochains runs."
        f"{variants_block}"
    )

    return {
        "externalId": question_id,
        "chatItems": [
            {
                "externalId": f"{question_id}-system",
                "role": "SYSTEM",
                "content": system_content,
            },
            {
                "externalId": f"{question_id}-user",
                "role": "USER",
                "content": case["question"],
            },
            {
                "externalId": f"{question_id}-reference",
                "role": "ASSISTANT",
                "content": case["answer"],
                "modelName": REFERENCE_MODEL_NAME,
            },
            {
                "externalId": f"{question_id}-prediction",
                "role": "ASSISTANT",
                "content": case["prediction"],
                "modelName": case.get("model_name", CANDIDATE_MODEL_NAME),
            },
        ],
        # `metadata` est libre et ressort à l'export : on y range ce
        # qu'il faudra pour reconstituer la banque sans relire les
        # fichiers d'entrée.
        "metadata": {
            "question_id": question_id,
            "judge_verdict": case["judge_verdict"],
            "judge_reason": case["judge_reason"],
            "prediction": case["prediction"],
        },
    }


def upload_assets(kili: Kili, project_id: str) -> list[str]:
    """Importer les conversations à arbitrer.

    Note : `kili.llm.import_conversations` remplace ici
    `append_many_to_dataset`, qui ne sait pas construire de `chatItems`.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.

    Returns:
        Les `externalId` des conversations importées.
    """
    cases = load_review_cases()
    conversations = [build_conversation(case) for case in cases]

    result = kili.llm.import_conversations(
        project_id=project_id,
        conversations=conversations,
    )
    logger.info("Import terminé : {}", result)
    return [case["question_id"] for case in cases]


# --- 3. Pré-annotations ---------------------------------------------------


def predict(asset: dict) -> dict:
    """Pré-annotation factice — TODO: brancher votre juge ici.

    Ici la « prédiction » n'est pas une sortie de modèle à corriger mais
    le **verdict du LLM-as-judge**, pré-positionné pour que le métier
    arbitre au lieu de partir d'un écran vide.

    Le format de label d'un projet LLM_STATIC diffère de celui des
    exemples 01 à 09 :

        {
          "round": {
            "NOM_DU_JOB": {
              "0": {"categories": ["NOM_DE_CATEGORIE"]}
            }
          }
        }

    Trois différences à retenir :

    1. le label est indexé par **niveau** (`conversation`, `round`,
       `completion`) et non directement par nom de job ;
    2. au niveau `round`, chaque job est indexé par le **numéro du
       tour**, sous forme de chaîne (`"0"` pour le premier) ;
    3. `categories` est une **liste de chaînes** — et non une liste de
       dictionnaires `{"name": ..., "confidence": ...}` comme ailleurs.

    Args:
        asset: Un cas produit par `load_review_cases`.

    Returns:
        Un label conforme au format LLM_STATIC.
    """
    # Le juge a rejeté le cas : on pré-positionne le verdict
    # correspondant, que le métier n'aura qu'à corriger s'il n'est pas
    # d'accord. C'est précisément ce qui fait gagner du temps par
    # rapport à l'Excel.
    verdict = (
        "NON_ACCEPTABLE"
        if asset.get("judge_verdict") == "NON_CONFORME"
        else "ACCEPTABLE"
    )

    return {
        "round": {
            "VERDICT_METIER": {"0": {"categories": [verdict]}},
        }
    }


def upload_predictions(kili: Kili, project_id: str) -> None:
    """Importer les verdicts du juge comme pré-annotations.

    Deux façons de procéder :

    1. passer `label` directement dans chaque conversation lors de
       `import_conversations` (le plus simple si l'on importe et
       pré-annote en une seule fois) ;
    2. réimporter les conversations avec leur `label`, comme ici, pour
       garder les quatre étapes du dépôt séparées et pouvoir rejouer la
       pré-annotation seule.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
    """
    cases = load_review_cases()
    conversations = []
    for case in cases:
        conversation = build_conversation(case)
        # `label` accepte les trois niveaux ; on ne remplit que `round`.
        conversation["label"] = predict(case)
        conversations.append(conversation)

    result = kili.llm.import_conversations(
        project_id=project_id,
        conversations=conversations,
    )
    logger.info("{} pré-annotations importées : {}", len(cases), result)


# --- 4. Export : refermer la boucle ---------------------------------------


def export_review(kili: Kili, project_id: str) -> None:
    """Exporter les arbitrages et en déduire la banque enrichie.

    C'est l'étape qui referme la boucle : les cas que le métier a jugés
    `ACCEPTABLE` deviennent des `secondary_answers` de leur question.
    Le fichier produit est celui que le prochain run du juge doit
    relire.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet à exporter.
    """
    # `kili.llm.export` renvoie les conversations avec leurs labels,
    # dans le format LLM (et non le `jsonResponse` des autres exemples).
    conversations = kili.llm.export(project_id=project_id)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_LABELS_PATH.write_text(
        json.dumps(conversations, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Export brut écrit dans {}", EXPORT_LABELS_PATH)

    enriched, promoted = build_enriched_answer_bank(
        answer_bank=_load_jsonl(ANSWER_BANK_PATH),
        conversations=conversations or [],
    )
    write_answer_bank(EXPORT_BANK_PATH, enriched)

    logger.info(
        "{} prédiction(s) promue(s) en secondary_answer", len(promoted)
    )
    for question_id in promoted:
        logger.info("  → {}", question_id)
    logger.info(
        "Banque enrichie écrite dans {} — à réinjecter dans le prochain "
        "run du juge.",
        EXPORT_BANK_PATH,
    )


# --- 5. Orchestration -----------------------------------------------------


def main() -> None:
    """Enchaîner les quatre étapes du cycle de vie."""
    setup_logging()
    steps = parse_steps(build_parser(__doc__ or PROJECT_TITLE))
    kili = get_kili()

    project_id = steps.project_id
    if steps.create:
        project = kili.create_project(
            title=PROJECT_TITLE,
            description=(
                "Arbitrage métier des cas rejetés par le LLM-as-judge."
            ),
            # Type dédié à la comparaison de sorties de modèles.
            input_type="LLM_STATIC",
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
        export_review(kili, project_id)

    logger.info("Terminé. project_id = {}", project_id)


if __name__ == "__main__":
    main()
