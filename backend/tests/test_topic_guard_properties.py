# Feature: assistant-qa-and-documents-redesign, Property 1: Topic Guard Classification
"""
Property tests for Topic Guard classification in ChatService.

**Validates: Requirements 2.3, 2.4, 2.5**

Property 1: Topic Guard Classification
For any user question string, the Topic Guard SHALL classify it as medical
(belonging to Accepted_Medical_Topics) or non-medical, and:
  (a) for non-medical questions, the LLM SHALL return a response prefixed
      with [TOPIC_GUARD_REFUSAL];
  (b) for medical questions, the LLM SHALL process the question normally
      and return a substantive answer.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.chat_service import ChatService
from backend.services.llm_router import StreamChunk

# ---------------------------------------------------------------------------
# Medical keyword set used by the mock to simulate Topic Guard behaviour
# ---------------------------------------------------------------------------

_MEDICAL_KEYWORDS = [
    "malaria", "dengue", "tuberculosis", "fever", "infection",
    "clinical", "nutrition", "mental health", "medical ethics",
    "tropical", "disease", "treatment", "symptoms", "diagnosis",
    "malnourished", "assessment", "protocol", "vaccine", "antibiotic",
    "paludisme", "fièvre", "traitement", "maladie",
]

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

medical_questions = st.sampled_from([
    "What are the symptoms of malaria?",
    "How to treat dengue fever?",
    "What is the protocol for tuberculosis?",
    "Nutritional needs for malnourished children",
    "Mental health assessment tools",
    "Medical ethics in clinical trials",
    "What antibiotics treat tropical infections?",
    "How is yellow fever diagnosed?",
    "What are the signs of severe malaria in children?",
    "Describe the treatment protocol for cholera",
    "What vaccines are recommended for tropical diseases?",
    "How to manage a patient with high fever and rash?",
    "What is the clinical presentation of typhoid?",
    "Nutrition guidelines for patients with tuberculosis",
    "Mental health interventions for trauma patients",
])

non_medical_questions = st.sampled_from([
    "What is the best football team?",
    "How to cook pasta?",
    "Who won the election?",
    "Best movies of 2024",
    "How to invest in stocks?",
    "What is the capital of France?",
    "Tell me a joke",
    "How to fix a flat tire?",
    "What programming language should I learn?",
    "Recommend a good restaurant",
    "How does blockchain work?",
    "What is the weather today?",
    "Who painted the Mona Lisa?",
    "How to play chess?",
    "What are the rules of basketball?",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db():
    """Return a mock Motor database whose collection accepts upserts."""
    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_collection.update_one = AsyncMock(return_value=None)
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return mock_db


def _extract_user_question(prompt: str) -> str:
    """Extract the user question from the assembled prompt.

    The prompt format is:
        <system prompt>
        User: <question>
    We extract everything after the last 'User: ' marker.
    """
    marker = "\nUser: "
    idx = prompt.rfind(marker)
    if idx == -1:
        return prompt
    return prompt[idx + len(marker):]


def _is_medical_question(prompt: str) -> bool:
    """Heuristic check: does the user question contain any medical keyword?"""
    user_q = _extract_user_question(prompt).lower()
    return any(kw in user_q for kw in _MEDICAL_KEYWORDS)


def _make_topic_guard_llm_router():
    """Create a mock LLMRouter that simulates Topic Guard behaviour.

    Inspects the assembled prompt and:
    - If the user question contains medical keywords → yields a substantive answer
    - Otherwise → yields a [TOPIC_GUARD_REFUSAL] prefixed refusal
    """
    mock_router = MagicMock()

    async def fake_generate_stream(prompt: str, context: list[dict]):
        if _is_medical_question(prompt):
            answer = "Based on current medical guidelines, here is the relevant information for your question."
            for word in answer.split():
                yield StreamChunk(token=word + " ", llm_used="mock-medical-llm")
        else:
            refusal = (
                "[TOPIC_GUARD_REFUSAL]\n"
                "I'm sorry, I can only answer questions about tropical diseases, "
                "infectious diseases, clinical medicine, nutrition, mental health, "
                "and medical ethics."
            )
            for word in refusal.split():
                yield StreamChunk(token=word + " ", llm_used="mock-medical-llm")

    mock_router.generate_stream = fake_generate_stream
    return mock_router


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _collect_done_answer(service: ChatService, user_message: str) -> str | None:
    """Run send_message_stream and return the assembled answer from the done event."""
    done_answer = None
    async for event in service.send_message_stream(
        session_id=None,
        user_message=user_message,
    ):
        if event.type == "done":
            done_answer = event.answer
    return done_answer


# ---------------------------------------------------------------------------
# Property 1a: Non-medical questions produce [TOPIC_GUARD_REFUSAL] prefix
# ---------------------------------------------------------------------------

@given(question=non_medical_questions)
@h_settings(max_examples=100)
def test_non_medical_questions_produce_topic_guard_refusal(question: str):
    """
    **Validates: Requirements 2.3, 2.4, 2.5**

    For any non-medical question, the assembled answer from the done event
    SHALL start with [TOPIC_GUARD_REFUSAL].
    """
    mock_db = _make_mock_db()
    mock_llm = _make_topic_guard_llm_router()
    service = ChatService(db=mock_db, llm_router=mock_llm)

    answer = _run(_collect_done_answer(service, question))

    assert answer is not None, "Expected a done event with an answer"
    assert answer.strip().startswith("[TOPIC_GUARD_REFUSAL]"), (
        f"Non-medical question '{question}' should produce a [TOPIC_GUARD_REFUSAL] "
        f"prefix, but got: {answer[:100]!r}"
    )


# ---------------------------------------------------------------------------
# Property 1b: Medical questions produce substantive answers (no refusal)
# ---------------------------------------------------------------------------

@given(question=medical_questions)
@h_settings(max_examples=100)
def test_medical_questions_produce_substantive_answers(question: str):
    """
    **Validates: Requirements 2.3, 2.4, 2.5**

    For any medical question, the assembled answer from the done event
    SHALL NOT start with [TOPIC_GUARD_REFUSAL] and SHALL be non-empty.
    """
    mock_db = _make_mock_db()
    mock_llm = _make_topic_guard_llm_router()
    service = ChatService(db=mock_db, llm_router=mock_llm)

    answer = _run(_collect_done_answer(service, question))

    assert answer is not None, "Expected a done event with an answer"
    assert len(answer.strip()) > 0, (
        f"Medical question '{question}' should produce a non-empty answer"
    )
    assert not answer.strip().startswith("[TOPIC_GUARD_REFUSAL]"), (
        f"Medical question '{question}' should NOT produce a [TOPIC_GUARD_REFUSAL] "
        f"prefix, but got: {answer[:100]!r}"
    )


# ---------------------------------------------------------------------------
# Property 2: Topic Guard Refusal Language Matching
# ---------------------------------------------------------------------------

# French indicators used by the language-aware mock to detect French input
_FRENCH_INDICATORS = [
    "quel", "quelle", "comment", "qui", "est-ce", "les", "des", "pour",
    "dans", "une", "avec", "sur", "fait", "sont", "cette", "peut",
    "meilleur", "cuisiner", "gagné", "élections", "temps", "jouer",
    "apprendre", "réparer", "investir", "fonctionne", "peint",
]

# Strategies for non-medical questions by language

non_medical_questions_fr = st.sampled_from([
    "Quel est le meilleur film?",
    "Comment cuisiner des pâtes?",
    "Qui a gagné les élections?",
    "Quel temps fait-il aujourd'hui?",
    "Comment investir dans les actions?",
    "Quelle est la capitale de la France?",
    "Comment jouer aux échecs?",
    "Quel est le meilleur restaurant?",
    "Comment fonctionne la blockchain?",
    "Qui a peint la Joconde?",
    "Comment réparer une crevaison?",
    "Quel langage de programmation apprendre?",
    "Quelles sont les règles du basketball?",
    "Comment faire une omelette?",
    "Quel est le meilleur jeu vidéo?",
])

non_medical_questions_en = non_medical_questions  # reuse existing English strategy


def _detect_french(text: str) -> bool:
    """Return True if the text contains French indicator words."""
    lower = text.lower()
    return any(indicator in lower for indicator in _FRENCH_INDICATORS)


def _make_language_aware_topic_guard_llm_router():
    """Create a mock LLMRouter that returns refusals in the input language.

    Detects whether the user question is in French or English and generates
    the refusal message in the matching language.
    """
    mock_router = MagicMock()

    async def fake_generate_stream(prompt: str, context: list[dict]):
        user_q = _extract_user_question(prompt)

        if _is_medical_question(prompt):
            answer = "Based on current medical guidelines, here is the relevant information."
            for word in answer.split():
                yield StreamChunk(token=word + " ", llm_used="mock-medical-llm")
        elif _detect_french(user_q):
            refusal = (
                "[TOPIC_GUARD_REFUSAL]\n"
                "Je suis désolé, je ne peux répondre qu'aux questions sur les maladies "
                "tropicales, les maladies infectieuses, la médecine clinique, la nutrition, "
                "la santé mentale et l'éthique médicale."
            )
            for word in refusal.split():
                yield StreamChunk(token=word + " ", llm_used="mock-medical-llm")
        else:
            refusal = (
                "[TOPIC_GUARD_REFUSAL]\n"
                "I'm sorry, I can only answer questions about tropical diseases, "
                "infectious diseases, clinical medicine, nutrition, mental health, "
                "and medical ethics."
            )
            for word in refusal.split():
                yield StreamChunk(token=word + " ", llm_used="mock-medical-llm")

    mock_router.generate_stream = fake_generate_stream
    return mock_router


# French refusal marker words
_FRENCH_REFUSAL_WORDS = {"désolé", "questions", "maladies", "médecine", "répondre", "tropicales"}
# English refusal marker words
_ENGLISH_REFUSAL_WORDS = {"sorry", "questions", "diseases", "medicine", "answer", "tropical"}


def _extract_refusal_body(answer: str) -> str:
    """Return the text after the [TOPIC_GUARD_REFUSAL] marker."""
    marker = "[TOPIC_GUARD_REFUSAL]\n"
    idx = answer.find(marker)
    if idx == -1:
        # Try without newline in case of whitespace differences
        marker = "[TOPIC_GUARD_REFUSAL]"
        idx = answer.find(marker)
        if idx == -1:
            return answer
        return answer[idx + len(marker):].strip()
    return answer[idx + len(marker):].strip()


@given(question=non_medical_questions_fr)
@h_settings(max_examples=100)
def test_french_non_medical_questions_get_french_refusal(question: str):
    """
    **Validates: Requirement 2.6**

    For any non-medical question in French, the refusal message after
    [TOPIC_GUARD_REFUSAL] SHALL contain French language text.
    """
    mock_db = _make_mock_db()
    mock_llm = _make_language_aware_topic_guard_llm_router()
    service = ChatService(db=mock_db, llm_router=mock_llm)

    answer = _run(_collect_done_answer(service, question))

    assert answer is not None, "Expected a done event with an answer"
    assert answer.strip().startswith("[TOPIC_GUARD_REFUSAL]"), (
        f"Non-medical question '{question}' should produce a [TOPIC_GUARD_REFUSAL] "
        f"prefix, but got: {answer[:100]!r}"
    )

    refusal_body = _extract_refusal_body(answer)
    refusal_lower = refusal_body.lower()
    matched = [w for w in _FRENCH_REFUSAL_WORDS if w in refusal_lower]
    assert len(matched) >= 2, (
        f"French question '{question}' should produce a French refusal, "
        f"but refusal text matched only {matched} French words. "
        f"Refusal body: {refusal_body[:200]!r}"
    )


@given(question=non_medical_questions_en)
@h_settings(max_examples=100)
def test_english_non_medical_questions_get_english_refusal(question: str):
    """
    **Validates: Requirement 2.6**

    For any non-medical question in English, the refusal message after
    [TOPIC_GUARD_REFUSAL] SHALL contain English language text.
    """
    mock_db = _make_mock_db()
    mock_llm = _make_language_aware_topic_guard_llm_router()
    service = ChatService(db=mock_db, llm_router=mock_llm)

    answer = _run(_collect_done_answer(service, question))

    assert answer is not None, "Expected a done event with an answer"
    assert answer.strip().startswith("[TOPIC_GUARD_REFUSAL]"), (
        f"Non-medical question '{question}' should produce a [TOPIC_GUARD_REFUSAL] "
        f"prefix, but got: {answer[:100]!r}"
    )

    refusal_body = _extract_refusal_body(answer)
    refusal_lower = refusal_body.lower()
    matched = [w for w in _ENGLISH_REFUSAL_WORDS if w in refusal_lower]
    assert len(matched) >= 2, (
        f"English question '{question}' should produce an English refusal, "
        f"but refusal text matched only {matched} English words. "
        f"Refusal body: {refusal_body[:200]!r}"
    )
