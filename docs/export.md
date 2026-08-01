# Export des annotations

Deux façons de récupérer les annotations, à choisir selon l'usage.

## `kili.labels(...)` — lecture brute

Renvoie les labels tels qu'ils sont stockés : un `jsonResponse` par
label, exactement dans le format décrit par les autres pages de cette
documentation.

À privilégier pour inspecter, déboguer, ou réinjecter les annotations
dans un traitement maison. C'est ce que fait
`kili_examples.exports.export_labels_to_json`, utilisé par les neuf
exemples.

```python
labels = list(
    kili.labels(
        project_id=project_id,
        fields=["id", "jsonResponse", "labelType", "author.email", "assetId"],
    )
)
```

Nommer explicitement les `fields` documente ce dont on a besoin et évite
de rapatrier des colonnes inutiles.

### Les types de labels

`labelType` distingue l'origine d'une annotation :

| Type | Origine |
| --- | --- |
| `PREDICTION` | pré-annotation importée par `create_predictions` |
| `DEFAULT` | annotation humaine |
| `REVIEW` | annotation issue de l'étape de revue |
| `INFERENCE` | sortie de modèle destinée à la comparaison, non proposée à la correction |
| `AUTOSAVE` | sauvegarde automatique en cours d'annotation |

Filtrer avec `type_in=["DEFAULT", "REVIEW"]` pour ne récupérer que le
travail humain validé.

## `kili.export_labels(...)` — format d'entraînement

Écrit directement une archive dans un format consommable par les
frameworks de vision.

```python
kili.export_labels(
    project_id=project_id,
    filename="export.zip",
    fmt="coco",
)
```

Formats acceptés (relevés dans le SDK 2.176.1,
`kili/services/export/types.py`) :

`raw`, `kili`, `yolo_v4`, `yolo_v5`, `yolo_v7`, `yolo_v8`, `coco`,
`pascal_voc`, `geojson`.

### Quel format pour quelle tâche

| Format | Couvre |
| --- | --- |
| `kili` / `raw` | tout — le format natif, sans perte |
| `yolo_v4` … `yolo_v8` | boîtes englobantes uniquement |
| `coco` | boîtes et polygones |
| `pascal_voc` | boîtes |
| `geojson` | annotations géospatiales |

!!! warning "Les formats de vision ne couvrent pas tout"
    Un job `TRANSCRIPTION` ou `NAMED_ENTITIES_RECOGNITION` n'a pas
    d'équivalent en COCO, YOLO ou Pascal VOC. Pour ces tâches, restez
    sur le format natif via `kili.labels(...)` ou `fmt="kili"`.

Ce dépôt exporte en JSON natif (choix figé) ; les formats ci-dessus sont
documentés ici pour le jour où un modèle de détection devra être
entraîné.

## Où atterrissent les exports

Chaque exemple écrit dans
`data/processed/<nom_de_l_exemple>/labels.json`. Le dossier `data/` est
gitignoré : les annotations exportées ne sont jamais versionnées.
