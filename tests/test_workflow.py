"""Tests de la logique de pilotage (exemples 11 et 12).

Ce module ne contient que des fonctions pures : aucun réseau, aucun
double de client Kili n'est nécessaire.
"""

from kili_examples.workflow import (
    BRANCH_AUTO,
    BRANCH_HABITATION,
    PRIORITY_DELAI_LEGAL,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    build_claim_metadata,
    claim_branch,
    claim_priority,
    first_object_mid,
    merge_metadata,
    round_robin_assignment,
    summarize_issues,
)

# --- Branche et priorité --------------------------------------------------


def test_une_infiltration_est_un_sinistre_habitation():
    text = (
        "Suite aux fortes pluies, une infiltration d'eau a endommagé le "
        "plafond du salon de mon appartement."
    )
    assert claim_branch(text) == BRANCH_HABITATION


def test_une_collision_est_un_sinistre_auto():
    text = "Collision avec un autre véhicule au rond-point de Rouen."
    assert claim_branch(text) == BRANCH_AUTO


def test_le_degat_des_eaux_passe_en_tete_de_file():
    text = "Un dégât des eaux provenant de l'étage a inondé ma salle de bain."
    assert claim_priority(text) == PRIORITY_URGENT


def test_le_vol_ouvre_un_delai_legal():
    text = "Vol de mon véhicule stationné rue des Lilas."
    assert claim_priority(text) == PRIORITY_DELAI_LEGAL


def test_un_bris_de_glace_suit_l_ordre_d_arrivee():
    text = "Bris de glace sur le pare-brise, impact dû à un gravillon."
    assert claim_priority(text) == PRIORITY_NORMAL


# --- Métadonnées ----------------------------------------------------------


def test_la_metadonnee_porte_la_cle_reservee_text():
    metadata = build_claim_metadata(
        {"external_id": "declaration_000", "text": "Collision au parking."}
    )
    assert metadata["text"] == "Collision au parking."
    assert metadata["branche"] == BRANCH_AUTO
    assert metadata["priorite_calculee"] == PRIORITY_NORMAL


def test_un_texte_long_est_tronque_dans_la_metadonnee():
    metadata = build_claim_metadata(
        {"external_id": "declaration_001", "text": "a" * 500}
    )
    assert metadata["text"].endswith("…")
    assert len(metadata["text"]) == 121


def test_la_fusion_conserve_les_cles_existantes():
    merged = merge_metadata(
        {"branche": "AUTO", "text": "extrait"},
        {"numero_contrat": "AUTO-2025-0001"},
    )
    assert merged == {
        "branche": "AUTO",
        "text": "extrait",
        "numero_contrat": "AUTO-2025-0001",
    }


def test_la_fusion_accepte_un_asset_sans_metadonnee():
    assert merge_metadata(None, {"a": 1}) == {"a": 1}


def test_la_fusion_ne_modifie_pas_l_entree():
    existing = {"branche": "AUTO"}
    merge_metadata(existing, {"branche": "HABITATION"})
    assert existing == {"branche": "AUTO"}


# --- Assignation ----------------------------------------------------------


def test_la_repartition_tourne_sur_les_annotateurs():
    assignment = round_robin_assignment(
        ["a", "b", "c", "d", "e"], ["marie", "paul"]
    )
    assert assignment == [
        ["marie"],
        ["paul"],
        ["marie"],
        ["paul"],
        ["marie"],
    ]


def test_sans_annotateur_aucun_asset_n_est_assigne():
    # Une liste vide par asset est ce que Kili attend pour « personne » :
    # c'est aussi la façon de remettre un asset dans le pot commun.
    assert round_robin_assignment(["a", "b"], []) == [[], []]


# --- Issues ---------------------------------------------------------------


def test_le_mid_du_premier_objet_est_retrouve():
    json_response = {
        "ZONE_ENDOMMAGEE": {
            "annotations": [
                {"mid": "20240101", "categories": [{"name": "PARE_CHOCS"}]},
                {"mid": "20240102", "categories": [{"name": "PORTIERE"}]},
            ]
        }
    }
    assert first_object_mid(json_response) == "20240101"


def test_un_label_de_classification_n_a_pas_de_mid():
    json_response = {
        "TYPE_SINISTRE": {"categories": [{"name": "VOL", "confidence": 90}]}
    }
    assert first_object_mid(json_response) is None


def test_le_resume_separe_issues_et_questions():
    report = summarize_issues(
        [
            {"id": "1", "type": "ISSUE", "status": "OPEN", "assetId": "a1"},
            {"id": "2", "type": "ISSUE", "status": "SOLVED", "assetId": "a2"},
            {"id": "3", "type": "QUESTION", "status": "OPEN", "assetId": "a1"},
        ]
    )
    assert report["total"] == 3
    assert report["issues"] == {"OPEN": 1, "SOLVED": 1}
    assert report["questions"] == {"OPEN": 1}
    # a1 porte deux éléments ouverts mais n'apparaît qu'une fois ; a2 est
    # résolu, il ne bloque plus personne.
    assert report["assets_a_traiter"] == ["a1"]


def test_le_resume_d_un_projet_sans_signalement():
    assert summarize_issues([]) == {
        "total": 0,
        "issues": {},
        "questions": {},
        "assets_a_traiter": [],
    }
