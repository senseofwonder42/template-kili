"""Pilotage d'un projet Kili : file d'annotation et boucle qualité.

Ce module porte la logique **pure** des exemples 11 et 12 — celle qui se
teste hors ligne, sans instance ni clé d'API. Les vrais appels au SDK
(`update_properties_in_assets`, `assign_assets_to_labelers`,
`create_issues`, ...) restent dans les scripts d'exemple, conformément à
la règle du dépôt : on apprend l'API de Kili, pas notre abstraction.

Deux familles de fonctions :

1. **préparer la file** (exemple 11) — dériver des métadonnées et une
   priorité depuis le contenu métier, fusionner des métadonnées,
   répartir les assets entre annotateurs ;
2. **lire la boucle qualité** (exemple 12) — retrouver l'objet visé par
   une issue et résumer l'état des questions et des issues.
"""

from typing import Any

# --- Vocabulaire métier ---------------------------------------------------

# Branche d'assurance déduite du texte de la déclaration. Elle sert à la
# fois de métadonnée filtrable et de clé de routage vers un gestionnaire.
BRANCH_AUTO = "AUTO"
BRANCH_HABITATION = "HABITATION"

# Mots-clés de rattachement, lus dans les déclarations synthétiques
# produites par `scripts/generate_sample_data.py`.
_HABITATION_KEYWORDS = (
    "infiltration",
    "dégât des eaux",
    "appartement",
    "plafond",
    "salle de bain",
    "salon",
)

# Priorités de file. Kili attend un entier, **plus grand = servi en
# premier**, les ex aequo étant départagés par date de création (FIFO).
# La règle retenue ici est métier, pas technique :
#
# - un dégât des eaux s'aggrave tant qu'il n'est pas traité ;
# - un vol ouvre un délai légal (dépôt de plainte, déclaration sous
#   deux jours ouvrés) ;
# - le reste suit l'ordre d'arrivée.
PRIORITY_URGENT = 2
PRIORITY_DELAI_LEGAL = 1
PRIORITY_NORMAL = 0

# Longueur de l'extrait placé dans la clé réservée `text`.
METADATA_EXCERPT_LENGTH = 120


# --- 1. Préparer la file (exemple 11) -------------------------------------


def claim_branch(text: str) -> str:
    """Déduire la branche d'assurance d'une déclaration.

    Règle volontairement naïve — un modèle de classification ferait
    mieux. L'intérêt ici est d'obtenir une métadonnée **filtrable** dès
    l'import, avant toute annotation.

    Args:
        text: Texte libre de la déclaration de sinistre.

    Returns:
        `BRANCH_HABITATION` si le texte évoque un sinistre du logement,
        `BRANCH_AUTO` sinon.
    """
    lowered = text.lower()
    if any(keyword in lowered for keyword in _HABITATION_KEYWORDS):
        return BRANCH_HABITATION
    return BRANCH_AUTO


def claim_priority(text: str) -> int:
    """Calculer la priorité de file d'une déclaration.

    Args:
        text: Texte libre de la déclaration de sinistre.

    Returns:
        `PRIORITY_URGENT` pour un dégât des eaux, `PRIORITY_DELAI_LEGAL`
        pour un vol, `PRIORITY_NORMAL` sinon.
    """
    lowered = text.lower()
    if "dégât des eaux" in lowered or "infiltration" in lowered:
        return PRIORITY_URGENT
    if "vol" in lowered:
        return PRIORITY_DELAI_LEGAL
    return PRIORITY_NORMAL


def build_claim_metadata(declaration: dict[str, Any]) -> dict[str, Any]:
    """Construire la métadonnée d'import d'une déclaration.

    Trois clés sont **réservées** par Kili : `imageUrl`, `text` et `url`.
    Elles s'affichent en tête du panneau de métadonnées de l'interface
    d'annotation, là où les autres clés tombent dans un tableau. On se
    sert donc de `text` pour l'information que l'annotateur doit voir en
    premier, ici un extrait de la déclaration.

    Args:
        declaration: Enregistrement `{"external_id": ..., "text": ...}`
            lu depuis `declarations.jsonl`.

    Returns:
        La métadonnée à passer dans `json_metadata_array`.
    """
    text = declaration["text"]
    excerpt = text[:METADATA_EXCERPT_LENGTH]
    if len(text) > METADATA_EXCERPT_LENGTH:
        excerpt = f"{excerpt}…"
    return {
        # Clé réservée : mise en avant dans l'interface.
        "text": excerpt,
        # Clés libres : filtrables via `kili.assets(metadata_where=...)`.
        "branche": claim_branch(text),
        "priorite_calculee": claim_priority(text),
    }


def merge_metadata(
    existing: dict[str, Any] | None, new: dict[str, Any]
) -> dict[str, Any]:
    """Fusionner une métadonnée existante avec de nouvelles clés.

    `update_properties_in_assets(json_metadatas=...)` reçoit la
    métadonnée **entière** de l'asset : envoyer seulement les nouvelles
    clés écraserait les anciennes. Le motif sûr est donc systématiquement
    lecture, fusion, écriture — c'est ce que cette fonction encapsule.

    Args:
        existing: Métadonnée actuelle de l'asset, telle que renvoyée par
            `kili.assets(fields=["jsonMetadata"])`. `None` est accepté :
            un asset importé sans métadonnée n'a rien à conserver.
        new: Clés à ajouter ou à mettre à jour. Elles gagnent en cas de
            conflit.

    Returns:
        Un nouveau dictionnaire ; les entrées ne sont pas modifiées.
    """
    return {**(existing or {}), **new}


def round_robin_assignment(
    external_ids: list[str], labeler_ids: list[str]
) -> list[list[str]]:
    """Répartir des assets entre annotateurs, à tour de rôle.

    Produit le `to_be_labeled_by_array` attendu par Kili : une **liste
    par asset**, contenant les annotateurs autorisés à le traiter. Ici
    un seul annotateur par asset, ce qui est le cas courant ; une liste à
    plusieurs éléments ouvre l'asset à plusieurs personnes, une liste
    vide remet l'asset à disposition de toute l'équipe.

    Args:
        external_ids: Assets à répartir, dans l'ordre.
        labeler_ids: Annotateurs destinataires (identifiants ou emails,
            selon la méthode du SDK appelée ensuite).

    Returns:
        Une liste de listes, alignée sur `external_ids`. Si
        `labeler_ids` est vide, renvoie une liste vide par asset, ce qui
        correspond à « aucun assigné ».
    """
    if not labeler_ids:
        return [[] for _ in external_ids]
    return [
        [labeler_ids[index % len(labeler_ids)]]
        for index in range(len(external_ids))
    ]


# --- 2. Lire la boucle qualité (exemple 12) -------------------------------


def first_object_mid(json_response: dict[str, Any]) -> str | None:
    """Retrouver le `mid` du premier objet annoté d'un label.

    Une issue peut viser un **objet précis** d'un label (une boîte, un
    polygone, une entité) plutôt que le label entier. On l'y rattache par
    son `mid`, l'identifiant que porte chaque annotation dans le
    `jsonResponse`.

    Args:
        json_response: Le `jsonResponse` d'un label, tel que renvoyé par
            `kili.labels(fields=["jsonResponse"])`.

    Returns:
        Le premier `mid` rencontré, ou `None` si le label ne contient
        aucun objet (cas d'un label purement de classification).
    """
    for job_response in json_response.values():
        if not isinstance(job_response, dict):
            continue
        for annotation in job_response.get("annotations", []):
            mid = annotation.get("mid")
            if mid:
                return mid
    return None


def summarize_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Résumer l'état des questions et des issues d'un projet.

    `kili.issues(...)` renvoie **les deux à la fois** : un objet `Issue`
    représente aussi bien une issue qu'une question, le champ `type` les
    distingue (`"ISSUE"` / `"QUESTION"`). Ce résumé les sépare et compte
    par statut (`OPEN`, `SOLVED`, `CANCELLED`).

    Args:
        issues: Les objets renvoyés par `kili.issues(...)`, demandés avec
            au moins les champs `type`, `status` et `assetId`.

    Returns:
        Un rapport `{"total", "issues", "questions",
        "assets_a_traiter"}`, où les deux sous-dictionnaires comptent par
        statut et `assets_a_traiter` liste les assets portant au moins un
        élément ouvert.
    """
    report: dict[str, Any] = {
        "total": len(issues),
        "issues": {},
        "questions": {},
        "assets_a_traiter": [],
    }
    for issue in issues:
        bucket = "questions" if issue.get("type") == "QUESTION" else "issues"
        status = issue.get("status", "INCONNU")
        report[bucket][status] = report[bucket].get(status, 0) + 1

        asset_id = issue.get("assetId")
        if (
            status == "OPEN"
            and asset_id
            and asset_id not in report["assets_a_traiter"]
        ):
            report["assets_a_traiter"].append(asset_id)
    return report
