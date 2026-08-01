# Classification

Attribuer une ou plusieurs catégories à un asset entier (texte, PDF, image).

Exemples de référence : `examples/01_text_classification.py`,
`examples/02_pdf_classification.py`, `examples/03_image_classification.py`.

## json_interface

```json
{
  "jobs": {
    "TYPE_DOCUMENT": {
      "mlTask": "CLASSIFICATION",
      "content": {
        "categories": {
          "AVENANT": {"children": [], "name": "Avenant", "color": "#472CED"},
          "ATTESTATION": {"children": [], "name": "Attestation"}
        },
        "input": "radio"
      },
      "instruction": "Quel est le type de ce document ?",
      "required": 1,
      "isChild": false
    }
  }
}
```

### Le champ `input`

| Valeur | Comportement | Quand l'utiliser |
| --- | --- | --- |
| `radio` | une seule catégorie | mono-classe (le cas courant) |
| `checkbox` | plusieurs catégories | multi-label |
| `dropdown` | une seule, en liste déroulante | au-delà d'une dizaine de catégories |

### Points d'attention

- La **clé** de la catégorie (`AVENANT`) est l'identifiant stable : c'est
  elle qui apparaît dans les prédictions et les exports. Le champ `name`
  n'est qu'un libellé d'affichage, modifiable sans casser les données.
- `required` vaut `1` ou `0` — un entier, pas un booléen.

## Charge utile de prédiction

```python
{
    "TYPE_DOCUMENT": {
        "categories": [{"name": "AVENANT", "confidence": 88}]
    }
}
```

En multi-label (`checkbox`), on ajoute simplement des entrées :

```python
{
    "PARTIES_TOUCHEES": {
        "categories": [
            {"name": "PARE_CHOCS", "confidence": 91},
            {"name": "PORTIERE", "confidence": 63},
        ]
    }
}
```

`confidence` est un entier de 0 à 100. Facultatif pour une annotation
humaine, recommandé pour une prédiction : Kili l'affiche et permet de
filtrer les assets peu sûrs.

## Sous-jobs conditionnels

Un sous-job n'apparaît que si une catégorie précise est sélectionnée.
Deux conditions, toutes les deux nécessaires :

1. la catégorie parente déclare `"children": ["SOUS_TYPE_AUTO"]` ;
2. le job enfant porte `"isChild": true`.

```json
{
  "jobs": {
    "CLASSIFICATION_SINISTRE": {
      "mlTask": "CLASSIFICATION",
      "content": {
        "categories": {
          "SINISTRE_AUTO": {
            "children": ["SOUS_TYPE_AUTO"],
            "name": "Sinistre automobile"
          }
        },
        "input": "radio"
      },
      "required": 1,
      "isChild": false
    },
    "SOUS_TYPE_AUTO": {
      "mlTask": "CLASSIFICATION",
      "content": {
        "categories": {"COLLISION": {"children": [], "name": "Collision"}},
        "input": "radio"
      },
      "required": 0,
      "isChild": true
    }
  }
}
```

Dans la prédiction, la réponse du sous-job se loge sous la clé `children`
**de la catégorie qui le déclenche** :

```python
{
    "CLASSIFICATION_SINISTRE": {
        "categories": [
            {
                "name": "SINISTRE_AUTO",
                "confidence": 90,
                "children": {
                    "SOUS_TYPE_AUTO": {
                        "categories": [
                            {"name": "COLLISION", "confidence": 80}
                        ]
                    }
                },
            }
        ]
    }
}
```

!!! warning "Limite documentée par Kili"
    Seuls les jobs de **classification** et de **transcription** peuvent
    être des sous-jobs. La profondeur est limitée à quatre niveaux
    (un parent et trois niveaux de sous-jobs).
