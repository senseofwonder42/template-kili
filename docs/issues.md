# Questions et issues

La boucle qualité d'un projet : l'annotateur demande un avis, le
relecteur conteste une annotation, le responsable qualité clôture.

Exemple de référence : `examples/12_issues_and_questions.py`.

!!! info "Pilotable depuis le SDK"
    La documentation Kili ne décrit cette boucle que côté interface. Le
    SDK Python la couvre pourtant entièrement : création, lecture,
    comptage et changement de statut. Tout ce qui suit est lu dans le
    source de `kili` 2.176.1.

## Question ou issue ?

Ce sont **deux objets de même nature** — côté API, un seul type `Issue`,
distingué par son champ `type`. Ce qui change, c'est ce à quoi ils se
rattachent et qui les émet.

| | Question | Issue |
| --- | --- | --- |
| Se rattache à | un **asset** | un **label**, éventuellement un objet de ce label |
| Émise par | l'annotateur qui bloque | le relecteur qui conteste |
| Existe avant annotation | oui | non — il faut un label |
| Méthode de création | `create_questions` | `create_issues` |
| `type` renvoyé | `"QUESTION"` | `"ISSUE"` |

## Poser une question

```python
kili.create_questions(
    project_id=project_id,
    asset_id_array=["ckg22d81r0jrg0885unmuswj8"],
    text_array=["Ce sinistre relève de deux garanties, laquelle retenir ?"],
)
```

`asset_external_id_array` remplace `asset_id_array` si l'on ne connaît
que l'identifiant métier.

## Ouvrir une issue

Une issue vise un label, donc il faut d'abord ses identifiants :

```python
labels = kili.labels(
    project_id=project_id,
    fields=["id", "assetId", "jsonResponse"],
)
kili.create_issues(
    project_id=project_id,
    label_id_array=[label["id"] for label in labels],
    object_mid_array=[first_object_mid(label["jsonResponse"]) for label in labels],
    text_array=["La zone encadrée ne correspond pas au dégât décrit."],
)
```

### Viser un objet précis

`object_mid_array` est le raffinement utile : chaque annotation d'un
`jsonResponse` porte un `mid`, et le passer accroche le signalement
**sur l'objet** — la bonne boîte, le bon polygone, la bonne entité —
plutôt que sur le label entier.

```python
{
  "ZONE_ENDOMMAGEE": {
    "annotations": [
      {"mid": "20240101", "categories": [{"name": "PARE_CHOCS"}], ...}
    ]
  }
}
```

`None` est accepté : un label de pure classification n'a pas d'objet, et
l'issue porte alors sur le label entier. C'est ce que renvoie
`kili_examples.workflow.first_object_mid` dans ce cas.

## Lire les deux à la fois

`kili.issues(...)` renvoie **questions et issues mélangées**. Deux
façons de s'y retrouver :

```python
# Tout lire, trier côté client
tout = kili.issues(
    project_id=project_id,
    fields=["id", "type", "status", "assetId", "objectMid"],
)

# Ou demander un seul type au serveur
questions = kili.issues(project_id=project_id, issue_type="QUESTION")
ouvertes = kili.issues(project_id=project_id, status="OPEN")
```

`kili.count_issues(project_id, issue_type=..., status=...)` renvoie le
compte sans rapatrier les objets.

Côté assets, le même filtre donne la liste de reprises d'un relecteur :

```python
kili.assets(
    project_id=project_id,
    fields=["externalId"],
    issue_type="ISSUE",
    issue_status="OPEN",
)
```

## Cycle de vie

Trois statuts : `OPEN`, `SOLVED` (traité) et `CANCELLED` (sans objet).

```python
kili.update_issue_status(issue_id=issue["id"], status="SOLVED")
```

L'exemple 12 tient volontairement cette étape **hors du chemin par
défaut** (`--resolve` doit être demandé explicitement) : clôturer en
masse des signalements qu'on n'a pas traités vide la boucle qualité de
son sens.

Répondre à une question relève de l'interface, pas d'un script : c'est
une conversation entre l'annotateur et son référent.

## Voir aussi

- [Piloter la file d'annotation](workflow.md) — métadonnées, priorité,
  assignation.
- [Export](export.md) — récupérer les labels une fois la boucle refermée.
