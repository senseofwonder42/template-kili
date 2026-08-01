# Kili by example

Dépôt de référence interne pour piloter **Kili Technology** depuis son
SDK Python, appliqué à des cas d'usage assurance.

Neuf squelettes exécutables, un par type d'annotation. Chacun déroule le
même cycle de vie en quatre étapes :

1. créer le projet et son interface d'annotation (`json_interface`) ;
2. importer les assets ;
3. importer les prédictions du modèle (pré-annotations) ;
4. exporter les annotations obtenues.

> Le contenu le plus utile de ce dépôt est la **forme exacte du
> `json_interface` et de la charge utile de prédiction pour chaque type
> d'annotation** — ce que l'équipe n'avait documenté nulle part.

---

## ⚠️ Code non testé

**Rien de ce dépôt n'a été exécuté contre une instance Kili.** Il n'y
avait ni instance, ni clé d'API, ni accès réseau lors de l'écriture.

Ce qui a été vérifié localement : les signatures du SDK (lues dans le
source de `kili` 2.176.1), la validité des charges utiles (via le
parseur du SDK, hors ligne), le lint, les tests et la génération des
données d'exemple.

Ce qui reste à confirmer est listé dans la page
[Incertitudes](incertitudes.md). **Lisez-la avant le premier run.**

### Procédure de première exécution sur le serveur

À faire dans cet ordre, sur un projet jetable :

1. **Configurer l'accès.** Copier `.env.example` vers `.env`, y mettre
   `KILI_API_KEY` et `KILI_API_ENDPOINT` (sur une instance
   auto-hébergée, l'URL se termine généralement par
   `/api/label/v2/graphql`).
2. **Installer.** `uv sync`
3. **Générer les données d'exemple.**
   `uv run python scripts/generate_sample_data.py`
4. **Créer un seul projet, sans rien importer.**
   ```bash
   uv run python examples/01_text_classification.py --create
   ```
   Noter le `project_id` affiché.
5. **Vérifier l'interface dans l'UI.** Ouvrir le projet dans Kili et
   contrôler que les catégories s'affichent — et surtout que le sous-job
   `SOUS_TYPE_AUTO` apparaît bien quand on coche « Sinistre
   automobile ». C'est le point le plus susceptible d'être faux.
6. **Importer les assets** sur ce même projet :
   ```bash
   uv run python examples/01_text_classification.py --upload \
     --project-id <project_id>
   ```
7. **Importer les prédictions**, puis vérifier dans l'UI qu'elles
   apparaissent bien comme pré-annotations :
   ```bash
   uv run python examples/01_text_classification.py --predict \
     --project-id <project_id>
   ```
8. **Exporter** :
   ```bash
   uv run python examples/01_text_classification.py --export \
     --project-id <project_id>
   ```
9. Seulement ensuite, dérouler les exemples 02 à 09 — en commençant par
   le 04 (géométrie image) et le 06 (géométrie PDF), les deux plus
   susceptibles de demander un ajustement.
10. **Supprimer les projets jetables** créés pendant cette recette.

---

## Prérequis

- Python 3.12 et [uv](https://docs.astral.sh/uv/)
- un accès à l'instance Kili on-premise (clé d'API)

## Installation

```bash
uv sync
cp .env.example .env   # puis renseigner les deux variables Kili
```

Les identifiants ne sont **jamais** écrits dans le code : ils sont lus
depuis `.env` par pydantic-settings. Un `.env` absent ou incomplet
provoque une erreur explicite au démarrage
(`MissingKiliCredentialsError`).

## Générer les données d'exemple

```bash
uv run python scripts/generate_sample_data.py
```

Produit dans `data/samples/` des documents d'assurance **entièrement
synthétiques** : déclarations et emails (JSONL), constats, attestations,
avenants et factures (PDF), photos de dégâts (images). Génération
déterministe et idempotente.

**Aucune donnée réelle n'entre dans ce dépôt.** Le dossier `data/` est
gitignoré.

## Lancer un exemple

```bash
# le cycle complet (crée un nouveau projet)
uv run python examples/01_text_classification.py

# une étape seulement, sur un projet existant
uv run python examples/01_text_classification.py --predict --project-id <id>
```

Chaque script accepte `--create`, `--upload`, `--predict`, `--export`.
Sans aucun drapeau, les quatre étapes s'enchaînent. `--project-id`
permet de rejouer une étape sans recréer de projet.

---

## Besoin métier → type d'annotation → exemple

| Besoin métier | Type d'annotation Kili | Exemple |
| --- | --- | --- |
| Trier des déclarations de sinistre écrites | `CLASSIFICATION` (+ sous-job) | [`01_text_classification.py`](./examples/01_text_classification.py) |
| Typer des documents contractuels PDF | `CLASSIFICATION` sur PDF | [`02_pdf_classification.py`](./examples/02_pdf_classification.py) |
| Estimer la gravité de dégâts sur photo | `CLASSIFICATION` mono + multi-label | [`03_image_classification.py`](./examples/03_image_classification.py) |
| Localiser les zones abîmées d'un véhicule | `OBJECT_DETECTION` (`rectangle`) | [`04_object_detection.py`](./examples/04_object_detection.py) |
| Mesurer une surface sinistrée (dégât des eaux) | `OBJECT_DETECTION` (`semantic`, `polygon`) | [`05_segmentation.py`](./examples/05_segmentation.py) |
| Relever les champs d'un constat amiable | `OBJECT_DETECTION` + sous-job `TRANSCRIPTION` | [`06_pdf_ocr.py`](./examples/06_pdf_ocr.py) |
| Extraire les champs d'une facture de réparation | `TRANSCRIPTION` (un job par champ) | [`07_vlm_text_extraction.py`](./examples/07_vlm_text_extraction.py) |
| Repérer contrat, montant, date dans un email | `NAMED_ENTITIES_RECOGNITION` | [`08_ner_text.py`](./examples/08_ner_text.py) |
| Traiter un PDF de sinistre en une seule passe | interface multi-jobs + job conditionnel | [`09_custom_multitask_pdf.py`](./examples/09_custom_multitask_pdf.py) |

L'exemple **09** est celui à lire pour comprendre qu'une interface Kili
n'est qu'un arbre JSON de jobs, combinables librement.

## Organisation du dépôt

```
examples/          les neuf squelettes — la source de vérité
src/kili_examples/ le peu de code partagé (client, interfaces, import, export)
scripts/           génération des données synthétiques
notebooks/         trois visites guidées
docs/              une page par type d'annotation + les incertitudes
tests/             tests des helpers purs, client Kili mocké
```

### Scripts ou notebooks ?

Les **scripts de `examples/` sont la source de vérité** : testés,
versionnés, exécutables en une commande.

Les **notebooks sont une visite guidée** ; ils importent le code des
scripts au lieu de le dupliquer.

| Notebook | Contenu |
| --- | --- |
| `01_prise_en_main.ipynb` | connexion, projet minimal, anatomie du `json_interface` |
| `02_cycle_complet.ipynb` | les quatre étapes déroulées sur l'exemple 01 |
| `03_interface_personnalisee.ipynb` | construction pas à pas de l'interface multi-jobs de l'exemple 09 |

`nbstripout` (via pre-commit) retire les sorties des notebooks avant
chaque commit.

## Documentation

```bash
uv run --group docs mkdocs serve
```

- [Classification](classification.md)
- [Détection d'objets et segmentation](object-detection.md)
- [Entités nommées](ner.md)
- [Transcription et OCR](transcription.md)
- [Spécificités PDF](pdf-ocr.md)
- [Export](export.md)
- [**Incertitudes**](incertitudes.md)

## Conventions

- **Prose en français** (README, docs, docstrings, commentaires) : c'est
  de la documentation d'équipe interne.
- **Code en anglais** (noms de fonctions, de fichiers, de variables).
- **Ontologies en vocabulaire métier français** (`SINISTRE_AUTO`,
  `MONTANT_FRANCHISE`, `DATE_ACCIDENT`) : les annotateurs les lisent.
- Le SDK Kili n'est **pas** encapsulé derrière une façade : les exemples
  appellent les vraies méthodes, pour qu'on apprenne l'API et non notre
  abstraction. On préfère la répétition entre exemples au partage
  astucieux — c'est du code pédagogique.

---

# Outillage du projet

## 🧪 Tests

```bash
uv run pytest
```

Les tests ne touchent jamais au réseau et ne demandent aucune clé : le
client Kili est remplacé par un double, et les charges utiles de
prédiction sont validées hors ligne par le parseur du SDK.

## 🧹 Lint et formatage

```bash
uv run ruff check .
uv run ruff format .
```

## 📦 Gestion des dépendances

Ce projet suit le workflow `uv` moderne.

```bash
uv add <package>      # ajouter
uv remove <package>   # retirer
```

> **⚠️ Important :** ne pas utiliser `uv pip install` ni créer d'environnement
> à la main avec `uv venv`. Les commandes `uv add/remove` maintiennent
> `pyproject.toml`, `uv.lock` et le venv synchronisés.

Les tâches courantes sont aussi regroupées dans le [Makefile](./Makefile) :
`make help` pour la liste.

## 🪝 Pre-commit

```bash
uv run pre-commit install        # une seule fois
uv run pre-commit run --all-files
```

## ⚙️ Variables d'environnement

Toutes les variables d'environnement se déclarent dans
[config.py](./src/kili_examples/config.py) :

```python
class Settings(BaseSettings):
    """Load environment variables as settings."""

    kili_api_key: str | None = None       # KILI_API_KEY
    kili_api_endpoint: str | None = None  # KILI_API_ENDPOINT
```

## ♻️ Mise à jour depuis le template

Ce projet a été généré avec [Copier](https://copier.readthedocs.io/).

```bash
copier update --trust
```

## 📧 Contacts

* **afleuren** - [antoine.j.fleurentin@gmail.com](mailto:antoine.j.fleurentin@gmail.com)
