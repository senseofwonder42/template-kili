# Prompt — Repo "Kili by example"

> Prompt prêt à coller dans une session fraîche pour bootstrapper le dépôt.
> Décisions figées : scripts + notebooks, SDK Kili 2.x on-premise, données synthétiques,
> prédictions factices, 9 squelettes, scaffold copier `lean` + MkDocs + pre-commit,
> prose en français / code en anglais.

---

# Task

Bootstrap a self-contained, internal "Kili by example" repository at
/Users/afleuren/Projects/template-kili. It is a teaching repo: a set of runnable
Python skeletons showing how to drive Kili Technology (annotation platform) through
its Python SDK, one skeleton per annotation type used by an insurance company.
Today the team has no shared documentation or reference code; this repo becomes it.

Every skeleton must cover the same four-step lifecycle end to end:
(1) create the project + its annotation interface (JSON ontology),
(2) upload assets, (3) upload model predictions / pre-annotations,
(4) export the resulting annotations.

# Context

- Reference docs (READ THEM — do not write SDK calls from memory):
  - Platform docs: https://docs.kili-technology.com/docs/introduction-to-kili-technology
  - Python SDK docs + tutorials: https://python-sdk-docs.kili-technology.com/latest/tutorials/
  - SDK API reference: https://python-sdk-docs.kili-technology.com/latest/sdk/project/
  - Interface (ontology JSON) reference: search the docs for "customize the interface"
    / "json_interface" — the exact JSON schema per input type (CLASSIFICATION,
    OBJECT_DETECTION with tools bbox/polygon/semantic, NAMED_ENTITIES_RECOGNITION,
    TRANSCRIPTION, ...) is the single most valuable thing this repo documents.
- Target: Kili Python SDK 2.x against an ON-PREMISE instance. Every entry point reads
  KILI_API_KEY and KILI_API_ENDPOINT from a .env file (pydantic-settings), never hardcoded.
- CRITICAL: nothing can be executed or verified during this task. There is no Kili
  instance, no API key, and no network access to the platform from this machine. Do not
  pretend to have run anything. Correctness therefore comes from (a) following the
  official docs closely, (b) keeping code simple and explicit, (c) explicitly flagging
  every place where you are unsure.
- Project scaffolding comes from the copier template
  gh:senseofwonder42/copier-datascience-template (uv, ruff, loguru, pytest, pydantic
  settings, src/ layout, notebooks/, data/, optional MkDocs / pre-commit / DVC / Docker).
- Language convention: prose (README, MkDocs pages, docstrings, comments, notebook
  markdown cells) in FRENCH — this is internal team documentation. Code identifiers,
  file names and function names in ENGLISH. Kili ontology labels/categories in French
  business vocabulary (e.g. SINISTRE_AUTO, MONTANT_FRANCHISE, DATE_ACCIDENT) since
  human annotators read them.
- User CLAUDE.md conventions apply: uv for dependencies (`uv add`, never hand-edit
  pyproject.toml), loguru not logging, pytest not unittest, pydantic for validation,
  pymupdf (import fitz) for PDF work, Google-style docstrings, typed public signatures,
  no speculative abstractions.

# Requirements

## 1. Scaffold

Run copier non-interactively in the existing (currently non-git) directory:

    uvx copier copy --trust --defaults \
      -d project_name="Kili Examples" \
      -d project_profile=lean \
      -d use_mkdocs=true -d use_precommit=true -d use_docker=false \
      gh:senseofwonder42/copier-datascience-template .

Inspect the template's actual question names first (`copier copy --help`, or read the
template's copier.yml) and adapt the -d keys to the real variable names; do not invent
them. Profile `lean`, MkDocs on, pre-commit on (nbstripout matters here), Docker off,
DVC off. Then `git init` and `uv sync`. If copier fails (network, unknown variables),
fall back to reproducing the equivalent structure by hand and say so explicitly in your
final report.

## 2. Shared package: src/kili_examples/

Small and non-speculative — only what at least two examples need:

- `client.py` — `get_kili() -> Kili` reading api_key/api_endpoint from settings.
- `settings.py` — pydantic-settings model over .env.
- `assets.py` — batched upload helper (Kili has practical batch-size limits; document
  the chosen batch size and why), plus a helper to build external_id from a file path.
- `exports.py` — fetch labels and write them to disk as JSON, with a documented note on
  the alternative export formats Kili supports (YOLO / COCO / Pascal VOC) and when to
  use `kili.export_labels(...)` vs iterating `kili.labels(...)`.
- `interfaces.py` — typed helpers that build valid json_interface dicts per job type.
  This is the pedagogical core: keep it explicit and readable rather than clever.

Do NOT wrap the Kili SDK in a facade. Examples must show real SDK calls so readers
learn the API, not our abstraction.

## 3. The nine skeletons: examples/

One executable script per file, each with a `if __name__ == "__main__":` CLI
(argparse or typer if the template already ships it) exposing the four lifecycle steps
as flags (e.g. `--create --upload --predict --export`, default = run all).
Each script is heavily commented in French, follows the same section order, and prints
the created project_id so the reader can follow along in the UI.

      01_text_classification.py     — triage des déclarations de sinistre (multi-classe +
                                      un job de classification hiérarchique enfant)
      02_pdf_classification.py      — typage de documents contractuels (avenant, attestation,
                                      résiliation) ; montre les spécificités de l'asset PDF
      03_image_classification.py    — gravité des dégâts sur photo de véhicule
      04_object_detection.py        — détection des zones endommagées (bounding boxes)
      05_segmentation.py            — polygones/masques de zones sinistrées (dégât des eaux)
      06_pdf_ocr.py                 — transcription d'un constat amiable (TRANSCRIPTION job
                                      + zones sur PDF)
      07_vlm_text_extraction.py     — extraction de champs clés d'une facture de réparation
                                      (OCR + VLM) : montre le passage sortie modèle → JSON Kili
      08_ner_text.py                — entités dans un email client (NAMED_ENTITIES_RECOGNITION,
                                      offsets de caractères)
      09_custom_multitask_pdf.py    — interface personnalisée combinant, sur un même PDF de
                                      sinistre : classification du document + NER + OCR de
                                      champs + bounding boxes, avec au moins un job
                                      conditionnel (sous-job déclenché par une catégorie)

Example 09 is the flagship: it must demonstrate that a Kili interface is just a JSON
tree of jobs, including nested/conditional jobs, and how a single prediction payload
addresses several jobs at once.

## 4. Predictions

Each script defines:

    def predict(asset: ...) -> dict:
        """Prédiction factice — TODO: brancher votre modèle ici."""

returning a hand-written, schema-valid Kili JSON response consistent with that
example's ontology. No ML dependencies anywhere (no spaCy, torch, tesseract, YOLO).
The teaching value is the exact JSON shape per annotation type — annotate those dicts
generously with French comments explaining each key (categories, confidence,
boundingPoly, normalizedVertices, beginOffset/content for NER, mid, jobName, ...).
Show the correct SDK call for uploading them (`kili.create_predictions(...)` or the
current 2.x equivalent — verify against the docs) and explain model_name /
prediction vs. "inference" semantics.

## 5. Sample data

`scripts/generate_sample_data.py` generates fully synthetic French insurance documents
into `data/samples/` — no real data ever enters this repo:

- text: JSONL of fake claim descriptions and customer emails
- pdf: fake constat amiable / attestation / repair invoice, generated with pymupdf
  (preferred, already a house dependency) or reportlab
- image: simple synthetic "vehicle damage" and "water damage" images (Pillow) —
  crude shapes are fine, they only need to be annotatable

Deterministic (fixed seed), idempotent, and fast. `data/` contents stay gitignored.

## 6. Notebooks

Three narrative notebooks only, mirroring (not duplicating) the scripts — they import
from `src/kili_examples/` and walk through the steps with French markdown between cells:

      notebooks/01_prise_en_main.ipynb        — connexion, création d'un projet minimal,
                                                anatomie du json_interface
      notebooks/02_cycle_complet.ipynb        — le cycle complet sur l'exemple 01
      notebooks/03_interface_personnalisee.ipynb — construction pas à pas de l'interface
                                                multi-jobs de l'exemple 09

State clearly in the README that scripts are the source of truth and notebooks are the
guided tour. nbstripout via pre-commit keeps outputs out of git.

## 7. Documentation

- `README.md` (French): what this repo is, prerequisites, .env setup for the on-prem
  instance, `uv sync`, how to generate sample data, a table mapping
  "besoin métier → type d'annotation Kili → exemple à lire", and a prominent
  "⚠️ Code non testé" section with a step-by-step first-run procedure on the company
  server (start with example 01 on a throwaway project, check project_id, verify the
  interface renders in the UI, then the rest).
- MkDocs pages: one page per annotation type, focused on the json_interface and the
  prediction payload for that type — the reference the team currently lacks.
- A `docs/` (or README) section on known uncertainties: every SDK call you could not
  confirm in the official docs, listed explicitly, so the first person running this on
  the server knows where to look.

## 8. Tests

`pytest` on pure helpers only — json_interface builders and prediction-payload
builders (shape assertions), sample-data generation (files exist, deterministic).
Mock the Kili client; never attempt a network call in tests. Do not write tests that
require credentials.

# Inputs / Outputs

- Input: nothing at runtime beyond a `.env` (KILI_API_KEY, KILI_API_ENDPOINT) and
  generated sample data. Ship `.env.example`.
- Output: a working repo tree; each script, when run against a real Kili instance,
  creates a project, uploads assets and predictions, and writes exported annotations
  to `data/processed/<example>/labels.json`.
- Edge cases to handle explicitly and simply: batched uploads for large asset lists,
  idempotent re-runs (reuse an existing project via `--project-id` instead of always
  creating a new one), and a clear error if .env is missing.

# Constraints & non-goals

- Do NOT claim anything was tested, executed against Kili, or verified end to end.
  Run only what genuinely runs locally: `uv sync`, ruff, pytest, and the sample-data
  generator.
- No ML models, no heavy dependencies, no Docker, no DVC, no CI pipelines.
- No abstraction layer hiding the Kili SDK; no configurability that was not asked for.
- Do not include or fabricate any real insurance data.
- Keep each script readable top-to-bottom in one sitting; prefer repetition across
  examples over shared cleverness (this is teaching code).
- If the SDK docs contradict this prompt (renamed methods, changed signatures), follow
  the docs and note the deviation in your final report.

# Deliverable

A complete repository at /Users/afleuren/Projects/template-kili, git-initialized with
a single initial commit, containing the scaffold, `src/kili_examples/`, the nine
`examples/*.py`, `scripts/generate_sample_data.py`, three notebooks, tests, README and
MkDocs pages — all in the language convention above.

Definition of done:

1. `uv sync` succeeds.
2. `uv run ruff check .` and `uv run ruff format --check .` pass.
3. `uv run pytest` passes.
4. `uv run python scripts/generate_sample_data.py` produces the sample files.
5. Every example script imports cleanly (`uv run python -c "import ..."`) — no
   syntax/import errors — even though no Kili call can be exercised.
6. Your final report lists, explicitly: what you actually ran, what remains unverified,
   and every SDK call whose signature you could not confirm in the official docs.

---

## Hypothèses figées (modifiables avant lancement)

- Profil copier `lean`, avec MkDocs + pre-commit, sans Docker ni DVC.
- 3 notebooks seulement (pas un par exemple).
- Python 3.12 (défaut du template).
- Exemple 09 sur PDF uniquement — pas de second exemple d'interface custom sur image.
- Tests `pytest` limités aux helpers purs, client Kili mocké.
- Export des annotations en JSON, formats YOLO/COCO simplement mentionnés.
