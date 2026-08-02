"""Tests de la boucle d'amélioration du LLM-as-judge (exemple 10).

Logique pure : aucun appel réseau, aucun client Kili nécessaire.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from kili_examples.rag_review import (
    build_enriched_answer_bank,
    build_judge_prompt_context,
    extract_business_verdict,
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


def make_conversation(question_id, verdict, prediction="prédiction test"):
    """Fabriquer une conversation exportée, éventuellement arbitrée."""
    conversation = {
        "externalId": question_id,
        "metadata": {"question_id": question_id, "prediction": prediction},
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
    if verdict is not None:
        conversation["label"] = {
            "round": {"VERDICT_METIER": {"0": {"categories": [verdict]}}}
        }
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


# --- Lecture du verdict ---------------------------------------------------


def test_extract_verdict_reads_the_round_level():
    conversation = make_conversation("q-1", "ACCEPTABLE")
    assert extract_business_verdict(conversation) == "ACCEPTABLE"


def test_extract_verdict_returns_none_when_not_reviewed():
    conversation = make_conversation("q-1", verdict=None)
    assert extract_business_verdict(conversation) is None


def test_extract_verdict_tolerates_dict_categories():
    """L'export pourrait renvoyer la forme `[{"name": ...}]`."""
    conversation = {
        "label": {
            "round": {
                "VERDICT_METIER": {
                    "0": {"categories": [{"name": "ACCEPTABLE"}]}
                }
            }
        }
    }
    assert extract_business_verdict(conversation) == "ACCEPTABLE"


# --- Enrichissement de la banque ------------------------------------------


def test_acceptable_prediction_becomes_a_secondary_answer():
    conversations = [make_conversation("q-1", "ACCEPTABLE", "variante A")]

    enriched, promoted = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert promoted == ["q-1"]
    entry = next(e for e in enriched if e["question_id"] == "q-1")
    assert entry["secondary_answers"] == ["variante A"]


def test_non_acceptable_prediction_is_ignored():
    conversations = [make_conversation("q-1", "NON_ACCEPTABLE", "mauvaise")]

    enriched, promoted = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )

    assert promoted == []
    entry = next(e for e in enriched if e["question_id"] == "q-1")
    assert entry["secondary_answers"] == []


def test_unreviewed_conversation_is_ignored():
    conversations = [make_conversation("q-1", verdict=None)]
    _, promoted = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert promoted == []


def test_promotion_is_idempotent():
    """Rejouer l'export ne doit pas dupliquer une variante.

    La boucle tourne à chaque run : sans cette garantie, la banque
    enflerait de doublons.
    """
    conversations = [make_conversation("q-1", "ACCEPTABLE", "variante A")]

    once, _ = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    twice, promoted = build_enriched_answer_bank(
        answer_bank=once, conversations=conversations
    )

    assert promoted == []
    assert twice == once


def test_prediction_identical_to_reference_is_not_added():
    conversations = [make_conversation("q-1", "ACCEPTABLE", "réponse 1")]
    _, promoted = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert promoted == []


def test_original_bank_is_not_mutated():
    conversations = [make_conversation("q-1", "ACCEPTABLE", "variante A")]
    build_enriched_answer_bank(answer_bank=BANK, conversations=conversations)
    assert BANK[0]["secondary_answers"] == []


def test_unknown_question_id_is_skipped():
    conversations = [make_conversation("q-inconnue", "ACCEPTABLE")]
    _, promoted = build_enriched_answer_bank(
        answer_bank=BANK, conversations=conversations
    )
    assert promoted == []


def test_prediction_falls_back_to_last_assistant_item():
    """Sans métadonnée, on relit le dernier ASSISTANT."""
    conversation = make_conversation("q-1", "ACCEPTABLE", "variante B")
    del conversation["metadata"]["prediction"]

    _, promoted = build_enriched_answer_bank(
        answer_bank=BANK, conversations=[conversation]
    )
    assert promoted == ["q-1"]


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


# --- Intégration avec le script d'exemple ---------------------------------


def test_only_judge_rejections_are_sent_to_review(example):
    """Le métier ne doit relire que les cas rejetés par le juge."""
    cases = example.load_review_cases()
    assert cases, "aucun cas à arbitrer"
    assert all(case["judge_verdict"] == "NON_CONFORME" for case in cases)


def test_conversation_has_exactly_two_assistant_items(example):
    """Kili impose deux ASSISTANT par tour en LLM_STATIC."""
    for case in example.load_review_cases():
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
    for case in example.load_review_cases():
        for item in example.build_conversation(case)["chatItems"]:
            assert item["externalId"] not in seen
            seen.add(item["externalId"])


def test_assistant_items_declare_a_model_name(example):
    """`modelName` est requis pour les ASSISTANT."""
    for case in example.load_review_cases():
        for item in example.build_conversation(case)["chatItems"]:
            if item["role"] == "ASSISTANT":
                assert item.get("modelName")


def test_interface_jobs_all_declare_a_level(example):
    """Un job LLM sans `level` ne s'afficherait pas au bon endroit."""
    jobs = example.build_interface()["jobs"]
    assert jobs
    for job in jobs.values():
        assert job["level"] in {"completion", "round", "conversation"}


def test_prefilled_verdict_mirrors_the_judge(example):
    """La pré-annotation reprend le verdict du juge, à corriger."""
    case = example.load_review_cases()[0]
    label = example.predict(case)

    verdict = label["round"]["VERDICT_METIER"]["0"]["categories"]
    assert verdict == ["NON_ACCEPTABLE"]


def test_prefilled_verdict_uses_a_declared_category(example):
    """Le verdict pré-rempli doit exister dans l'ontologie."""
    jobs = example.build_interface()["jobs"]
    declared = set(jobs["VERDICT_METIER"]["content"]["categories"])

    for case in example.load_review_cases():
        label = example.predict(case)
        for name in label["round"]["VERDICT_METIER"]["0"]["categories"]:
            assert name in declared


def test_system_prompt_carries_the_judge_reason(example):
    """L'annotateur doit voir pourquoi le cas lui est soumis."""
    case = example.load_review_cases()[0]
    chat_items = example.build_conversation(case)["chatItems"]

    system = next(i for i in chat_items if i["role"] == "SYSTEM")
    assert case["judge_reason"] in system["content"]


def test_known_variants_are_shown_to_the_reviewer(example):
    """Les variantes déjà acceptées sont rappelées au relecteur."""
    case = dict(example.load_review_cases()[0])
    case["secondary_answers"] = ["une variante déjà validée"]

    chat_items = example.build_conversation(case)["chatItems"]
    system = next(i for i in chat_items if i["role"] == "SYSTEM")
    assert "une variante déjà validée" in system["content"]
