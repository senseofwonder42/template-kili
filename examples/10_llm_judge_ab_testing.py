"""Exemple 10 — Révision métier d'un jeu d'évaluation RAG (assurance auto).

Besoin métier
    On évalue un RAG métier en comparant sa prédiction à une réponse
    validée par les experts. Un LLM-as-judge classe automatiquement
    chaque prédiction en conforme / non conforme, mais il est trop
    sévère : il ignore ce qui, dans la réponse de référence, est
    *essentiel* et ce qui n'est qu'*optionnel*.

    À chaque nouveau benchmark, on fait relire une sélection de cas par
    le métier pour produire **la version suivante du dataset**. Le
    métier répond à deux questions indépendantes :

    1. la réponse de référence est-elle correcte ? Elle est présumée
       bonne — d'où le pré-remplissage à OUI — mais l'annotation
       d'origine est parfois fautive et doit pouvoir être corrigée ;
    2. la nouvelle réponse prédite est-elle correcte ?

    Deux champs libres, tous deux optionnels, complètent le tableau :
    l'un pour réécrire une référence fautive, l'autre pour saisir une
    seconde formulation valide. Ce dernier couvre le cas courant où la
    prédiction est *presque* bonne — il lui manque une information, ou
    elle en ajoute une fausse : plutôt que de la rejeter en bloc, le
    métier en écrit la version correcte, qui rejoint les
    `secondary_answers`.

Un choix de conception : le juge ne s'affiche pas
    Le verdict du juge sert uniquement à **sélectionner** les cas
    (voir `--scope`). Il n'apparaît jamais à l'écran : l'afficher ferait
    perdre du temps aux annotateurs et les ancrerait sur l'avis qu'on
    cherche précisément à auditer. Il reste dans les `metadata`, d'où
    l'export tire les statistiques de désaccord juge / métier.

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
    - un périmètre de revue paramétrable, pour arbitrer entre coût
      d'annotation et complétude de l'audit ;
    - un export qui referme la boucle en écrivant la version suivante
      du dataset, plus un rapport de révision séparé.

Ce que cet exemple remplace
    Le fichier Excel de revue : traçabilité par annotateur, file de
    travail, et surtout une sortie directement réutilisable par le run
    suivant.

Usage
    uv run python examples/10_llm_judge_ab_testing.py
    uv run python examples/10_llm_judge_ab_testing.py --scope sample \\
        --sample-size 3
    uv run python examples/10_llm_judge_ab_testing.py --export \\
        --project-id <id>
"""

import json
import random
from pathlib import Path

from kili.client import Kili
from loguru import logger

from kili_examples.cli import build_parser, parse_review_scope, parse_steps
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
    NO,
    PREDICTION_CORRECT_JOB,
    REFERENCE_CORRECT_JOB,
    REFERENCE_FIX_JOB,
    REJECTED_VERDICT,
    SECONDARY_ANSWER_JOB,
    YES,
    build_enriched_answer_bank,
    write_answer_bank,
)

PROJECT_TITLE = "10 - Revision metier du jeu d'evaluation RAG"
RAG_DIR = DATA_DIR / "samples" / "rag"
ANSWER_BANK_PATH = RAG_DIR / "answer_bank.jsonl"
JUDGE_RUN_PATH = RAG_DIR / "judge_run.jsonl"

EXPORT_DIR = PROCESSED_DIR / "10_llm_judge_ab_testing"
EXPORT_LABELS_PATH = EXPORT_DIR / "labels.json"
EXPORT_BANK_PATH = EXPORT_DIR / "answer_bank_enrichie.jsonl"
EXPORT_REPORT_PATH = EXPORT_DIR / "revision_report.json"

# Les `modelName` des deux ASSISTANT. Ils s'affichent dans l'éditeur :
# autant qu'ils disent explicitement laquelle est la référence.
REFERENCE_MODEL_NAME = "reference-metier"
CANDIDATE_MODEL_NAME = "rag-assurance-auto-v2"

# Graine du tirage `--scope sample`. Fixe, pour que deux exécutions
# soumettent exactement le même échantillon : sans cela, rejouer
# l'exemple changerait le périmètre à chaque fois.
SAMPLE_SEED = 20260802


# --- 1. Interface d'annotation --------------------------------------------


def build_interface() -> dict:
    """Construire le `json_interface` de révision.

    Quatre jobs, tous au niveau `round` (l'échange question + ses deux
    réponses), car c'est bien l'échange que le métier arbitre :

    - `REFERENCE_CORRECTE` et `PREDICTION_CORRECTE` : deux jugements
      **indépendants**. Les séparer est tout l'intérêt du montage — une
      prédiction peut être fautive parce que la référence l'était.
    - `REFERENCE_CORRIGEE` et `REPONSE_SECONDAIRE` : deux champs libres
      optionnels. Séparés eux aussi, pour que l'export sache sans
      ambiguïté où va chaque texte saisi.

    Le `level` est la seule nouveauté par rapport aux interfaces des
    exemples 01 à 09.

    Returns:
        Le `json_interface` complet.
    """
    jobs = {
        REFERENCE_CORRECT_JOB: build_llm_classification_job(
            instruction=(
                "La réponse de référence (à gauche) est-elle correcte ?"
            ),
            categories={
                YES: build_category(
                    "Oui — la référence fait autorité", color="#3CD876"
                ),
                NO: build_category(
                    "Non — la référence est fautive", color="#FFB300"
                ),
            },
            level="round",
            input_type="radio",
        ),
        PREDICTION_CORRECT_JOB: build_llm_classification_job(
            instruction="La nouvelle réponse (à droite) est-elle correcte ?",
            categories={
                YES: build_category("Oui — acceptable", color="#3CD876"),
                NO: build_category("Non — inacceptable", color="#FF6B6B"),
            },
            level="round",
            input_type="radio",
        ),
        REFERENCE_FIX_JOB: build_llm_transcription_job(
            instruction=(
                "Si la référence est fautive : saisir ici sa version "
                "corrigée. Elle remplacera la réponse de référence."
            ),
            level="round",
            required=False,
        ),
        SECONDARY_ANSWER_JOB: build_llm_transcription_job(
            instruction=(
                "Facultatif : une autre formulation valide. Utile si la "
                "nouvelle réponse est presque bonne — corrigez-la ici "
                "plutôt que de la rejeter."
            ),
            level="round",
            required=False,
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


def load_review_cases(
    scope: str = "rejected", sample_size: int = 10
) -> list[dict]:
    """Assembler les cas à faire relire par le métier.

    On joint la banque de réponses et le run du juge sur `question_id`,
    puis on sélectionne selon le périmètre demandé :

    - `rejected` : uniquement les cas rejetés par le juge. Le moins
      coûteux, mais aveugle à ses **faux positifs** — une prédiction
      qu'il a validée à tort ne sera jamais relue.
    - `all` : toutes les questions. Audit complet du juge, coût
      d'annotation proportionnel à la taille du benchmark.
    - `sample` : tous les rejets, plus `sample_size` cas validés tirés
      au hasard. Le compromis : on contrôle les faux positifs sans
      relire l'intégralité du jeu.

    Le tirage de `sample` est déterministe (graine fixe) : deux
    exécutions soumettent le même échantillon.

    Args:
        scope: Périmètre de revue (`rejected`, `all` ou `sample`).
        sample_size: Nombre de cas validés à tirer, en `sample`.

    Returns:
        Les cas à relire, enrichis de la question, de la réponse
        validée, de ses variantes connues et du verdict du juge.
    """
    bank = {
        item["question_id"]: item for item in _load_jsonl(ANSWER_BANK_PATH)
    }
    judge_run = _load_jsonl(JUDGE_RUN_PATH)

    rejected, accepted = [], []
    for run_item in judge_run:
        reference = bank.get(run_item["question_id"])
        if reference is None:
            logger.warning(
                "question_id inconnue dans la banque : {}",
                run_item["question_id"],
            )
            continue
        case = {**reference, **run_item}
        if run_item["judge_verdict"] == REJECTED_VERDICT:
            rejected.append(case)
        else:
            accepted.append(case)

    if scope == "all":
        cases = rejected + accepted
    elif scope == "sample":
        # `sample` ne peut pas tirer plus d'éléments qu'il n'en existe.
        drawn = random.Random(SAMPLE_SEED).sample(
            accepted, min(sample_size, len(accepted))
        )
        cases = rejected + drawn
    else:
        cases = rejected

    logger.info(
        "Périmètre '{}' : {} cas à relire ({} rejetés et {} validés par "
        "le juge, sur {} évalués)",
        scope,
        len(cases),
        len(rejected),
        len(cases) - len(rejected),
        len(judge_run),
    )
    return cases


def build_conversation(case: dict, scope: str = "rejected") -> dict:
    """Construire la conversation Kili d'un cas à relire.

    Structure d'un asset LLM_STATIC — très différente des autres types :
    l'asset **est** une liste de `chatItems`, chacun portant un `role`
    (`SYSTEM`, `USER` ou `ASSISTANT`).

    Le montage retenu ici :

    - `SYSTEM` : la consigne, et le rappel des variantes déjà validées.
      **Pas le verdict du juge** : l'annotateur juge à l'aveugle.
    - `USER` : la question métier.
    - `ASSISTANT` n°1 : la **réponse validée** (la référence).
    - `ASSISTANT` n°2 : la **prédiction** du RAG.

    Kili attend exactement deux ASSISTANT par tour, ce qui correspond
    précisément à notre comparaison référence / prédiction et donne un
    affichage côte à côte dans l'éditeur.

    Args:
        case: Un cas produit par `load_review_cases`.
        scope: Périmètre de revue, tracé dans les métadonnées.

    Returns:
        Le dictionnaire de conversation attendu par
        `kili.llm.import_conversations`.
    """
    question_id = case["question_id"]

    # Les variantes déjà validées lors des runs précédents sont
    # rappelées au relecteur : sans cela il risque de re-saisir une
    # formulation déjà connue.
    known_variants = case.get("secondary_answers") or []
    variants_block = (
        "\n\nFormulations déjà acceptées pour cette question :\n"
        + "\n".join(f"- {variant}" for variant in known_variants)
        if known_variants
        else ""
    )

    system_content = (
        "Révision d'un jeu d'évaluation RAG (assurance auto).\n\n"
        "À gauche, la réponse de référence actuelle ; à droite, la "
        "réponse produite par la nouvelle version du RAG.\n\n"
        "Jugez les deux indépendamment. Si la nouvelle réponse est "
        "presque bonne (une information manque, ou une information "
        "fausse s'est glissée), saisissez sa version corrigée dans le "
        "champ prévu : elle deviendra une réponse acceptable de plus."
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
        # `metadata` est libre et ressort à l'export. Le verdict du juge
        # y est rangé — invisible à l'annotateur, mais nécessaire pour
        # mesurer où le juge s'est trompé.
        "metadata": {
            "question_id": question_id,
            "judge_verdict": case["judge_verdict"],
            "judge_reason": case["judge_reason"],
            "prediction": case["prediction"],
            "scope": scope,
        },
    }


def upload_assets(kili: Kili, project_id: str, scope: str, size: int) -> None:
    """Importer les conversations à relire.

    Note : `kili.llm.import_conversations` remplace ici
    `append_many_to_dataset`, qui ne sait pas construire de `chatItems`.

    Args:
        kili: Client Kili authentifié.
        project_id: Projet cible.
        scope: Périmètre de revue.
        size: Taille de l'échantillon, en périmètre `sample`.
    """
    cases = load_review_cases(scope, size)
    conversations = [build_conversation(case, scope) for case in cases]

    result = kili.llm.import_conversations(
        project_id=project_id,
        conversations=conversations,
    )
    logger.info("Import terminé : {}", result)


# --- 3. Pré-annotations ---------------------------------------------------


def predict(asset: dict) -> dict:
    """Pré-annotation : la référence est présumée correcte.

    Un seul champ est pré-rempli, et c'est délibéré :

    - `REFERENCE_CORRECTE` = OUI, parce que la référence est validée par
      les experts. La contredire doit rester l'exception, pas la
      valeur par défaut à saisir à chaque cas.
    - `PREDICTION_CORRECTE` est **laissé vide**. C'est le jugement que
      l'on cherche à obtenir ; le pré-remplir avec l'avis du juge
      biaiserait l'annotateur vers cet avis, alors que tout l'objet du
      dispositif est de le vérifier.
    - les deux champs libres restent vides, par nature.

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
        asset: Un cas produit par `load_review_cases`. Non utilisé : la
            pré-annotation est la même pour tous les cas. Le paramètre
            est conservé pour rester homogène avec les exemples 01 à 09.

    Returns:
        Un label conforme au format LLM_STATIC.
    """
    return {
        "round": {
            REFERENCE_CORRECT_JOB: {"0": {"categories": [YES]}},
        }
    }


def upload_predictions(
    kili: Kili, project_id: str, scope: str, size: int
) -> None:
    """Importer les pré-annotations.

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
        scope: Périmètre de revue.
        size: Taille de l'échantillon, en périmètre `sample`.
    """
    cases = load_review_cases(scope, size)
    conversations = []
    for case in cases:
        conversation = build_conversation(case, scope)
        # `label` accepte les trois niveaux ; on ne remplit que `round`.
        conversation["label"] = predict(case)
        conversations.append(conversation)

    result = kili.llm.import_conversations(
        project_id=project_id,
        conversations=conversations,
    )
    logger.info("{} pré-annotations importées : {}", len(cases), result)


# --- 4. Export : la version suivante du dataset ---------------------------


def export_review(kili: Kili, project_id: str) -> None:
    """Exporter les arbitrages et en déduire le dataset révisé.

    C'est l'étape qui referme la boucle. Elle produit trois fichiers :

    - `labels.json` : l'export brut, tel que Kili le renvoie ;
    - `answer_bank_enrichie.jsonl` : **le nouveau dataset**, au schéma
      strictement identique à celui d'entrée, donc relisible tel quel
      par le prochain run du juge ;
    - `revision_report.json` : la traçabilité (références corrigées,
      variantes ajoutées, désaccords avec le juge), tenue à l'écart du
      dataset pour ne pas l'alourdir.

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

    enriched, report = build_enriched_answer_bank(
        answer_bank=_load_jsonl(ANSWER_BANK_PATH),
        conversations=conversations or [],
    )
    write_answer_bank(EXPORT_BANK_PATH, enriched)
    EXPORT_REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _log_report(report)
    logger.info(
        "Nouveau dataset écrit dans {} — à réinjecter dans le prochain "
        "run du juge. Rapport détaillé dans {}.",
        EXPORT_BANK_PATH,
        EXPORT_REPORT_PATH,
    )


def _log_report(report: dict) -> None:
    """Résumer le rapport de révision dans les logs."""
    corrected = report["references_corrigees"]
    promoted = report["predictions_promues"]
    rewrites = report["reecritures_manuelles"]
    disagreement = report["desaccord_juge_metier"]

    logger.info("{} référence(s) corrigée(s)", len(corrected))
    for item in corrected:
        logger.info("  → {}", item["question_id"])
    logger.info(
        "{} réponse(s) secondaire(s) ajoutée(s) : {} prédiction(s) "
        "promue(s) telle(s) quelle(s), {} réécriture(s) manuelle(s)",
        len(promoted) + len(rewrites),
        len(promoted),
        len(rewrites),
    )
    logger.info(
        "Désaccord juge / métier : {} sur {} cas arbitrés "
        "({} faux négatif(s) du juge, {} faux positif(s))",
        disagreement["desaccords"],
        disagreement["cas_arbitres"],
        disagreement["faux_negatifs_juge"],
        disagreement["faux_positifs_juge"],
    )

    orphans = report["references_fautives_sans_correction"]
    if orphans:
        logger.warning(
            "{} référence(s) déclarée(s) fautive(s) sans correction "
            "saisie — à traiter à la main : {}",
            len(orphans),
            ", ".join(orphans),
        )


# --- 5. Orchestration -----------------------------------------------------


def main() -> None:
    """Enchaîner les quatre étapes du cycle de vie."""
    setup_logging()
    parser = build_parser(__doc__ or PROJECT_TITLE, with_scope=True)
    steps = parse_steps(parser)
    review = parse_review_scope(parser)
    kili = get_kili()

    project_id = steps.project_id
    if steps.create:
        project = kili.create_project(
            title=f"{PROJECT_TITLE} [{review.scope}]",
            description=(
                "Révision métier du jeu d'évaluation RAG : la référence "
                "et la prédiction sont jugées indépendamment."
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
        upload_assets(kili, project_id, review.scope, review.sample_size)
    if steps.predict:
        upload_predictions(kili, project_id, review.scope, review.sample_size)
    if steps.export:
        export_review(kili, project_id)

    logger.info("Terminé. project_id = {}", project_id)


if __name__ == "__main__":
    main()
