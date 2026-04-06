"""
Backend E2E RAG chat integration tests — real MongoDB via Testcontainers.

Feature: testing-coverage
Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""
from __future__ import annotations

import uuid

import httpx
import hypothesis
import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, ASGITransport
from hypothesis import given, settings
from hypothesis import strategies as st
from motor.motor_asyncio import AsyncIOMotorDatabase

# ---------------------------------------------------------------------------
# LLM stub constants
# ---------------------------------------------------------------------------

_LLM_BASE_URL = "https://api.openai.com/v1"

_STUB_CHAT_RESPONSE = {
    "choices": [{"message": {"content": "Voici une réponse médicale de test."}}]
}

_STUB_EMBEDDING_RESPONSE = {
    "data": [{"embedding": [0.0] * 1536}]
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm_endpoints(router=None):
    """Register respx stubs for both the embedding and chat/completions endpoints."""
    r = router or respx.mock
    r.post(f"{_LLM_BASE_URL}/embeddings").mock(
        return_value=httpx.Response(200, json=_STUB_EMBEDDING_RESPONSE)
    )
    r.post(f"{_LLM_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json=_STUB_CHAT_RESPONSE)
    )


def _setup_chat_service(integration_app, real_db):
    """Override the get_chat_service dependency to use the test DB and stubbed LLM."""
    from backend.services.chat_service import ChatService
    from backend.services.embedding_model import EmbeddingModel
    from backend.services.llm_router import LLMRouter
    from backend.services.index_manager import IndexManager
    from backend.services.llamaindex_pipeline import LlamaIndexPipeline
    from backend.routers.chat import get_chat_service

    # Re-use the real_db client directly
    llm_router = LLMRouter(
        primary_url=_LLM_BASE_URL,
        primary_api_key="test-key",
        fallback_url=_LLM_BASE_URL,
        fallback_api_key="test-key",
    )
    embedder = EmbeddingModel(
        base_url=_LLM_BASE_URL,
        api_key="test-key",
    )
    index_manager = IndexManager(db=real_db)
    pipeline = LlamaIndexPipeline(
        index_manager=index_manager,
        llm_router=llm_router,
        embedder=embedder,
    )
    chat_service = ChatService(db=real_db, rag_service=pipeline)

    # Override the FastAPI dependency so the router uses our test service
    integration_app.dependency_overrides[get_chat_service] = lambda: chat_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def medecin_client(integration_app):
    """Async client authenticated as the seeded medecin user."""
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert resp.status_code == 200, f"medecin login failed: {resp.text}"
        yield client


# ---------------------------------------------------------------------------
# Test 1 — Chat message returns non-empty answer and sources list
# Validates: Requirement 6.1
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_message_returns_answer_and_sources(
    integration_app,
    medecin_client: AsyncClient,
    real_db: AsyncIOMotorDatabase,
):
    _setup_chat_service(integration_app, real_db)

    with respx.mock(assert_all_mocked=True) as mock_router:
        _mock_llm_endpoints(mock_router)

        resp = await medecin_client.post(
            "/api/v1/chat/message",
            json={"message": "Quels sont les symptômes du paludisme?", "session_id": None},
        )
    assert resp.status_code == 200, f"chat message failed: {resp.text}"
    body = resp.json()

    assert isinstance(body["answer"], str) and len(body["answer"]) > 0, (
        f"Expected non-empty answer string, got: {body['answer']!r}"
    )
    assert isinstance(body["sources"], list), (
        f"Expected sources to be a list, got: {type(body['sources'])}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Multiple messages in same session: history returns all in chronological order
# Validates: Requirement 6.2
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_messages_history_chronological_order(
    integration_app,
    medecin_client: AsyncClient,
    real_db: AsyncIOMotorDatabase,
):
    _setup_chat_service(integration_app, real_db)

    session_id = str(uuid.uuid4())
    messages = [
        "Quels sont les symptômes du paludisme?",
        "Quel est le traitement recommandé?",
        "Y a-t-il des contre-indications?",
    ]

    with respx.mock(assert_all_mocked=True) as mock_router:
        _mock_llm_endpoints(mock_router)
        for msg in messages:
            resp = await medecin_client.post(
                "/api/v1/chat/message",
                json={"message": msg, "session_id": session_id},
            )
            assert resp.status_code == 200, f"chat message failed: {resp.text}"

    history_resp = await medecin_client.get(f"/api/v1/chat/history/{session_id}")
    assert history_resp.status_code == 200, f"history GET failed: {history_resp.text}"
    history = history_resp.json()

    msgs = history["messages"]
    # Each send_message call pushes 2 turns (user + assistant)
    assert len(msgs) == len(messages) * 2, (
        f"Expected {len(messages) * 2} messages, got {len(msgs)}"
    )

    # Roles must alternate: user, assistant, user, assistant, ...
    for i, msg in enumerate(msgs):
        expected_role = "user" if i % 2 == 0 else "assistant"
        assert msg["role"] == expected_role, (
            f"Expected role '{expected_role}' at index {i}, got '{msg['role']}'"
        )

    # Timestamps must be non-decreasing
    timestamps = [msg["timestamp"] for msg in msgs]
    for i in range(1, len(timestamps)):
        assert timestamps[i] >= timestamps[i - 1], (
            f"Timestamps not non-decreasing at index {i}: "
            f"{timestamps[i - 1]} > {timestamps[i]}"
        )


# ---------------------------------------------------------------------------
# Test 3 — Message and response are persisted in MongoDB
# Validates: Requirement 6.3
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_message_persisted_in_mongodb(
    integration_app,
    medecin_client: AsyncClient,
    real_db: AsyncIOMotorDatabase,
):
    _setup_chat_service(integration_app, real_db)

    session_id = str(uuid.uuid4())
    user_message = "Quels antibiotiques pour une pneumonie?"

    with respx.mock(assert_all_mocked=True) as mock_router:
        _mock_llm_endpoints(mock_router)
        resp = await medecin_client.post(
            "/api/v1/chat/message",
            json={"message": user_message, "session_id": session_id},
        )
    assert resp.status_code == 200, f"chat message failed: {resp.text}"

    # Query MongoDB directly
    doc = await real_db["chat_sessions"].find_one({"session_id": session_id})
    assert doc is not None, f"Expected session doc in MongoDB for session_id={session_id}"

    stored_messages = doc.get("messages", [])
    assert len(stored_messages) >= 2, (
        f"Expected at least 2 stored messages (user + assistant), got {len(stored_messages)}"
    )

    user_turns = [m for m in stored_messages if m["role"] == "user"]
    assert any(m["content"] == user_message for m in user_turns), (
        f"User message content not found in stored messages: {stored_messages}"
    )

    assistant_turns = [m for m in stored_messages if m["role"] == "assistant"]
    assert len(assistant_turns) >= 1, "Expected at least one assistant turn persisted"


# ---------------------------------------------------------------------------
# Test 4 — Unauthenticated chat request returns HTTP 401
# Validates: Requirement 6.4
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)
async def test_unauthenticated_chat_returns_401(integration_app):
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/chat/message",
            json={"message": "Test sans authentification", "session_id": None},
        )
        assert resp.status_code == 401, (
            f"Expected HTTP 401 for unauthenticated request, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Subtask 7.1 — Property 9: Chat history ordering
# Feature: testing-coverage, Property 9: Chat history ordering
# Validates: Requirements 6.2
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
@given(messages=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5))
@settings(max_examples=5, deadline=None, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
@respx.mock(assert_all_mocked=True)
async def test_property_chat_history_ordering(
    integration_app,
    real_db: AsyncIOMotorDatabase,
    messages: list[str],
):
    """
    Property 9: Chat history ordering
    For any sequence of N messages in the same session, GET history SHALL return
    exactly N*2 messages (N user + N assistant turns) in chronological order.

    # Feature: testing-coverage, Property 9: Chat history ordering
    Validates: Requirements 6.2
    """
    _setup_chat_service(integration_app, real_db)

    # Reset rate limiter for each Hypothesis example
    from backend.core.rate_limit import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass

    session_id = str(uuid.uuid4())

    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        login_resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "medecin@test.local", "password": "TestPassword123!"},
        )
        assert login_resp.status_code == 200, f"login failed: {login_resp.text}"

        with respx.mock(assert_all_mocked=True) as mock_router:
            _mock_llm_endpoints(mock_router)
            for msg in messages:
                resp = await client.post(
                    "/api/v1/chat/message",
                    json={"message": msg, "session_id": session_id},
                )
                assert resp.status_code == 200, f"chat message failed: {resp.text}"

        history_resp = await client.get(f"/api/v1/chat/history/{session_id}")
        assert history_resp.status_code == 200, f"history GET failed: {history_resp.text}"
        history_msgs = history_resp.json()["messages"]

        # Exactly N*2 messages (user + assistant per message)
        assert len(history_msgs) == len(messages) * 2, (
            f"Expected {len(messages) * 2} messages for {len(messages)} inputs, "
            f"got {len(history_msgs)}"
        )

        # All user turns appear before their corresponding assistant turns
        for i in range(len(messages)):
            user_idx = i * 2
            assistant_idx = i * 2 + 1
            assert history_msgs[user_idx]["role"] == "user", (
                f"Expected 'user' at index {user_idx}, got '{history_msgs[user_idx]['role']}'"
            )
            assert history_msgs[assistant_idx]["role"] == "assistant", (
                f"Expected 'assistant' at index {assistant_idx}, "
                f"got '{history_msgs[assistant_idx]['role']}'"
            )

        # Timestamps are non-decreasing
        timestamps = [m["timestamp"] for m in history_msgs]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Timestamps not non-decreasing at index {i}: "
                f"{timestamps[i - 1]} > {timestamps[i]}"
            )
