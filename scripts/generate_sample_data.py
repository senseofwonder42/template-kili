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
RAG_DIR = SAMPLES_DIR / "rag"

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

# --- Jeu d'évaluation RAG (exemple 10) -----------------------------------
#
# Écrit à la main plutôt que tiré au sort : l'intérêt pédagogique tient
# précisément à la *nature* du désaccord entre le juge LLM et le métier.
#
# `judge_verdict` simule la sortie du LLM-as-judge du run précédent.
# Les cas intéressants sont ceux marqués NON_CONFORME : certains sont de
# vraies erreurs, d'autres de la sévérité excessive (le juge reproche
# l'absence d'un élément qui n'est en fait qu'optionnel).
RAG_EVALUATION_CASES = [
    {
        "question_id": "q-0001",
        "question": (
            "Quel est le délai pour déclarer un sinistre automobile ?"
        ),
        "answer": (
            "Vous disposez de 5 jours ouvrés à compter de la date du "
            "sinistre pour le déclarer à votre assureur. Ce délai est "
            "ramené à 2 jours ouvrés en cas de vol du véhicule."
        ),
        "prediction": (
            "Le délai de déclaration est de 5 jours ouvrés après le sinistre."
        ),
        # Le juge sanctionne l'absence du cas « vol », que le métier
        # considère comme une précision optionnelle ici.
        "judge_verdict": "NON_CONFORME",
        "judge_reason": (
            "La prédiction omet le délai spécifique de 2 jours en cas de "
            "vol mentionné dans la réponse de référence."
        ),
    },
    {
        "question_id": "q-0002",
        "question": "Comment fonctionne le bonus-malus ?",
        "answer": (
            "Le coefficient de réduction-majoration démarre à 1,00. Il "
            "diminue de 5 % par année sans sinistre responsable, jusqu'à "
            "un plancher de 0,50. Il augmente de 25 % par sinistre "
            "responsable."
        ),
        "prediction": (
            "Le bonus-malus part de 1,00. Chaque année sans sinistre "
            "responsable le fait baisser de 5 %, avec un minimum de "
            "0,50. À l'inverse, un sinistre responsable le majore de "
            "25 %."
        ),
        # Reformulation fidèle : le juge l'accepte.
        "judge_verdict": "CONFORME",
        "judge_reason": "Tous les éléments chiffrés sont présents.",
    },
    {
        "question_id": "q-0003",
        "question": "La franchise s'applique-t-elle en cas de bris de glace ?",
        "answer": (
            "Oui, une franchise spécifique bris de glace de 90 euros "
            "s'applique. Elle est supprimée si la réparation est "
            "effectuée dans le réseau de garages partenaires."
        ),
        "prediction": (
            "Non, le bris de glace n'est jamais soumis à franchise."
        ),
        # Vraie erreur : le juge a raison de rejeter.
        "judge_verdict": "NON_CONFORME",
        "judge_reason": (
            "La prédiction contredit la réponse de référence sur "
            "l'existence même de la franchise."
        ),
    },
    {
        "question_id": "q-0004",
        "question": (
            "Que couvre la garantie responsabilité civile automobile ?"
        ),
        "answer": (
            "La responsabilité civile couvre les dommages corporels et "
            "matériels causés aux tiers. Elle est obligatoire. Elle ne "
            "couvre ni les dommages au véhicule de l'assuré ni ses "
            "propres blessures."
        ),
        "prediction": (
            "Elle prend en charge les dommages corporels et matériels "
            "que vous causez à autrui. C'est la garantie minimale "
            "légalement obligatoire."
        ),
        # Le juge reproche l'absence des exclusions, que le métier juge
        # non essentielles pour répondre à la question posée.
        "judge_verdict": "NON_CONFORME",
        "judge_reason": (
            "La prédiction ne mentionne pas les exclusions présentes "
            "dans la réponse de référence."
        ),
    },
    {
        "question_id": "q-0005",
        "question": "Puis-je prêter mon véhicule à un tiers ?",
        "answer": (
            "Le prêt de volant est autorisé sauf clause contraire au "
            "contrat. En cas de sinistre responsable, une franchise "
            "majorée de 150 euros peut s'appliquer si le conducteur a "
            "moins de 3 ans de permis."
        ),
        "prediction": (
            "Oui, le prêt de volant est possible sauf mention contraire "
            "dans votre contrat. Attention : si le conducteur a moins de "
            "3 ans de permis, une franchise majorée de 150 euros "
            "s'applique en cas de sinistre responsable."
        ),
        "judge_verdict": "CONFORME",
        "judge_reason": "Reformulation complète et fidèle.",
    },
    {
        "question_id": "q-0006",
        "question": "Comment résilier mon contrat auto ?",
        "answer": (
            "Depuis la loi Hamon, vous pouvez résilier à tout moment "
            "après la première année d'engagement, sans frais ni "
            "justificatif. La résiliation prend effet un mois après "
            "réception de la demande par l'assureur."
        ),
        "prediction": (
            "Après un an de contrat, la loi Hamon vous permet de "
            "résilier quand vous le souhaitez, sans frais. L'effet est "
            "au bout d'un mois."
        ),
        # Le juge sanctionne « sans justificatif », omis par la
        # prédiction — sévérité discutable.
        "judge_verdict": "NON_CONFORME",
        "judge_reason": (
            "L'absence de justificatif n'est pas explicitement mentionnée."
        ),
    },
    {
        "question_id": "q-0007",
        "question": "Le vol d'autoradio est-il couvert ?",
        "answer": (
            "Le vol d'autoradio d'origine est couvert par la garantie "
            "vol, sous réserve d'effraction constatée. Les autoradios "
            "installés après l'achat doivent avoir été déclarés."
        ),
        "prediction": (
            "Oui, tout autoradio est couvert sans condition par la "
            "garantie vol."
        ),
        # Vraie erreur : suppression des conditions.
        "judge_verdict": "NON_CONFORME",
        "judge_reason": (
            "La prédiction supprime les conditions d'effraction et de "
            "déclaration."
        ),
    },
    {
        "question_id": "q-0008",
        "question": "Quelle est la durée de validité du constat amiable ?",
        "answer": (
            "Le constat amiable doit être transmis à l'assureur dans un "
            "délai de 5 jours ouvrés. Une fois signé par les deux "
            "parties, il ne peut plus être modifié."
        ),
        "prediction": (
            "Il faut l'envoyer à l'assureur sous 5 jours ouvrés. Après "
            "signature des deux conducteurs, aucune modification n'est "
            "possible."
        ),
        "judge_verdict": "CONFORME",
        "judge_reason": "Équivalent sémantique.",
    },
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


def _generate_rag_files() -> None:
    """Écrire la banque de réponses et le run du LLM-as-judge.

    Deux fichiers, qui reflètent la séparation des responsabilités du
    cas d'usage :

    - `answer_bank.jsonl` : la vérité terrain validée par les métiers.
      C'est le fichier que la boucle enrichit avec des
      `secondary_answers`. Il démarre sans aucune variante.
    - `judge_run.jsonl` : la sortie d'un run d'évaluation — pour chaque
      question, la prédiction du RAG et le verdict du juge.
    """
    answer_bank = [
        {
            "question_id": case["question_id"],
            "question": case["question"],
            "answer": case["answer"],
            # Aucune variante au départ : c'est la boucle métier qui
            # remplira cette liste, run après run.
            "secondary_answers": [],
        }
        for case in RAG_EVALUATION_CASES
    ]
    _write_jsonl(RAG_DIR / "answer_bank.jsonl", answer_bank)

    judge_run = [
        {
            "question_id": case["question_id"],
            "prediction": case["prediction"],
            "judge_verdict": case["judge_verdict"],
            "judge_reason": case["judge_reason"],
            "model_name": "rag-assurance-auto-v2",
        }
        for case in RAG_EVALUATION_CASES
    ]
    _write_jsonl(RAG_DIR / "judge_run.jsonl", judge_run)


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
    _generate_rag_files()

    logger.info("Données d'exemple générées dans {}", SAMPLES_DIR)


if __name__ == "__main__":
    setup_logging()
    generate_sample_data()
