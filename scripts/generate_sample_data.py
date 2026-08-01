"""Génération de données d'exemple 100 % synthétiques.

Aucune donnée réelle n'entre dans ce dépôt. Ce script fabrique des
documents d'assurance fictifs — déclarations de sinistre, emails clients,
constats, attestations, factures de réparation, photos de dégâts — qui
servent uniquement de support d'annotation.

Le tirage est déterministe (graine fixe) : deux exécutions produisent des
fichiers identiques, ce qui permet aux exemples de référencer des
`external_id` stables et aux tests de vérifier le contenu.

Usage:
    uv run python scripts/generate_sample_data.py
"""

import json
import random
from pathlib import Path

import fitz  # pymupdf
from loguru import logger
from PIL import Image, ImageDraw

from kili_examples.config import settings
from kili_examples.logging import setup_logging
from kili_examples.paths import DATA_DIR

SAMPLES_DIR = DATA_DIR / "samples"
TEXT_DIR = SAMPLES_DIR / "text"
PDF_DIR = SAMPLES_DIR / "pdf"
IMAGE_DIR = SAMPLES_DIR / "image"

# --- Vocabulaire métier fictif -------------------------------------------

CLAIM_TEMPLATES = [
    "Le {date}, mon véhicule a été percuté à l'arrière sur le parking du "
    "centre commercial de {ville}. Dégâts sur le pare-chocs.",
    "Suite aux fortes pluies du {date}, une infiltration d'eau a endommagé "
    "le plafond du salon de mon appartement à {ville}.",
    "Le {date}, un dégât des eaux provenant de l'étage supérieur a inondé "
    "ma salle de bain à {ville}.",
    "Collision avec un autre véhicule le {date} au rond-point de {ville}. "
    "Constat amiable rempli sur place.",
    "Vol de mon véhicule stationné rue des Lilas à {ville}, constaté le "
    "{date} au matin. Plainte déposée au commissariat.",
    "Bris de glace sur le pare-brise le {date} sur la route entre {ville} "
    "et Rouen. Impact dû à un gravillon.",
]

EMAIL_TEMPLATES = [
    "Bonjour,\n\nJe suis {nom}, assuré sous le contrat {contrat}. "
    "Je souhaite connaître le montant de ma franchise pour le sinistre "
    "déclaré le {date}. Mon interlocuteur était {conseiller}.\n\n"
    "Cordialement,\n{nom}",
    "Madame, Monsieur,\n\nSuite à mon sinistre du {date}, je n'ai toujours "
    "pas reçu l'expertise. Mon contrat est le {contrat}. "
    "Merci de me rappeler au 01 23 45 67 89.\n\n{nom}",
    "Bonjour {conseiller},\n\nJe vous confirme que le garage de {ville} a "
    "réceptionné mon véhicule le {date}. Le devis s'élève à {montant} "
    "euros. Contrat {contrat}.\n\nBien à vous,\n{nom}",
]

VILLES = ["Lyon", "Nantes", "Lille", "Bordeaux", "Strasbourg", "Toulouse"]
NOMS = [
    "Camille Berger",
    "Dominique Roussel",
    "Sacha Meunier",
    "Alix Fontaine",
    "Charlie Perrot",
]
CONSEILLERS = ["M. Lambert", "Mme Girard", "le service sinistres"]
CONTRATS = ["AUTO-2024-1187", "MRH-2023-0942", "AUTO-2025-3310"]
DATES = ["12/03/2025", "04/11/2024", "27/06/2025", "19/01/2025"]


def _generate_claims(rng: random.Random, count: int) -> list[dict]:
    """Fabriquer des déclarations de sinistre fictives."""
    claims = []
    for index in range(count):
        template = CLAIM_TEMPLATES[index % len(CLAIM_TEMPLATES)]
        claims.append(
            {
                "external_id": f"declaration_{index:03d}",
                "text": template.format(
                    date=rng.choice(DATES), ville=rng.choice(VILLES)
                ),
            }
        )
    return claims


def _generate_emails(rng: random.Random, count: int) -> list[dict]:
    """Fabriquer des emails clients fictifs."""
    emails = []
    for index in range(count):
        template = EMAIL_TEMPLATES[index % len(EMAIL_TEMPLATES)]
        emails.append(
            {
                "external_id": f"email_{index:03d}",
                "text": template.format(
                    nom=rng.choice(NOMS),
                    contrat=rng.choice(CONTRATS),
                    date=rng.choice(DATES),
                    conseiller=rng.choice(CONSEILLERS),
                    ville=rng.choice(VILLES),
                    montant=rng.randrange(400, 3000, 50),
                ),
            }
        )
    return emails


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """Écrire une liste d'enregistrements au format JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("{} lignes écrites dans {}", len(rows), path)


def _write_pdf(path: Path, title: str, lines: list[str]) -> None:
    """Écrire un PDF d'une page à partir de lignes de texte.

    Le rendu est volontairement rudimentaire : ces PDF servent de support
    d'annotation (OCR, NER, boîtes), pas de modèle de document.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page()  # A4 par défaut (595 x 842 points)

    page.insert_text((72, 90), title, fontsize=16, fontname="helv")
    vertical = 130
    for line in lines:
        page.insert_text((72, vertical), line, fontsize=11, fontname="helv")
        vertical += 22

    document.save(path)
    document.close()
    logger.info("PDF écrit : {}", path)


def _generate_pdfs(rng: random.Random) -> None:
    """Fabriquer un constat, une attestation et une facture fictifs."""
    _write_pdf(
        PDF_DIR / "constat_amiable_001.pdf",
        "CONSTAT AMIABLE D'ACCIDENT AUTOMOBILE",
        [
            f"Date de l'accident : {rng.choice(DATES)}",
            f"Lieu : {rng.choice(VILLES)}",
            f"Vehicule A : assure {rng.choice(NOMS)}",
            f"Contrat : {rng.choice(CONTRATS)}",
            "Vehicule B : tiers non identifie",
            "Degats constates : pare-chocs arriere enfonce",
            "Blesses : non",
            "Montant estime des reparations : "
            f"{rng.randrange(500, 4000, 50)} EUR",
        ],
    )

    _write_pdf(
        PDF_DIR / "attestation_001.pdf",
        "ATTESTATION D'ASSURANCE",
        [
            f"Assure : {rng.choice(NOMS)}",
            f"Numero de contrat : {rng.choice(CONTRATS)}",
            "Garantie : responsabilite civile automobile",
            "Periode de validite : 01/01/2025 au 31/12/2025",
            f"Etabli a {rng.choice(VILLES)}",
        ],
    )

    _write_pdf(
        PDF_DIR / "resiliation_001.pdf",
        "COURRIER DE RESILIATION",
        [
            f"Assure : {rng.choice(NOMS)}",
            f"Numero de contrat : {rng.choice(CONTRATS)}",
            "Objet : resiliation a echeance annuelle",
            f"Date de la demande : {rng.choice(DATES)}",
            "Motif : changement d'assureur",
        ],
    )

    _write_pdf(
        PDF_DIR / "avenant_001.pdf",
        "AVENANT AU CONTRAT",
        [
            f"Assure : {rng.choice(NOMS)}",
            f"Numero de contrat : {rng.choice(CONTRATS)}",
            "Objet : ajout d'un conducteur secondaire",
            f"Date d'effet : {rng.choice(DATES)}",
        ],
    )

    _write_pdf(
        PDF_DIR / "facture_reparation_001.pdf",
        "FACTURE DE REPARATION",
        [
            "Garage Central - 14 rue des Ateliers",
            f"Ville : {rng.choice(VILLES)}",
            "Numero de facture : F-2025-0481",
            f"Date : {rng.choice(DATES)}",
            f"Immatriculation : AB-{rng.randrange(100, 999)}-CD",
            "Piece : pare-chocs arriere            420.00 EUR",
            "Main d'oeuvre : 4 heures              260.00 EUR",
            "Montant total TTC :                   816.00 EUR",
            "Franchise deduite :                   300.00 EUR",
        ],
    )


def _generate_images(rng: random.Random) -> None:
    """Fabriquer des images synthétiques annotables.

    Des formes géométriques suffisent : l'objectif est d'avoir des zones
    identifiables à entourer d'une boîte ou d'un polygone, pas de simuler
    une vraie photo de sinistre.
    """
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Deux « photos de véhicule » avec une zone de dégât contrastée.
    for index in range(2):
        image = Image.new("RGB", (640, 480), (208, 214, 222))
        draw = ImageDraw.Draw(image)
        # Carrosserie
        draw.rectangle([80, 180, 560, 360], fill=(70, 110, 180))
        # Vitres
        draw.rectangle([170, 200, 300, 260], fill=(150, 190, 220))
        # Roues
        draw.ellipse([140, 330, 220, 410], fill=(40, 40, 45))
        draw.ellipse([420, 330, 500, 410], fill=(40, 40, 45))
        # Zone endommagée : tache irrégulière sombre
        damage_x = rng.randrange(400, 470)
        draw.polygon(
            [
                (damage_x, 250),
                (damage_x + 70, 235),
                (damage_x + 90, 300),
                (damage_x + 30, 325),
            ],
            fill=(90, 60, 40),
        )
        path = IMAGE_DIR / f"vehicule_degat_{index:03d}.jpg"
        image.save(path, quality=90)
        logger.info("Image écrite : {}", path)

    # Deux « photos de dégât des eaux » : auréole sur un mur clair.
    for index in range(2):
        image = Image.new("RGB", (640, 480), (238, 234, 226))
        draw = ImageDraw.Draw(image)
        center_x = rng.randrange(240, 400)
        center_y = rng.randrange(180, 280)
        # Auréoles concentriques, du plus clair au plus foncé
        for radius, color in (
            (150, (206, 194, 170)),
            (105, (178, 160, 130)),
            (60, (150, 130, 100)),
        ):
            draw.ellipse(
                [
                    center_x - radius,
                    center_y - int(radius * 0.75),
                    center_x + radius,
                    center_y + int(radius * 0.75),
                ],
                fill=color,
            )
        path = IMAGE_DIR / f"degat_des_eaux_{index:03d}.jpg"
        image.save(path, quality=90)
        logger.info("Image écrite : {}", path)


def generate_sample_data() -> None:
    """Générer l'ensemble des fichiers d'exemple dans `data/samples/`.

    L'opération est idempotente : les fichiers existants sont écrasés par
    un contenu identique, la graine étant fixe.
    """
    rng = random.Random(settings.random_seed)

    _write_jsonl(TEXT_DIR / "declarations.jsonl", _generate_claims(rng, 12))
    _write_jsonl(TEXT_DIR / "emails.jsonl", _generate_emails(rng, 8))
    _generate_pdfs(rng)
    _generate_images(rng)

    logger.info("Données d'exemple générées dans {}", SAMPLES_DIR)


if __name__ == "__main__":
    setup_logging()
    generate_sample_data()
