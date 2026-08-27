# Piloter la file d'annotation

Métadonnées, priorité, assignation : ce qui se joue **autour** de
l'annotation, une fois les assets importés.

Exemple de référence : `examples/11_queue_management.py`.

## Métadonnées d'asset

Une métadonnée est un dictionnaire JSON libre attaché à un asset. Elle
est visible dans l'interface d'annotation, ressort à l'export, et surtout
elle est **filtrable**.

### Les deux temps de la métadonnée

À l'import, via `json_metadata_array` — une entrée par asset :

```python
kili.append_many_to_dataset(
    project_id=project_id,
    content_array=[...],
    external_id_array=[...],
    json_metadata_array=[{"branche": "AUTO", "text": "Collision..."}],
)
```

Après coup, via `update_properties_in_assets` — pour la donnée qui
arrive plus tard (une remontée du back-office, un score de modèle, un
numéro de dossier) :

```python
kili.update_properties_in_assets(
    project_id=project_id,
    external_ids=["declaration_000"],
    json_metadatas=[{"branche": "AUTO", "numero_contrat": "AUTO-2025-0001"}],
)
```

!!! warning "La mise à jour remplace, elle ne fusionne pas"
    `json_metadatas` reçoit la métadonnée **entière** de l'asset.
    N'envoyer que les nouvelles clés effacerait les précédentes. Le motif
    sûr est donc lecture, fusion, écriture :

    ```python
    assets = kili.assets(project_id, fields=["externalId", "jsonMetadata"])
    kili.update_properties_in_assets(
        project_id=project_id,
        external_ids=[a["externalId"] for a in assets],
        json_metadatas=[
            merge_metadata(a.get("jsonMetadata"), nouvelles_cles)
            for a in assets
        ],
    )
    ```

    `merge_metadata` est dans `kili_examples.workflow`. Que la
    plateforme remplace effectivement au lieu de fusionner reste à
    confirmer au premier run (voir [Incertitudes](incertitudes.md)) — le
    motif ci-dessus est correct dans les deux cas.

### Les trois clés réservées

`imageUrl`, `text` et `url` ont un traitement d'affichage particulier :
Kili les remonte **en tête** du panneau de métadonnées, là où les autres
clés tombent dans un tableau. On y met donc ce que l'annotateur doit voir
en premier.

| Clé | Usage |
| --- | --- |
| `text` | un extrait, un résumé, une consigne propre au dossier |
| `imageUrl` | une image de contexte (la photo du sinistre à côté du PDF) |
| `url` | un lien vers la fiche dans l'outil métier |

### Filtrer sur les métadonnées

C'est ce qui rend la métadonnée utile plutôt que décorative :

```python
kili.assets(project_id, metadata_where={"branche": "AUTO"})
kili.assets(project_id, metadata_where={"branche": ["AUTO", "HABITATION"]})
kili.assets(project_id, metadata_where={"montant": [1000, 5000]})
```

| Forme | Sens |
| --- | --- |
| `{"cle": "valeur"}` | égalité |
| `{"cle": ["a", "b"]}` | l'une ou l'autre valeur |
| `{"cle": [2, 10]}` | intervalle numérique |

Le même filtre est disponible dans la page Queue et dans Explore côté
interface.

## Priorité de file

La priorité est un **entier par asset**, mis à jour par la même méthode :

```python
kili.update_properties_in_assets(
    project_id=project_id,
    external_ids=external_ids,
    priorities=[2, 0, 1, 0],
)
```

- Par défaut, tout asset vaut **0**.
- **Plus le nombre est grand, plus l'asset est servi tôt.**
- À priorité égale, l'ordre est celui de création (FIFO).

La règle de calcul est métier, pas technique. Celle de l'exemple 11
(`kili_examples.workflow.claim_priority`) : un dégât des eaux passe
devant parce qu'il s'aggrave, un vol suit parce qu'il ouvre un délai
légal, le reste suit l'ordre d'arrivée.

## Assigner des assets à un annotateur

Répartir explicitement le travail évite que deux gestionnaires ouvrent le
même dossier, et permet de router un sinistre vers la personne qui a
l'expertise correspondante.

Le tableau attendu est une liste **par asset** des annotateurs autorisés :

```python
to_be_labeled_by_array = [["marie"], ["paul"], ["marie"]]
```

- une liste à plusieurs éléments ouvre l'asset à plusieurs personnes ;
- une **liste vide** retire les assignés et remet l'asset dans le pot
  commun.

### Deux méthodes, deux formats d'identifiant

!!! danger "Le piège"
    Les deux méthodes du SDK ne veulent **pas** la même chose.

| Méthode | Attend |
| --- | --- |
| `kili.assign_assets_to_labelers(to_be_labeled_by_array=...)` | des **identifiants** utilisateur (`user.id`) |
| `kili.update_properties_in_assets(to_be_labeled_by_array=...)` | des **emails** |

C'est ce que disent les docstrings du SDK 2.176.1 ; le point est à
confirmer au premier run.

Pour retrouver les membres d'un projet et leurs deux identifiants :

```python
membres = kili.project_users(
    project_id=project_id,
    fields=["id", "role", "user.id", "user.email"],
)
labelers = [m for m in membres if m["role"] == "LABELER"]
```

### Relire la file

```python
kili.assets(
    project_id=project_id,
    fields=["externalId", "priority", "jsonMetadata", "toBeLabeledBy.user.email"],
    metadata_where={"branche": "AUTO"},
)
```

`kili.assets` accepte aussi `assignee_in=[...]` pour ne ramener que la
charge d'une personne donnée.

## Voir aussi

- [Questions et issues](issues.md) — la boucle qualité, une fois
  l'annotation lancée.
- [Incertitudes](incertitudes.md) — ce qui reste à confirmer sur ces
  méthodes.
