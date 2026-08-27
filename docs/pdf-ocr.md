# Spécificités des assets PDF

Ce que le PDF change par rapport au texte et à l'image.

Exemples de référence : `examples/02_pdf_classification.py`,
`examples/06_pdf_ocr.py`, `examples/09_custom_multitask_pdf.py`.

## Import

Pour un projet `input_type="PDF"`, `content_array` reçoit des **chemins
de fichiers locaux** (ou des URLs accessibles depuis le serveur Kili) —
et non le contenu lui-même comme pour un projet `TEXT`.

```python
kili.append_many_to_dataset(
    project_id=project_id,
    content_array=[str(path) for path in pdfs],
    external_id_array=[path.stem for path in pdfs],
    json_metadata_array=[{"nombre_de_pages": 3}, ...],
)
```

`json_metadata_array` est libre : les métadonnées sont consultables dans
l'interface et ressortent à l'export, ce qui aide à filtrer les assets.
Voir [Piloter la file d'annotation](workflow.md) pour les clés réservées,
la mise à jour après import et le filtrage `metadata_where`.

## Classification : rien ne change

Pour un job `CLASSIFICATION`, la réponse a exactement la même forme que
sur un asset texte ou image :

```python
{"TYPE_DOCUMENT": {"categories": [{"name": "FACTURE", "confidence": 88}]}}
```

C'est dès qu'on annote des **zones** que la géométrie PDF apparaît.

## Géométrie PDF

Une annotation positionnée dans un PDF porte trois clés, regroupées dans
une liste `annotations` **imbriquée** dans l'annotation :

| Clé | Rôle |
| --- | --- |
| `boundingPoly` | l'enveloppe globale de l'annotation |
| `polys` | les contours effectifs : un rectangle par ligne quand l'annotation court sur plusieurs lignes |
| `pageNumberArray` | la ou les pages concernées, **indexées à partir de 1** |

```python
{
    "CHAMPS_CONSTAT": {
        "annotations": [
            {
                "categories": [{"name": "DATE_ACCIDENT", "confidence": 85}],
                "mid": "prediction-champ-0",
                "type": "rectangle",
                "content": "",
                "annotations": [          # <- géométrie imbriquée
                    {
                        "boundingPoly": [
                            {"normalizedVertices": [
                                {"x": 0.30, "y": 0.19},
                                {"x": 0.30, "y": 0.15},
                                {"x": 0.55, "y": 0.15},
                                {"x": 0.55, "y": 0.19},
                            ]}
                        ],
                        "polys": [
                            {"normalizedVertices": [...]}
                        ],
                        "pageNumberArray": [1],
                    }
                ],
                "children": {
                    "TRANSCRIPTION_CHAMP": {"text": "12/03/2025"}
                },
            }
        ]
    }
}
```

!!! warning "Le piège de l'imbrication"
    Sur une **image**, `boundingPoly` est directement à la racine de
    l'annotation. Sur un **PDF**, il se trouve dans une liste
    `annotations` imbriquée, aux côtés de `polys` et `pageNumberArray`.
    C'est la différence la plus facile à manquer en passant d'un exemple
    à l'autre.

Les coordonnées suivent les mêmes conventions que pour l'image :
normalisées dans [0, 1], origine en haut à gauche. Elles sont relatives
à **la page** désignée par `pageNumberArray`.

## Jobs spécifiques au PDF

Kili expose deux `mlTask` propres au format paginé :

- `PAGE_LEVEL_CLASSIFICATION` : classer chaque page indépendamment ;
- `PAGE_LEVEL_TRANSCRIPTION` : transcrire page par page.

Ils ne sont pas couverts par les exemples de ce dépôt — voir
[Incertitudes](incertitudes.md).
