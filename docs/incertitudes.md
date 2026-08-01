# Incertitudes et points à vérifier

!!! danger "Aucun code de ce dépôt n'a été exécuté contre une instance Kili"
    Il n'y avait ni instance, ni clé d'API, ni accès réseau à la
    plateforme au moment de l'écriture. Cette page recense ce qui reste
    à confirmer lors du premier run sur le serveur de l'entreprise.

## Ce qui a réellement été vérifié

| Vérification | Moyen |
| --- | --- |
| Signatures des méthodes SDK | lues dans le code source de `kili` **2.176.1**, la version épinglée dans `uv.lock` |
| Formes des `json_response` | validées par `ParsedJobs`, le parseur du SDK, qui applique les mêmes règles que la plateforme (voir `tests/test_predictions.py`) |
| Cohérence interface / prédiction | chaque `predict()` est confronté au `build_interface()` du même exemple |
| Invariant des offsets NER | testé sur les données d'exemple |
| Génération des données | exécutée, déterministe |
| Lint, format, tests | `ruff check`, `ruff format --check`, `pytest` — tous verts |

## Ce qui n'a pas pu être vérifié

### 1. Tout appel réseau

Aucune des méthodes suivantes n'a été exécutée :

- `kili.create_project(...)`
- `kili.append_many_to_dataset(...)`
- `kili.create_predictions(...)`
- `kili.labels(...)`
- `kili.export_labels(...)`

Leurs **signatures** sont confirmées (lues dans le source 2.176.1), mais
pas leur comportement réel, ni les erreurs qu'elles peuvent renvoyer.

### 2. Le rendu des interfaces dans l'UI

Les `json_interface` produits sont structurellement conformes à la
documentation, mais personne n'a vu comment ils s'affichent. À vérifier
en priorité :

- l'apparition effective des **sous-jobs conditionnels** (exemples 01,
  06 et 09) — c'est la construction la plus susceptible de mal se
  comporter ;
- la cohabitation de `semantic` et `polygon` dans un même job
  (exemple 05) ;
- l'affichage des quatre jobs simultanés de l'exemple 09.

### 3. Le champ `id` des catégories

La documentation Kili montre souvent un champ `id` dans les catégories
(`"id": "category1"`). Les interfaces de ce dépôt **ne le renseignent
pas**, ce champ semblant généré côté plateforme. Si l'UI ou l'import
s'en plaint, il faudra l'ajouter dans
`kili_examples.interfaces.build_category`.

### 4. `isNew`

La documentation mentionne un champ `isNew` sur les jobs. Son rôle exact
n'est pas documenté clairement et il est **omis** ici. Les fixtures du
SDK le montrent tantôt à `true`, tantôt à `false`, sans effet apparent
sur la validation.

### 5. `content` sur une annotation PDF

Dans l'exemple 06, le champ `content` de l'annotation parente est laissé
vide (`""`), le texte étant porté par le sous-job `TRANSCRIPTION`. Cette
convention vient d'une fixture du SDK
(`tests/unit/services/export/test_kili.py`) ; à confirmer que la
plateforme n'attend pas plutôt le texte reconnu à cet endroit.

### 6. Chemins locaux dans `content_array`

Les exemples PDF et image passent des **chemins de fichiers locaux** à
`append_many_to_dataset`. C'est le comportement documenté, mais sur une
instance on-premise, la question de savoir si le fichier est téléversé
par le SDK ou doit être accessible depuis le serveur mérite une
vérification sur le premier import.

### 7. `model_name` et sémantique prediction / inference

`create_predictions` crée des labels de type `PREDICTION`. La
distinction avec `INFERENCE` (via
`append_labels(label_type="INFERENCE")`) est décrite d'après la
documentation, mais son effet concret dans le flux de travail de
l'équipe reste à observer.

### 8. La taille de lot

`kili_examples.assets.DEFAULT_BATCH_SIZE` vaut 100, valeur alignée sur
`MUTATION_BATCH_SIZE` du SDK. Elle n'a pas été éprouvée sur un import
volumineux contre l'instance on-premise, dont les limites peuvent
différer du SaaS.

### 9. Jobs non couverts

Ces `mlTask` existent mais n'ont pas d'exemple ici :
`PAGE_LEVEL_CLASSIFICATION`, `PAGE_LEVEL_TRANSCRIPTION`,
`NAMED_ENTITIES_RELATION`, `OBJECT_RELATION`, `POSE_ESTIMATION`.

## Écart avec la commande d'origine

La commande `copier` fournie dans la spécification employait des noms de
variables (`project_profile`, `use_mkdocs`, `use_precommit`,
`use_docker`) qui ne correspondent pas à ceux du template. Les vrais
noms, lus dans son `copier.yml`, sont `add_docs`, `add_pre_commit`,
`add_docker`, `add_dvc`, `add_type_checking`. Le scaffold a été lancé
avec ces noms-là, et a réussi.
