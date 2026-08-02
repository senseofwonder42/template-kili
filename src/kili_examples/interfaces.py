"""Construction des `json_interface` Kili (ontologies).

C'est le coeur pédagogique du dépôt. Un `json_interface` est un simple
dictionnaire JSON décrivant l'arbre des « jobs » d'annotation :

    {"jobs": {"NOM_DU_JOB": {...}, "AUTRE_JOB": {...}}}

Chaque job porte au minimum :

- `mlTask`   : le type d'annotation (CLASSIFICATION, OBJECT_DETECTION,
               NAMED_ENTITIES_RECOGNITION, TRANSCRIPTION, ...)
- `content`  : les catégories proposées et le widget de saisie (`input`)
- `instruction` : la consigne affichée à l'annotateur
- `required` : 1 si l'annotateur doit remplir ce job, 0 sinon
- `isChild`  : True si le job n'apparaît que sous une catégorie parente

Les fonctions ci-dessous restent volontairement explicites et sans magie :
le lecteur doit pouvoir comparer le dictionnaire produit avec la
documentation Kili « Customizing the interface through JSON settings ».

Conventions de nommage retenues dans ce dépôt :

- les *clés* de jobs et de catégories sont en MAJUSCULES_SNAKE_CASE et en
  vocabulaire métier français (SINISTRE_AUTO, MONTANT_FRANCHISE, ...) car
  elles se retrouvent telles quelles dans les exports ;
- le champ `name` porte le libellé lisible affiché aux annotateurs.
"""

from typing import Any, Literal

# Widgets de saisie acceptés par un job de classification.
# - radio    : une seule catégorie possible (mono-classe)
# - checkbox : plusieurs catégories possibles (multi-label)
# - dropdown : une seule catégorie, présentée en liste déroulante
#              (préférable au-delà d'une dizaine de catégories)
ClassificationInput = Literal["radio", "checkbox", "dropdown"]

# Outils de dessin d'un job OBJECT_DETECTION.
# Vérifiés dans le SDK 2.176.1
# (kili/services/label_data_parsing/annotation.py).
DetectionTool = Literal[
    "rectangle", "polygon", "semantic", "marker", "polyline", "vector", "pose"
]

# Type d'une catégorie telle qu'attendue dans `content.categories`.
Category = dict[str, Any]
Job = dict[str, Any]


def build_category(
    name: str,
    *,
    children: list[str] | None = None,
    color: str | None = None,
) -> Category:
    """Construire une catégorie d'un job Kili.

    Args:
        name: Libellé lisible affiché à l'annotateur (ex. "Sinistre auto").
        children: Noms des jobs enfants déclenchés quand cette catégorie
            est sélectionnée. C'est *ce* champ qui rend un job conditionnel :
            le job enfant n'apparaît dans l'interface que si l'annotateur
            coche cette catégorie.
        color: Couleur hexadécimale de la catégorie (utile pour les jobs
            de détection, où elle colore les boîtes).

    Returns:
        Le dictionnaire de la catégorie.
    """
    category: Category = {"children": children or [], "name": name}
    if color is not None:
        category["color"] = color
    return category


def build_classification_job(
    *,
    instruction: str,
    categories: dict[str, Category],
    input_type: ClassificationInput = "radio",
    required: bool = True,
    is_child: bool = False,
) -> Job:
    """Construire un job de classification.

    Args:
        instruction: Consigne affichée à l'annotateur.
        categories: Catégories proposées, indexées par leur clé métier.
        input_type: Widget de saisie. `radio` pour du mono-classe,
            `checkbox` pour du multi-label, `dropdown` pour une liste longue.
        required: True si l'annotateur doit obligatoirement répondre.
        is_child: True si ce job est un sous-job déclenché par une
            catégorie parente (voir `build_category(children=...)`).

    Returns:
        Le dictionnaire du job, à placer sous la clé `jobs`.
    """
    return {
        "mlTask": "CLASSIFICATION",
        "content": {"categories": categories, "input": input_type},
        "instruction": instruction,
        "required": 1 if required else 0,
        "isChild": is_child,
    }


def build_transcription_job(
    *,
    instruction: str,
    required: bool = True,
    is_child: bool = False,
) -> Job:
    """Construire un job de transcription (saisie de texte libre).

    Un job TRANSCRIPTION n'a pas de catégories : l'annotateur saisit du
    texte. C'est le job utilisé pour l'OCR (relever la valeur d'un champ)
    et, en tant que sous-job, pour qualifier une entité ou une boîte.

    Args:
        instruction: Consigne affichée à l'annotateur.
        required: True si la saisie est obligatoire.
        is_child: True si ce job est déclenché par une catégorie parente.

    Returns:
        Le dictionnaire du job.
    """
    return {
        "mlTask": "TRANSCRIPTION",
        # `categories` reste vide : c'est `input: "textarea"` qui définit
        # le widget de saisie libre.
        "content": {"categories": {}, "input": "textarea"},
        "instruction": instruction,
        "required": 1 if required else 0,
        "isChild": is_child,
    }


def build_object_detection_job(
    *,
    instruction: str,
    categories: dict[str, Category],
    tools: list[DetectionTool],
    required: bool = True,
) -> Job:
    """Construire un job de détection d'objets.

    Le `mlTask` vaut OBJECT_DETECTION quel que soit l'outil : ce sont les
    `tools` qui distinguent une boîte englobante (`rectangle`) d'un
    polygone (`polygon`) ou d'un masque de segmentation (`semantic`).

    Args:
        instruction: Consigne affichée à l'annotateur.
        categories: Catégories d'objets à détecter.
        tools: Outils de dessin autorisés, dans l'ordre d'affichage.
        required: True si au moins une annotation est obligatoire.

    Returns:
        Le dictionnaire du job.
    """
    return {
        "mlTask": "OBJECT_DETECTION",
        "content": {"categories": categories, "input": "radio"},
        "instruction": instruction,
        "tools": tools,
        "required": 1 if required else 0,
        "isChild": False,
    }


def build_ner_job(
    *,
    instruction: str,
    categories: dict[str, Category],
    required: bool = True,
) -> Job:
    """Construire un job de reconnaissance d'entités nommées.

    Sur un asset TEXT, l'annotateur surligne des portions de texte ; la
    réponse est repérée par des offsets de caractères (`beginOffset`).
    Sur un asset PDF, le même `mlTask` produit en plus des coordonnées
    (`polys`, `pageNumberArray`) car le texte est positionné dans la page.

    Args:
        instruction: Consigne affichée à l'annotateur.
        categories: Types d'entités à repérer (ex. MONTANT_FRANCHISE).
        required: True si au moins une entité est obligatoire.

    Returns:
        Le dictionnaire du job.
    """
    return {
        "mlTask": "NAMED_ENTITIES_RECOGNITION",
        "content": {"categories": categories, "input": "radio"},
        "instruction": instruction,
        "required": 1 if required else 0,
        "isChild": False,
    }


# Niveaux d'annotation propres aux projets LLM_STATIC.
# Vérifiés dans `kili_formats.types.JobLevel` (SDK 2.176.1).
# - "completion"   : on annote chaque réponse d'assistant séparément
# - "round"        : on annote l'échange (question + ses réponses)
# - "conversation" : on annote la conversation entière
LlmJobLevel = Literal["completion", "round", "conversation"]


def build_llm_classification_job(
    *,
    instruction: str,
    categories: dict[str, Category],
    level: LlmJobLevel,
    input_type: ClassificationInput = "radio",
    required: bool = True,
) -> Job:
    """Construire un job de classification pour un projet LLM_STATIC.

    Identique à `build_classification_job`, à une clé près : `level`,
    qui indique à quel niveau de la conversation le job s'applique.
    Cette clé n'existe que dans les projets LLM.

    Args:
        instruction: Consigne affichée à l'annotateur.
        categories: Catégories proposées, indexées par leur clé métier.
        level: Niveau d'annotation (`completion`, `round` ou
            `conversation`).
        input_type: Widget de saisie.
        required: True si l'annotateur doit obligatoirement répondre.

    Returns:
        Le dictionnaire du job.
    """
    job = build_classification_job(
        instruction=instruction,
        categories=categories,
        input_type=input_type,
        required=required,
    )
    job["level"] = level
    return job


def build_llm_transcription_job(
    *,
    instruction: str,
    level: LlmJobLevel,
    required: bool = False,
) -> Job:
    """Construire un job de transcription pour un projet LLM_STATIC.

    Args:
        instruction: Consigne affichée à l'annotateur.
        level: Niveau d'annotation.
        required: True si la saisie est obligatoire.

    Returns:
        Le dictionnaire du job.
    """
    job = build_transcription_job(instruction=instruction, required=required)
    job["level"] = level
    return job


def build_json_interface(jobs: dict[str, Job]) -> dict[str, Any]:
    """Assembler les jobs en un `json_interface` complet.

    Args:
        jobs: Jobs indexés par leur nom (la clé sert d'identifiant dans
            les réponses d'annotation, d'où l'importance de la nommer
            explicitement).

    Returns:
        Le dictionnaire passé à `kili.create_project(json_interface=...)`.
    """
    return {"jobs": jobs}
