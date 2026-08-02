"""Tests de la révision métier du jeu d'évaluation RAG (exemple 10).

Logique pure : aucun appel réseau, aucun client Kili nécessaire.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from kili_examples.rag_review import (
    NO,
    PREDICTION_CORRECT_JOB,
    REFERENCE_CORRECT_JOB,
    REFERENCE_FIX_JOB,
    SECONDARY_ANSWER_JOB,
    YES,
    build_enriched_answer_bank,
    build_judge_prompt_context,
    extract_category,
    extract_text,
    is_reviewed,
    write_answer_bank,
)

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "10_llm_judge_ab_testing.py"
)


@pytest.fixture(scope="module")
def example() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ex10", EXAMPLE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_conversation(
    question_id,
    *,
    reference_ok=None,
    prediction_ok=None,
    reference_fix=None,
    secondary=None,
    prediction="prédiction test",
    judge_verdict="NON_CONFORME",
):
    """Fabriquer une conversation exportée, éventuellement arbitrée.

    Chaque job non renseigné est simplement absent du label, comme le
    ferait un export sur un cas partiellement traité.
    """
    conversation = {
        "externalId": question_id,
        "metadata": {
            "question_id": question_id,
            "prediction": prediction,
            "judge_verdict": judge_verdict,
        },
        "chatItems": [
            {"role": "USER", "content": "question ?"},
            {
                "role": "ASSISTANT",
                "content": "réponse de référence",
                "modelName": "reference-metier",
            },
            {
                "role": "ASSISTANT",
                "content": prediction,
                "modelName": "rag-v2",
            },
        ],
    }

    round_label = {}
    if reference_ok is not None:
        round_label[REFERENCE_CORRECT_JOB] = {
            "0": {"categories": [YES if reference_ok else NO]}
        }
    if prediction_ok is not None:
        round_label[PREDICTION_CORRECT_JOB] = {
            "0": {"categories": [YES if prediction_ok else NO]}
        }
    if reference_fix is not None:
        round_label[REFERENCE_FIX_JOB] = {"0": {"text": reference_fix}}
    if secondary is not None:
        round_label[SECONDARY_ANSWER_JOB] = {"0": {"text": secondary}}

    if round_label:
        conversation["label"] = {"round": round_label}
    return conversation


BANK = [
    {
        "question_id": "q-1",
        "question": "q1 ?",
        "answer": "réponse 1",
        "secondary_answers": [],
    },
    {
        "question_id": "q-2",
        "question": "q2 ?",
        "answer": "réponse 2",
        "secondary_answers": [],
    },
]


def entry_of(bank, question_id):
    return next(e for e in bank if e["question_id"] == question_id)


# --- Lecture des labels ---------------------------------------------------


def test_extract_category_reads_the_round_level():
    conversation = make_conversation("q-1", prediction_ok=True)
    assert extract_category(conversation, PREDICTION_CORRECT_JOB) == YES


def test_extract_category_returns_none_when_not_reviewed():
    conversation = make_conversation("q-1")
    assert extract_category(conversation, PREDICTION_CORRECT_JOB) is None


def test_extract_category_tolerates_dict_categories():
    """L'export pourrait renvoyer la forme `[{"name": ...}]`."""
    conversation = {
        "label": {
            "round": {
                PREDICTION_CORRECT_JOB: {"0": {"categories": [{"name": YES}]}}
            }
        }
    }
    assert extract_category(conversation, PREDICTION_CORRECT_JOB) == YES


def test_extract_text_returns_the_saisie():
    conversation = make_conversation("q-1", secondary="une variante")
    assert extract_text(conversation, SECONDARY_ANSWER_JOB) == "une variante"


def test_extract_text_treats_blank_input_as_empty():
    """Un champ ouvert puis laissé vide ne doit rien produire."""
    conversation = make_conversation("q-1", secondary="   \n  ")
    assert extract_text(conversation, SECONDARY_ANSWER_JOB) is None


def test_extract_text_strips_surrounding_whitespace():
    conversation = make_conversation("q-1", secondary="  variante  ")
    assert extract_text(conversation, SECONDARY_ANSWER_JOB) == "variante"


def test_is_reviewed_ignores_the_prefilled_reference_job():
    """Seule `PREDICTION_CORRECTE` prouve qu'un humain est passé."""
    prefilled_only = make_conversation("q-1", reference_ok=True)
    assert not is_reviewed(prefilled_only)

    reviewed = make_conversation("q-1", reference_ok=True, prediction_ok=False)
    assert is_reviewed(reviewed)


# --- Jugement de la prédiction --------------------------------------------


def test_correct_prediction_becomes_a_secondary_answer():
    conversations = [
        make_conversation("q-1", prediction_ok=True, prediction="variante A")
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert report["predictions_promues"] == ["q-1"]
    assert entry_of(enriched, "q-1")["secondary_answers"] == ["variante A"]


def test_incorrect_prediction_is_ignored():
    conversations = [
        make_conversation("q-1", prediction_ok=False, prediction="mauvaise")
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert report["predictions_promues"] == []
    assert entry_of(enriched, "q-1")["secondary_answers"] == []


def test_unreviewed_conversation_is_ignored():
    conversations = [make_conversation("q-1")]
    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert report["predictions_promues"] == []
    assert report["desaccord_juge_metier"]["cas_arbitres"] == 0


def test_promotion_is_idempotent():
    """Rejouer l'export ne doit pas dupliquer une variante.

    La boucle tourne à chaque run : sans cette garantie, la banque
    enflerait de doublons.
    """
    conversations = [
        make_conversation("q-1", prediction_ok=True, prediction="variante A")
    ]

    once, _ = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    twice, report = build_enriched_answer_bank(
        answer_bank=once, conversations=conversations
    )

    assert report["predictions_promues"] == []
    assert twice == once


def test_prediction_identical_to_reference_is_not_added():
    conversations = [
        make_conversation("q-1", prediction_ok=True, prediction="réponse 1")
    ]
    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert report["predictions_promues"] == []


def test_prediction_falls_back_to_last_assistant_item():
    """Sans métadonnée, on relit le dernier ASSISTANT."""
    conversation = make_conversation(
        "q-1", prediction_ok=True, prediction="variante B"
    )
    del conversation["metadata"]["prediction"]

    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=[conversation]
    )
    assert report["predictions_promues"] == ["q-1"]


# --- Réécriture manuelle --------------------------------------------------


def test_manual_rewrite_becomes_a_secondary_answer():
    conversations = [
        make_conversation(
            "q-1", prediction_ok=True, secondary="version corrigée"
        )
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert report["reecritures_manuelles"] == ["q-1"]
    assert entry_of(enriched, "q-1")["secondary_answers"] == [
        "version corrigée"
    ]


def test_rewrite_wins_over_the_raw_prediction():
    """La saisie du métier prime : la prédiction brute n'est pas ajoutée."""
    conversations = [
        make_conversation(
            "q-1",
            prediction_ok=True,
            prediction="prédiction brute",
            secondary="version corrigée",
        )
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert report["predictions_promues"] == []
    assert entry_of(enriched, "q-1")["secondary_answers"] == [
        "version corrigée"
    ]


def test_rewrite_is_kept_even_when_prediction_is_incorrect():
    """Le cas « presque bonne, je l'ai corrigée » — le coeur du besoin."""
    conversations = [
        make_conversation(
            "q-1",
            prediction_ok=False,
            prediction="il manque une info",
            secondary="la version complète",
        )
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert report["reecritures_manuelles"] == ["q-1"]
    assert entry_of(enriched, "q-1")["secondary_answers"] == [
        "la version complète"
    ]


def test_no_secondary_answer_is_required():
    """Un cas peut être arbitré sans produire la moindre variante."""
    conversations = [
        make_conversation("q-1", reference_ok=True, prediction_ok=False)
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert entry_of(enriched, "q-1")["secondary_answers"] == []
    assert report["reecritures_manuelles"] == []
    assert report["predictions_promues"] == []


def test_blank_rewrite_falls_back_to_the_prediction():
    conversations = [
        make_conversation(
            "q-1",
            prediction_ok=True,
            prediction="variante A",
            secondary="   ",
        )
    ]

    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert report["predictions_promues"] == ["q-1"]


# --- Correction de la référence -------------------------------------------


def test_faulty_reference_is_replaced():
    conversations = [
        make_conversation(
            "q-1",
            reference_ok=False,
            prediction_ok=False,
            reference_fix="la vraie réponse",
        )
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert entry_of(enriched, "q-1")["answer"] == "la vraie réponse"
    assert report["references_corrigees"] == [
        {
            "question_id": "q-1",
            "ancienne_reponse": "réponse 1",
            "nouvelle_reponse": "la vraie réponse",
        }
    ]


def test_faulty_reference_without_a_fix_is_not_overwritten():
    """Mieux vaut une référence imparfaite qu'une référence vide."""
    conversations = [
        make_conversation("q-1", reference_ok=False, prediction_ok=False)
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert entry_of(enriched, "q-1")["answer"] == "réponse 1"
    assert report["references_fautives_sans_correction"] == ["q-1"]


def test_correct_reference_is_never_replaced():
    """Un texte saisi par erreur ne doit pas écraser une bonne référence."""
    conversations = [
        make_conversation(
            "q-1",
            reference_ok=True,
            prediction_ok=False,
            reference_fix="saisie parasite",
        )
    ]

    enriched, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert entry_of(enriched, "q-1")["answer"] == "réponse 1"
    assert report["references_corrigees"] == []


def test_reference_fix_and_secondary_answer_combine():
    conversations = [
        make_conversation(
            "q-1",
            reference_ok=False,
            prediction_ok=False,
            reference_fix="la vraie réponse",
            secondary="une autre formulation",
        )
    ]

    enriched, _ = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    entry = entry_of(enriched, "q-1")
    assert entry["answer"] == "la vraie réponse"
    assert entry["secondary_answers"] == ["une autre formulation"]


def test_secondary_answer_equal_to_the_fixed_reference_is_dropped():
    """La correction et la variante peuvent converger : pas de doublon."""
    conversations = [
        make_conversation(
            "q-1",
            reference_ok=False,
            prediction_ok=True,
            reference_fix="texte unique",
            secondary="texte unique",
        )
    ]

    enriched, _ = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    entry = entry_of(enriched, "q-1")
    assert entry["answer"] == "texte unique"
    assert entry["secondary_answers"] == []


# --- Schéma et intégrité de la banque -------------------------------------


def test_output_schema_is_identical_to_the_input_schema():
    """Le juge doit pouvoir relire le fichier sans adaptation."""
    conversations = [
        make_conversation(
            "q-1",
            reference_ok=False,
            prediction_ok=True,
            reference_fix="corrigée",
            secondary="variante",
        )
    ]

    enriched, _ = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    for entry in enriched:
        assert set(entry) == set(BANK[0])


def test_questions_out_of_scope_are_carried_over_unchanged():
    """Les questions non soumises à revue restent telles quelles."""
    conversations = [make_conversation("q-1", prediction_ok=True)]

    enriched, _ = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert entry_of(enriched, "q-2") == BANK[1]


def test_original_bank_is_not_mutated():
    conversations = [
        make_conversation(
            "q-1",
            reference_ok=False,
            prediction_ok=True,
            reference_fix="corrigée",
        )
    ]
    build_enriched_answer_bank(answer_bank=BANK, conversations=conversations)

    assert BANK[0]["secondary_answers"] == []
    assert BANK[0]["answer"] == "réponse 1"


def test_unknown_question_id_is_skipped():
    conversations = [make_conversation("q-inconnue", prediction_ok=True)]
    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert report["predictions_promues"] == []


# --- Rapport de révision --------------------------------------------------


def test_report_counts_judge_false_negatives():
    """Le juge a rejeté, le métier accepte : son faux négatif."""
    conversations = [
        make_conversation(
            "q-1", prediction_ok=True, judge_verdict="NON_CONFORME"
        )
    ]

    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    stats = report["desaccord_juge_metier"]
    assert stats["faux_negatifs_juge"] == 1
    assert stats["faux_positifs_juge"] == 0
    assert stats["desaccords"] == 1


def test_report_counts_judge_false_positives():
    """Le juge a validé, le métier rejette : visible en scope all/sample."""
    conversations = [
        make_conversation("q-1", prediction_ok=False, judge_verdict="CONFORME")
    ]

    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    stats = report["desaccord_juge_metier"]
    assert stats["faux_positifs_juge"] == 1
    assert stats["faux_negatifs_juge"] == 0


def test_report_counts_agreements():
    conversations = [
        make_conversation(
            "q-1", prediction_ok=False, judge_verdict="NON_CONFORME"
        ),
        make_conversation("q-2", prediction_ok=True, judge_verdict="CONFORME"),
    ]

    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    stats = report["desaccord_juge_metier"]
    assert stats["cas_arbitres"] == 2
    assert stats["accords"] == 2
    assert stats["desaccords"] == 0


def test_report_is_json_serialisable():
    conversations = [make_conversation("q-1", prediction_ok=True)]
    _, report = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert json.loads(json.dumps(report)) == report


# --- Prompt du juge -------------------------------------------------------


def test_judge_prompt_with_a_single_answer():
    entry = {"answer": "réponse unique", "secondary_answers": []}
    prompt = build_judge_prompt_context(entry)
    assert "réponse unique" in prompt
    assert "acceptables" not in prompt


def test_judge_prompt_lists_every_valid_answer():
    entry = {
        "answer": "réponse principale",
        "secondary_answers": ["variante A", "variante B"],
    }
    prompt = build_judge_prompt_context(entry)

    assert "1. réponse principale" in prompt
    assert "2. variante A" in prompt
    assert "3. variante B" in prompt


def test_write_answer_bank_roundtrip(tmp_path):
    path = tmp_path / "out" / "bank.jsonl"
    write_answer_bank(path, BANK)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == BANK


# --- Sélection des cas (périmètre) ----------------------------------------


def test_default_scope_keeps_only_judge_rejections(example):
    cases = example.load_review_cases()
    assert cases, "aucun cas à relire"
    assert all(case["judge_verdict"] == "NON_CONFORME" for case in cases)


def test_scope_all_keeps_every_question(example):
    rejected = example.load_review_cases("rejected")
    every = example.load_review_cases("all")

    assert len(every) > len(rejected)
    assert any(case["judge_verdict"] == "CONFORME" for case in every)


def test_scope_sample_adds_accepted_cases(example):
    rejected = example.load_review_cases("rejected")
    sampled = example.load_review_cases("sample", sample_size=2)

    assert len(sampled) == len(rejected) + 2
    accepted = [c for c in sampled if c["judge_verdict"] == "CONFORME"]
    assert len(accepted) == 2


def test_scope_sample_is_deterministic(example):
    """Deux exécutions doivent soumettre le même échantillon."""
    first = example.load_review_cases("sample", sample_size=2)
    second = example.load_review_cases("sample", sample_size=2)

    assert [c["question_id"] for c in first] == [
        c["question_id"] for c in second
    ]


def test_scope_sample_caps_at_the_available_cases(example):
    """Demander plus de cas qu'il n'en existe ne doit pas planter."""
    sampled = example.load_review_cases("sample", sample_size=10_000)
    every = example.load_review_cases("all")

    assert len(sampled) == len(every)


# --- Construction des conversations ---------------------------------------


def test_conversation_has_exactly_two_assistant_items(example):
    """Kili impose deux ASSISTANT par tour en LLM_STATIC."""
    for case in example.load_review_cases("all"):
        chat_items = example.build_conversation(case)["chatItems"]
        roles = [item["role"] for item in chat_items]
        assert roles.count("ASSISTANT") == 2
        assert roles.count("USER") == 1
        # L'ordre compte : la référence d'abord, la prédiction ensuite.
        assistants = [i for i in chat_items if i["role"] == "ASSISTANT"]
        assert assistants[0]["content"] == case["answer"]
        assert assistants[1]["content"] == case["prediction"]


def test_chat_item_external_ids_are_unique(example):
    """`externalId` doit être unique : Kili s'en sert pour cibler."""
    seen = set()
    for case in example.load_review_cases("all"):
        for item in example.build_conversation(case)["chatItems"]:
            assert item["externalId"] not in seen
            seen.add(item["externalId"])


def test_assistant_items_declare_a_model_name(example):
    """`modelName` est requis pour les ASSISTANT."""
    for case in example.load_review_cases("all"):
        for item in example.build_conversation(case)["chatItems"]:
            if item["role"] == "ASSISTANT":
                assert item.get("modelName")


def test_system_prompt_never_leaks_the_judge(example):
    """L'annotateur juge à l'aveugle : le juge ne doit pas s'afficher."""
    for case in example.load_review_cases("all"):
        chat_items = example.build_conversation(case)["chatItems"]
        system = next(i for i in chat_items if i["role"] == "SYSTEM")

        content = system["content"]
        assert case["judge_reason"] not in content
        assert case["judge_verdict"] not in content
        # Ni le verdict, ni une allusion à l'existence même du juge :
        # savoir qu'un modèle a déjà tranché suffirait à ancrer.
        assert "as-judge" not in content.lower()
        assert "conforme" not in content.lower()


def test_judge_verdict_stays_available_in_metadata(example):
    """Invisible à l'écran, mais nécessaire au rapport de révision."""
    case = example.load_review_cases()[0]
    metadata = example.build_conversation(case)["metadata"]

    assert metadata["judge_verdict"] == case["judge_verdict"]
    assert metadata["judge_reason"] == case["judge_reason"]


def test_scope_is_traced_in_metadata(example):
    case = example.load_review_cases()[0]
    conversation = example.build_conversation(case, "sample")
    assert conversation["metadata"]["scope"] == "sample"


def test_known_variants_are_shown_to_the_reviewer(example):
    """Les variantes déjà acceptées sont rappelées au relecteur."""
    case = dict(example.load_review_cases()[0])
    case["secondary_answers"] = ["une variante déjà validée"]

    chat_items = example.build_conversation(case)["chatItems"]
    system = next(i for i in chat_items if i["role"] == "SYSTEM")
    assert "une variante déjà validée" in system["content"]


# --- Interface et pré-annotation ------------------------------------------


def test_interface_jobs_all_declare_a_level(example):
    """Un job LLM sans `level` ne s'afficherait pas au bon endroit."""
    jobs = example.build_interface()["jobs"]
    assert jobs
    for job in jobs.values():
        assert job["level"] in {"completion", "round", "conversation"}


def test_interface_exposes_the_four_expected_jobs(example):
    jobs = example.build_interface()["jobs"]
    assert set(jobs) == {
        REFERENCE_CORRECT_JOB,
        PREDICTION_CORRECT_JOB,
        REFERENCE_FIX_JOB,
        SECONDARY_ANSWER_JOB,
    }


def test_free_text_jobs_are_optional(example):
    """Aucune `secondary_answer` n'est obligatoire."""
    jobs = example.build_interface()["jobs"]
    assert jobs[REFERENCE_FIX_JOB]["required"] == 0
    assert jobs[SECONDARY_ANSWER_JOB]["required"] == 0


def test_both_judgements_are_required(example):
    jobs = example.build_interface()["jobs"]
    assert jobs[REFERENCE_CORRECT_JOB]["required"] == 1
    assert jobs[PREDICTION_CORRECT_JOB]["required"] == 1


def test_prefill_marks_the_reference_as_correct(example):
    """La référence est présumée bonne : le métier ne corrige qu'au besoin."""
    case = example.load_review_cases()[0]
    label = example.predict(case)

    assert label["round"][REFERENCE_CORRECT_JOB]["0"]["categories"] == [YES]


def test_prediction_judgement_is_never_prefilled(example):
    """Pré-cocher l'avis du juge biaiserait l'annotateur."""
    for case in example.load_review_cases("all"):
        label = example.predict(case)
        assert PREDICTION_CORRECT_JOB not in label["round"]


def test_prefilled_category_exists_in_the_ontology(example):
    jobs = example.build_interface()["jobs"]
    declared = set(jobs[REFERENCE_CORRECT_JOB]["content"]["categories"])

    case = example.load_review_cases()[0]
    label = example.predict(case)
    for name in label["round"][REFERENCE_CORRECT_JOB]["0"]["categories"]:
        assert name in declared
