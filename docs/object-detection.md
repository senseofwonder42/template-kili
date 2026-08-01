# Détection d'objets et segmentation

Localiser des zones dans une image ou une page de PDF : boîtes
englobantes, polygones, masques de segmentation.

Exemples de référence : `examples/04_object_detection.py` (rectangles),
`examples/05_segmentation.py` (polygones et masques).

## json_interface

```json
{
  "jobs": {
    "ZONES_ENDOMMAGEES": {
      "mlTask": "OBJECT_DETECTION",
      "content": {
        "categories": {
          "IMPACT": {"children": [], "name": "Impact", "color": "#FF6B6B"},
          "RAYURE": {"children": [], "name": "Rayure", "color": "#FFB300"}
        },
        "input": "radio"
      },
      "instruction": "Entourez chaque zone endommagée.",
      "tools": ["rectangle"],
      "required": 1,
      "isChild": false
    }
  }
}
```

Le `mlTask` vaut `OBJECT_DETECTION` **quel que soit l'outil**. C'est le
tableau `tools` qui distingue les formes.

### Les outils disponibles

| Outil | Forme produite |
| --- | --- |
| `rectangle` | boîte englobante (4 sommets) |
| `polygon` | contour fermé, dessiné point par point |
| `semantic` | masque de segmentation sémantique |
| `marker` | point unique |
| `polyline` / `vector` | ligne ouverte |
| `pose` | points d'articulation (pose estimation) |

*(Liste relevée dans le SDK 2.176.1, module
`kili/services/label_data_parsing/annotation.py`.)*

Plusieurs outils peuvent cohabiter dans un même job :
`"tools": ["semantic", "polygon"]`. La réponse portera alors un champ
`type` indiquant l'outil effectivement utilisé.

## Géométrie : les coordonnées normalisées

Kili n'utilise pas de pixels mais des coordonnées **normalisées dans
[0, 1]**, ce qui rend les annotations indépendantes de la résolution.

- origine `(0, 0)` : coin **haut-gauche** ;
- `x` croît vers la droite, `y` vers le bas.

Une boîte occupant le quart supérieur gauche va donc de `(0, 0)` à
`(0.5, 0.5)`.

L'ordre des sommets d'un rectangle est : bas-gauche, haut-gauche,
haut-droit, bas-droit.

!!! tip "Convertir depuis des pixels"
    Le SDK fournit
    `kili.utils.labels.bbox.bbox_points_to_normalized_vertices(...)`,
    qui accepte des points en pixels avec `img_width` / `img_height` et
    gère l'origine (`top_left` ou `bottom_left`).

## Charge utile de prédiction

```python
{
    "ZONES_ENDOMMAGEES": {
        "annotations": [
            {
                "categories": [{"name": "IMPACT", "confidence": 87}],
                "boundingPoly": [
                    {
                        "normalizedVertices": [
                            {"x": 0.62, "y": 0.70},
                            {"x": 0.62, "y": 0.48},
                            {"x": 0.87, "y": 0.48},
                            {"x": 0.87, "y": 0.70},
                        ]
                    }
                ],
                "type": "rectangle",
                "mid": "prediction-impact-1",
            }
        ]
    }
}
```

| Clé | Rôle |
| --- | --- |
| `annotations` | la clé racine — un job de détection produit **plusieurs** objets |
| `boundingPoly` | une **liste** de polygones : plusieurs entrées pour une forme en morceaux disjoints |
| `normalizedVertices` | les sommets ; exactement 4 pour un rectangle, autant que nécessaire pour un polygone |
| `type` | l'outil employé ; doit figurer parmi les `tools` du json_interface |
| `mid` | identifiant de l'objet, unique au sein de l'asset. Kili le génère pour les annotations humaines ; à fournir pour les prédictions |

### Formes en plusieurs morceaux

Une zone discontinue reste **une seule** annotation (donc un seul `mid`)
avec plusieurs entrées dans `boundingPoly` :

```python
{
    "categories": [{"name": "PEINTURE_CLOQUEE", "confidence": 61}],
    "boundingPoly": [
        {"normalizedVertices": [...]},  # première tache
        {"normalizedVertices": [...]},  # seconde tache
    ],
    "type": "polygon",
    "mid": "prediction-cloquage-1",
}
```

## Sur un PDF

La géométrie d'une annotation PDF est décrite dans
[OCR et PDF](pdf-ocr.md) : elle ajoute `polys` et `pageNumberArray`, et
se loge dans une liste `annotations` imbriquée.

## Export vers un format d'entraînement

Pour entraîner un modèle de détection, `kili.export_labels(...)` produit
directement du `yolo_v4` / `yolo_v5` / `yolo_v7` / `yolo_v8`, du `coco`
ou du `pascal_voc`. Voir [Export](export.md).
