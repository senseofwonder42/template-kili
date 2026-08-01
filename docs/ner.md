# Entités nommées (NER)

Repérer des portions de texte porteuses d'information : numéro de
contrat, montant, date, nom de personne.

Exemple de référence : `examples/08_ner_text.py`.

## json_interface

```json
{
  "jobs": {
    "ENTITES_EMAIL": {
      "mlTask": "NAMED_ENTITIES_RECOGNITION",
      "content": {
        "categories": {
          "NUMERO_CONTRAT": {
            "children": [],
            "name": "Numéro de contrat",
            "color": "#472CED"
          },
          "MONTANT": {"children": [], "name": "Montant", "color": "#3CD876"}
        },
        "input": "radio"
      },
      "instruction": "Surlignez les entités utiles au traitement.",
      "required": 1,
      "isChild": false
    }
  }
}
```

## Charge utile de prédiction (asset TEXT)

```python
{
    "ENTITES_EMAIL": {
        "annotations": [
            {
                "categories": [{"name": "NUMERO_CONTRAT", "confidence": 90}],
                "beginOffset": 56,
                "content": "AUTO-2024-1187",
                "mid": "entite-0",
            }
        ]
    }
}
```

| Clé | Rôle |
| --- | --- |
| `beginOffset` | index du **premier caractère** de l'entité dans le texte de l'asset, compté à partir de 0 |
| `content` | le texte exact surligné ; sa longueur détermine la fin de l'entité |
| `mid` | identifiant de l'entité, unique au sein de l'asset |

!!! danger "Le piège des offsets"
    L'invariant à respecter est :

    ```python
    texte[beginOffset : beginOffset + len(content)] == content
    ```

    Un décalage d'un seul caractère déplace le surlignage dans
    l'interface — **sans lever d'erreur à l'import**. Calculez toujours
    les offsets par programme (`str.find`, `re.finditer`) sur le texte
    exact envoyé à Kili, jamais à la main.

    Attention aux accents et aux retours à la ligne : les offsets se
    comptent en caractères Python, pas en octets.

    L'exemple 08 est couvert par un test qui vérifie cet invariant
    (`tests/test_predictions.py::test_ner_offsets_match_the_asset_text`).

## Sur un PDF

Le même `mlTask` s'applique aux assets PDF, mais l'entité porte en plus
sa position dans la page : une liste `annotations` imbriquée contenant
`boundingPoly`, `polys` et `pageNumberArray`. Voir
[OCR et PDF](pdf-ocr.md) et `examples/09_custom_multitask_pdf.py`.

Quand une entité court sur plusieurs lignes, `polys` contient un
rectangle par ligne alors que `boundingPoly` reste l'enveloppe globale.

## Relations entre entités

Kili propose un `mlTask` `NAMED_ENTITIES_RELATION` pour relier deux
entités entre elles (par exemple un montant à la prestation
correspondante). Ce cas n'est pas couvert par les exemples de ce dépôt.
