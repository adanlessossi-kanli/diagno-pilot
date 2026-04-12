# Feature: assistant-qa-and-documents-redesign, Property 7: Document Chat Session Persistence Round-Trip
# Feature: assistant-qa-and-documents-redesign, Property 9: DocumentSource Completeness with Highlight Data
"""
Property tests for DocumentChatService.

Property 7: Document Chat Session Persistence Round-Trip
For any sequence of N user messages sent to the Document Chat within a single
session, retrieving the session history SHALL return all N user messages and
their corresponding assistant responses in chronological order, with sources
preserved.

Property 9: DocumentSource Completeness with Highlight Data
For any DocumentSource returned by the Document Chat for a PDF-sourced chunk,
the DocumentSource SHALL include non-null values for documentId, title, source,
excerpt, page, and highlight (with bbox as a 4-element array and page as an
integer).
"""
from __future__ import annotations

import copy
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from backend.models.document import DocumentSource, HighlightInfo
from backend.services.document_chat_service import DocumentChatService
from backend.services.llamaindex_pipeline import StreamEvent


# ---------------------------------------------------------------------------
# In-memory MongoDB simulation
# ---------------------------------------------------------------------------

class _DeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class _InMemoryCollection:
    """Minimal in-memory collection supporting the operations used by DocumentChatService."""

    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self._docs: list[dict[str, Any]] = [copy.deepcopy(d) for d in (docs or [])]

    async def update_one(self, filter_: dict, update: dict, upsert: bool = False):
        # Find matching doc
        matched = None
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in filter_.items()):
                matched = doc
                break

        if matched is None and upsert:
            # Create new doc from filter + $setOnInsert
            matched = dict(filter_)
            if "$setOnInsert" in update:
                matched.update(update["$setOnInsert"])
            if "messages" not in matched:
                matched["messages"] = []
            self._docs.append(matched)

        if matched is not None:
            if "$push" in update:
                for field, value in update["$push"].items():
                    if field not in matched:
                        matched[field] = []
                    if isinstance(value, dict) and "$each" in value:
                        matched[field].extend(value["$each"])
                    else:
                        matched[field].append(value)
            if "$set" in update:
                matched.update(update["$set"])

    async def find_one(self, filter_: dict, projection: dict | None = None):
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in filter_.items()):
                result = copy.deepcopy(doc)
                if projection and "_id" in projection and projection["_id"] == 0:
                    result.pop("_id", None)
                # Handle $slice projection for messages
                if projection and "messages" in projection:
                    slice_val = projection["messages"]
                    if isinstance(slice_val, dict) and "$slice" in slice_val:
                        s = slice_val["$slice"]
                        msgs = result.get("messages", [])
                        if isinstance(s, list) and len(s) == 2:
                            result["messages"] = msgs[s[0]:s[0] + s[1]]
                        elif isinstance(s, int):
                            result["messages"] = msgs[:s]
                return result
        return None

    def aggregate(self, pipeline: list):
        return _AggregationCursor(self._docs, pipeline)

    async def delete_one(self, filter_: dict):
        for i, doc in enumerate(self._docs):
            if all(doc.get(k) == v for k, v in filter_.items()):
                self._docs.pop(i)
                return _DeleteResult(1)
        return _DeleteResult(0)

    def find(self, filter_: dict, projection: dict | None = None):
        return _FindCursor(self._docs, filter_, projection)


class _AggregationCursor:
    def __init__(self, docs: list[dict], pipeline: list):
        self._docs = docs
        self._pipeline = pipeline

    async def to_list(self, length: int = 100):
        results = []
        for stage in self._pipeline:
            if "$match" in stage:
                filt = stage["$match"]
                for doc in self._docs:
                    if all(doc.get(k) == v for k, v in filt.items()):
                        results.append(doc)
            elif "$project" in stage:
                proj = stage["$project"]
                projected = []
                for doc in results:
                    p = {}
                    for key, val in proj.items():
                        if isinstance(val, dict) and "$size" in val:
                            field = val["$size"]
                            if field.startswith("$"):
                                field = field[1:]
                            p[key] = len(doc.get(field, []))
                        else:
                            p[key] = doc.get(key)
                    projected.append(p)
                results = projected
        return results[:length]


class _FindCursor:
    def __init__(self, docs: list[dict], filter_: dict, projection: dict | None):
        self._results = []
        for doc in docs:
            if all(doc.get(k) == v for k, v in filter_.items()):
                result = copy.deepcopy(doc)
                if projection and "_id" in projection and projection["_id"] == 0:
                    result.pop("_id", None)
                if projection and "messages" in projection:
                    slice_val = projection["messages"]
                    if isinstance(slice_val, dict) and "$slice" in slice_val:
                        s = slice_val["$slice"]
                        msgs = result.get("messages", [])
                        if isinstance(s, int):
                            result["messages"] = msgs[:s]
                self._results.append(result)
        self._sort_key = None
        self._sort_dir = 1
        self._skip = 0
        self._limit = 100

    def sort(self, key, direction=-1):
        self._sort_key = key
        self._sort_dir = direction
        return self

    def skip(self, n: int):
        self._skip = n
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    async def to_list(self, length: int = 100):
        results = list(self._results)
        if self._sort_key:
            results.sort(
                key=lambda d: d.get(self._sort_key, ""),
                reverse=(self._sort_dir == -1),
            )
        results = results[self._skip:]
        return results[:min(self._limit, length)]


class _InMemoryDB:
    def __init__(self, collections: dict[str, _InMemoryCollection] | None = None) -> None:
        self._collections: dict[str, _InMemoryCollection] = collections or {}

    def __getitem__(self, name: str) -> _InMemoryCollection:
        if name not in self._collections:
            self._collections[name] = _InMemoryCollection()
        return self._collections[name]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_message_st = st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != "")

_source_st = st.fixed_dictionaries({
    "document_id": st.text(min_size=1, max_size=30).filter(lambda s: s.strip() != ""),
    "title": st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != ""),
    "source": st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != ""),
    "excerpt": st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != ""),
    "page": st.integers(min_value=0, max_value=500),
    "bbox": st.lists(st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False), min_size=4, max_size=4),
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_rag(answer_text: str, sources: list[DocumentSource] | None = None):
    """Return a mock LlamaIndexPipeline that yields StreamEvents."""
    mock_rag = MagicMock()

    async def fake_query_stream(
        question, context=None, top_k=5, region=None,
        source_filter=None, session_history=None, system_prompt=None,
    ):
        for word in answer_text.split():
            yield StreamEvent(type="token", content=word + " ")
        yield StreamEvent(
            type="done",
            answer=answer_text,
            sources=sources or [],
            llm_used="mock-llm",
            fallback_used=False,
        )

    mock_rag.query_stream = fake_query_stream
    return mock_rag


# ---------------------------------------------------------------------------
# Property 7: Document Chat Session Persistence Round-Trip
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(messages=st.lists(_message_st, min_size=1, max_size=10))
@pytest.mark.asyncio
async def test_property_7_session_persistence_round_trip(
    messages: list[str],
) -> None:
    """Sending N messages and retrieving history returns all N user+assistant
    pairs in order with sources preserved.

    **Validates: Requirements 5.3, 7.5**
    """
    # Build sources for each message
    test_sources = [
        DocumentSource(
            document_id="doc-1",
            title="Test Doc",
            source="TEST",
            excerpt="excerpt text",
            page=1,
            highlight=HighlightInfo(bbox=[10.0, 20.0, 30.0, 40.0], page=1),
        )
    ]

    db = _InMemoryDB()
    rag = _make_mock_rag("This is the answer.", sources=test_sources)
    service = DocumentChatService(db=db, rag_service=rag)

    session_id = "test-session-001"

    # Send all messages sequentially
    for msg in messages:
        events = []
        async for event in service.send_message_stream(
            session_id=session_id,
            user_message=msg,
            user_id="user-1",
        ):
            events.append(event)

        # Verify we got a done event
        done_events = [e for e in events if e.type == "done"]
        assert len(done_events) == 1, f"Expected 1 done event, got {len(done_events)}"

    # Retrieve history
    history = await service.get_history(session_id, user_id="user-1")
    assert history is not None, "Session not found after sending messages"

    stored_messages = history.get("messages", [])
    # Each user message produces a user turn + assistant turn = 2 * N
    assert len(stored_messages) == 2 * len(messages), (
        f"Expected {2 * len(messages)} messages, got {len(stored_messages)}"
    )

    # Verify order and content
    for i, msg in enumerate(messages):
        user_idx = i * 2
        assistant_idx = i * 2 + 1

        assert stored_messages[user_idx]["role"] == "user"
        assert stored_messages[user_idx]["content"] == msg
        assert stored_messages[user_idx]["sources"] == []

        assert stored_messages[assistant_idx]["role"] == "assistant"
        assert stored_messages[assistant_idx]["content"] == "This is the answer."
        # Verify sources are preserved (serialized as dicts)
        assert len(stored_messages[assistant_idx]["sources"]) == 1
        src = stored_messages[assistant_idx]["sources"][0]
        assert src["document_id"] == "doc-1"
        assert src["title"] == "Test Doc"
        assert src["highlight"] is not None
        assert src["highlight"]["bbox"] == [10.0, 20.0, 30.0, 40.0]


# ---------------------------------------------------------------------------
# Property 9: DocumentSource Completeness with Highlight Data
# ---------------------------------------------------------------------------

@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(source_data=_source_st, query=_message_st)
@pytest.mark.asyncio
async def test_property_9_document_source_completeness(
    source_data: dict,
    query: str,
) -> None:
    """For any DocumentSource returned by the Document Chat, all required fields
    (documentId, title, source, excerpt, page, highlight with bbox) SHALL be present.

    **Validates: Requirements 7.2, 7.4**
    """
    # Build a DocumentSource with highlight data from generated data
    source = DocumentSource(
        document_id=source_data["document_id"],
        title=source_data["title"],
        source=source_data["source"],
        excerpt=source_data["excerpt"],
        page=source_data["page"],
        highlight=HighlightInfo(bbox=source_data["bbox"], page=source_data["page"]),
    )

    db = _InMemoryDB()
    rag = _make_mock_rag("Answer text.", sources=[source])
    service = DocumentChatService(db=db, rag_service=rag)

    events = []
    async for event in service.send_message_stream(
        session_id=None,
        user_message=query,
        user_id="user-1",
    ):
        events.append(event)

    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1

    returned_sources = done_events[0].sources or []
    assert len(returned_sources) >= 1, "Expected at least 1 source in done event"

    for src in returned_sources:
        # Verify all required fields are present and non-null
        assert src.document_id is not None and src.document_id != ""
        assert src.title is not None and src.title != ""
        assert src.source is not None and src.source != ""
        assert src.excerpt is not None and src.excerpt != ""
        assert src.page is not None
        assert src.highlight is not None
        assert src.highlight.bbox is not None
        assert len(src.highlight.bbox) == 4
        assert isinstance(src.highlight.page, int)
