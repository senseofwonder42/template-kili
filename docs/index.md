# Kili by example

Référence interne pour piloter **Kili Technology** depuis son SDK
Python, appliquée à des cas d'usage assurance.

!!! danger "Code non testé"
    Rien de ce dépôt n'a été exécuté contre une instance Kili. Lisez
    [Incertitudes](incertitudes.md) avant le premier run sur le serveur.

---

## Référence par type d'annotation

C'est le coeur de cette documentation : pour chaque type d'annotation,
le `json_interface` à envoyer et la charge utile de prédiction
correspondante.

<div class="grid cards" markdown>

-   🏷️ **[Classification](classification.md)**
    ---
    Attribuer des catégories à un asset entier. Mono-classe,
    multi-label, et sous-jobs conditionnels.

-   🔲 **[Détection et segmentation](object-detection.md)**
    ---
    Boîtes, polygones et masques. Les coordonnées normalisées et les
    outils disponibles.

-   🔤 **[Entités nommées](ner.md)**
    ---
    Surligner des portions de texte. Le piège des offsets de
    caractères.

-   ✍️ **[Transcription et OCR](transcription.md)**
    ---
    Saisie de texte libre, seule ou couplée à une zone.

-   📄 **[Spécificités PDF](pdf-ocr.md)**
    ---
    Ce que le format paginé change : `polys` et `pageNumberArray`.

-   🤖 **[Évaluation LLM](llm-static.md)**
    ---
    `LLM_STATIC` : comparer des sorties de modèles, arbitrer un
    LLM-as-judge. L'asset est une conversation.

-   📤 **[Export](export.md)**
    ---
    `labels()` ou `export_labels()` — formats natif, COCO, YOLO,
    Pascal VOC.

</div>

---

## Pilotage du projet

Ce qui se joue autour de l'annotation : préparer la file, puis suivre la
boucle qualité.

<div class="grid cards" markdown>

-   🎛️ **[File d'annotation](workflow.md)**
    ---
    Métadonnées d'asset (dont les clés réservées), priorité de file et
    assignation à un annotateur.

-   💬 **[Questions et issues](issues.md)**
    ---
    Une question vise un asset, une issue vise un label — voire un
    objet précis. Les deux se lisent ensemble.

</div>

---

## Autres sections

<div class="grid cards" markdown>

-   📖 **Prise en main**
    ---
    Installation, configuration `.env`, procédure de premier run.

    [➡️ Lire le README](readme.md)

-   💻 **Référence du code**
    ---
    Documentation générée depuis les docstrings du package
    `kili_examples`.

    [➡️ Explorer le code](reference/index.md)

-   🎓 **Notebooks**
    ---
    Trois visites guidées : prise en main, cycle complet, interface
    personnalisée.

    [➡️ Voir les notebooks](notebooks/index.md)

-   ⚠️ **Incertitudes**
    ---
    Ce qui n'a pas pu être vérifié, et où regarder en premier.

    [➡️ Lire la liste](incertitudes.md)

</div>

---

## Démarrage rapide

```bash
uv sync
cp .env.example .env    # renseigner KILI_API_KEY et KILI_API_ENDPOINT
uv run python scripts/generate_sample_data.py
uv run python examples/01_text_classification.py --create
```

[Commencer](readme.md){ .md-button .md-button--primary }
