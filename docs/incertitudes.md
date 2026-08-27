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
- `kili.update_properties_in_assets(...)`
- `kili.assign_assets_to_labelers(...)`
- `kili.project_users(...)`
- `kili.create_questions(...)`, `kili.create_issues(...)`,
  `kili.issues(...)`, `kili.count_issues(...)`,
  `kili.update_issue_status(...)`

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

### 9. LLM_STATIC (exemple 10) — la zone la plus incertaine

L'exemple 10 s'appuie sur une partie du SDK plus récente et moins
documentée que le reste. Les signatures de `kili.llm.import_conversations`
et `kili.llm.export` sont confirmées dans le source 2.176.1, et les
formats proviennent des fixtures de test du SDK
(`tests/unit/llm/services/export/test_llm_static_export.py`). Restent à
vérifier :

- **La règle « exactement deux ASSISTANT par tour ».** Elle vient de la
  documentation. Notre montage (référence + prédiction) la respecte,
  mais le comportement en cas de violation n'est pas connu.
- **Le pré-remplissage via `label` à l'import.** Le format
  `{"round": {"JOB": {"0": {"categories": [...]}}}}` est repris des
  fixtures d'export. Qu'il soit accepté **en entrée** par
  `import_conversations` est plausible mais non prouvé. Si l'import
  échoue, repli : importer sans `label`, puis annoter dans l'UI. Le
  coût serait faible ici — un seul job est pré-rempli
  (`REFERENCE_CORRECTE = OUI`).
- **La clé `text` d'un job TRANSCRIPTION au niveau `round`.** Les deux
  champs libres de l'exemple (`REFERENCE_CORRIGEE`,
  `REPONSE_SECONDAIRE`) sont relus via `label.round.<JOB>."0".text`, par
  analogie avec les jobs de classification. La forme exacte que renvoie
  l'export pour une transcription LLM n'a pas été observée : c'est, avec
  le point suivant, ce qu'il faut vérifier en premier sur un vrai
  projet. `extract_text` renvoie `None` si la clé manque, donc une
  divergence de format se traduirait par des champs libres silencieusement
  ignorés — pas par une erreur.
- **La ré-importation d'une conversation existante.** L'exemple appelle
  `import_conversations` une seconde fois (étape `--predict`) avec les
  mêmes `externalId`. Le SDK peut soit mettre à jour, soit créer un
  doublon, soit refuser. **À tester en premier** : si le comportement
  n'est pas une mise à jour, fusionner les étapes `--upload` et
  `--predict` en passant `label` dès le premier import (le code est déjà
  structuré pour, voir `upload_predictions`).
- **La clé `level` dans le json_interface.** Les valeurs viennent de
  `kili_formats.types.JobLevel` ; leur rendu dans l'éditeur n'a pas été
  observé.
- **Le format exact renvoyé par `kili.llm.export`.** `extract_category`
  lit `label.round.<JOB>."0".categories` et tolère les deux formes de
  `categories` (liste de chaînes ou de dictionnaires), mais la structure
  réelle de l'export reste à confirmer. C'est le point à vérifier avant
  de se fier au dataset révisé.
- **`metadata` au retour.** On y range `question_id`, `prediction`,
  `judge_verdict` et `scope`. Si l'export ne les restitue pas,
  `_prediction_of` retombe sur le dernier chat item `ASSISTANT` et
  `_question_id_of` sur l'`externalId` — deux replis déjà en place. En
  revanche `judge_verdict` n'a **pas** de repli : sans lui, le dataset
  reste correct mais les statistiques de désaccord juge / métier du
  rapport sont fausses (tout sera compté comme si le juge avait validé).
- **Le `mlTask` `COMPARISON`.** Mentionné dans la documentation et
  présent dans les fixtures, il n'est pas utilisé par l'exemple 10.
  Il conviendrait à un choix « laquelle est la meilleure », mais pas au
  besoin traité ici : la référence et la prédiction peuvent être
  correctes toutes les deux, ou fausses toutes les deux, ce qu'une
  comparaison par paire ne sait pas exprimer.

### 10. Pilotage du projet (exemples 11 et 12)

Ces deux exemples n'annotent rien : ils n'ont donc **aucune** validation
hors ligne équivalente à `ParsedJobs`. Seules leurs fonctions pures sont
testées (`tests/test_workflow.py`). Points à vérifier :

- **Identifiants d'annotateur : `user.id` ou email ?** Les docstrings du
  SDK 2.176.1 se contredisent en apparence :
  `assign_assets_to_labelers` annonce des *userIds*,
  `update_properties_in_assets(to_be_labeled_by_array=...)` des
  *emails*. L'exemple 11 emprunte les deux chemins (le second via
  `--labeler-email`) et journalise les valeurs lues par
  `project_users` : c'est le premier run qui tranchera.
- **`json_metadatas` remplace-t-il ou fusionne-t-il ?** L'exemple 11
  suppose un **remplacement** et relit donc la métadonnée existante
  avant de réécrire (`merge_metadata`). Le motif reste correct si la
  plateforme fusionne ; il faut simplement confirmer laquelle des deux
  sémantiques s'applique, en comparant l'avant/après de l'étape
  `--enrich`.
- **Le champ `toBeLabeledBy` d'un asset.** Il est typé `ProjectUser`
  (singulier) dans `kili/types.py` alors que l'écriture attend une
  **liste** d'annotateurs. L'exemple 11 le demande sous la forme
  `toBeLabeledBy.user.email` à l'étape `--inspect` ; si la requête
  échoue, c'est ce champ qu'il faut corriger.
- **Le réglage « Auto assign » de l'organisation.** Son interaction avec
  une assignation programmatique n'est pas documentée.
- **Une issue sur un label de type `PREDICTION`.** L'exemple 12 prend
  les premiers labels du projet sans filtrer sur `labelType`. Si la
  plateforme refuse les signalements sur des pré-annotations, il faudra
  ajouter `label_type_in=["DEFAULT", "REVIEW"]` à l'appel
  `kili.labels(...)`.
- **Le typage et la visibilité des métadonnées.** La documentation
  mentionne `update_properties_in_project` pour déclarer une clé comme
  chaîne, nombre ou date et la rendre filtrable dans l'interface. Ce
  n'est pas couvert ici : les métadonnées de l'exemple 11 pourraient
  n'être filtrables que par l'API tant que ce réglage n'est pas fait.

### 11. Jobs non couverts

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
