# Transcription et OCR

Saisir du texte libre : relever la valeur d'un champ, transcrire une
mention manuscrite.

Exemples de référence : `examples/07_vlm_text_extraction.py`
(un job par champ), `examples/06_pdf_ocr.py` (zone + transcription).

## json_interface

Un job `TRANSCRIPTION` n'a **pas de catégories** : c'est `input` qui
définit la zone de saisie.

```json
{
  "jobs": {
    "MONTANT_TTC": {
      "mlTask": "TRANSCRIPTION",
      "content": {"categories": {}, "input": "textarea"},
      "instruction": "Montant total TTC en euros",
      "required": 1,
      "isChild": false
    }
  }
}
```

## Charge utile de prédiction

```python
{"MONTANT_TTC": {"text": "816.00"}}
```

La clé est `text` — et non `categories`. La valeur est **toujours une
chaîne** : convertissez les nombres avec `str()`.

## Deux montages possibles

### 1. Un job par champ (le plus simple)

Quand seule la valeur compte, sans sa position dans le document. C'est
le cas de l'extraction de champs de facture.

```python
{
    "NUMERO_FACTURE": {"text": "F-2025-0481"},
    "DATE_FACTURE": {"text": "12/03/2025"},
    "MONTANT_TTC": {"text": "816.00"},
}
```

!!! tip "Champs non extraits"
    Si le modèle n'a pas su lire un champ, **omettez la clé** plutôt que
    d'envoyer `{"text": ""}`. Kili n'affichera alors aucune
    pré-annotation pour ce job, ce qui se distingue clairement d'une
    valeur lue comme vide.

### 2. Zone + transcription (OCR assisté)

Quand la position compte : un job `OBJECT_DETECTION` dont chaque
catégorie déclare un sous-job `TRANSCRIPTION`.

```json
{
  "jobs": {
    "CHAMPS_CONSTAT": {
      "mlTask": "OBJECT_DETECTION",
      "content": {
        "categories": {
          "DATE_ACCIDENT": {
            "children": ["TRANSCRIPTION_CHAMP"],
            "name": "Date de l'accident"
          }
        },
        "input": "radio"
      },
      "tools": ["rectangle"],
      "required": 1,
      "isChild": false
    },
    "TRANSCRIPTION_CHAMP": {
      "mlTask": "TRANSCRIPTION",
      "content": {"categories": {}, "input": "textarea"},
      "instruction": "Recopiez la valeur lue dans la zone entourée.",
      "required": 1,
      "isChild": true
    }
  }
}
```

L'annotateur entoure la case, puis saisit ce qu'il y lit.

## Passer d'une sortie de modèle au JSON Kili

Un OCR ou un VLM renvoie typiquement un dictionnaire plat. La traduction
vers Kili tient en une table de correspondance explicite :

```python
FIELD_TO_JOB = {
    "numero_facture": "NUMERO_FACTURE",
    "montant_ttc": "MONTANT_TTC",
}

def predict(asset: dict) -> dict:
    model_output = run_vlm(asset)  # {"montant_ttc": "816.00", ...}
    response = {}
    for field_name, job_name in FIELD_TO_JOB.items():
        value = model_output.get(field_name)
        if value is None:
            continue  # champ non lu : on n'émet pas de clé
        response[job_name] = {"text": str(value)}
    return response
```

Isoler cette table rend visible le contrat entre le modèle et
l'ontologie : c'est le seul endroit à modifier si l'un des deux évolue.
