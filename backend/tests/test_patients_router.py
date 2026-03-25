# Feature: diagno-pilot-improvements, Property 11: Pagination — cohérence des métadonnées de réponse
"""
Tests de propriété pour la pagination des patients — Diagno-Pilot

Property 11 : Pagination — cohérence des métadonnées de réponse
**Validates: Requirements 8.1, 8.2, 8.3**

Pour tout appel à GET /api/v1/patients?page=P&page_size=S avec P ≥ 1 et
1 ≤ S ≤ 100, la réponse doit satisfaire :
  - len(items) ≤ S
  - page == P
  - page_size == S
  - si P * S > total alors len(items) == 0
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.routers.auth import create_access_token

# ---------------------------------------------------------------------------
# Stratégies Hypothesis
# ---------------------------------------------------------------------------

# Pages valides : P ≥ 1
page_strategy = st.integers(min_value=1, max_value=50)

# Tailles de page valides : 1 ≤ S ≤ 100
page_size_strategy = st.integers(min_value=1, max_value=100)

# Nombre total de patients en base (0 à 200 pour couvrir les cas limites)
total_patients_strategy = st.integers(min_value=0, max_value=200)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_doc(user_id: str) -> dict:
    return {
        "_id": ObjectId(user_id),
        "email": f"{user_id[:8]}@test.com",
        "role": "medecin",
        "full_name": "Dr. Test",
        "locale": "fr",
    }


def _make_token(user_id: str) -> str:
    return create_access_token(user_id=user_id, role="medecin")


def _build_patient_docs(n: int, created_by: ObjectId) -> list[dict]:
    """Construit n documents patients factices."""
    from datetime import datetime, timezone
    return [
        {
            "_id": ObjectId(),
            "full_name": f"Patient {i}",
            "date_of_birth": None,
            "weight_kg": None,
            "age_group": None,
            "allergies": [],
            "comorbidities": {"renal_failure": False, "hepatic_failure": False},
            "current_medications": [],
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Property 11 — cohérence des métadonnées de pagination
# ---------------------------------------------------------------------------


@given(
    page=page_strategy,
    page_size=page_size_strategy,
    total_in_db=total_patients_strategy,
)
@h_settings(max_examples=100, deadline=None)
def test_p11_pagination_metadata_consistency(
    page: int,
    page_size: int,
    total_in_db: int,
):
    """
    Feature: diagno-pilot-improvements, Property 11:
    Pour tout appel GET /api/v1/patients?page=P&page_size=S avec P ≥ 1 et
    1 ≤ S ≤ 100, la réponse doit satisfaire :
      - len(items) ≤ S
      - page == P
      - page_size == S
      - si P * S > total alors len(items) == 0

    **Validates: Requirements 8.1, 8.2, 8.3**
    """
    user_id = str(ObjectId())

    async def _run():
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.core.auth import get_current_user

        user_doc = _make_user_doc(user_id)
        token = _make_token(user_id)
        created_by_oid = ObjectId(user_id)

        # Construire les documents patients factices
        all_docs = _build_patient_docs(total_in_db, created_by_oid)

        # Calculer la tranche attendue (skip/limit)
        skip = (page - 1) * page_size
        if skip >= total_in_db and total_in_db > 0:
            expected_docs = []
        else:
            expected_docs = all_docs[skip: skip + page_size]

        async def mock_get_current_user():
            return user_doc

        # Mock de la collection MongoDB patients
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=total_in_db)

        # Mock du curseur find().skip().limit()
        mock_cursor = MagicMock()
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=expected_docs)
        mock_collection.find = MagicMock(return_value=mock_cursor)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        app.dependency_overrides[get_current_user] = mock_get_current_user

        try:
            with patch("backend.services.patient_service.db") as mock_db_obj:
                mock_db_obj.get_db.return_value = mock_db

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    headers = {"Authorization": f"Bearer {token}"}
                    resp = await client.get(
                        f"/api/v1/patients?page={page}&page_size={page_size}",
                        headers=headers,
                    )

                    assert resp.status_code == 200, (
                        f"Attendu 200, obtenu {resp.status_code}: {resp.text}"
                    )

                    data = resp.json()

                    # Vérification des champs de métadonnées
                    assert "items" in data, "La réponse doit contenir 'items'"
                    assert "total" in data, "La réponse doit contenir 'total'"
                    assert "page" in data, "La réponse doit contenir 'page'"
                    assert "page_size" in data, "La réponse doit contenir 'page_size'"

                    items = data["items"]
                    total = data["total"]
                    resp_page = data["page"]
                    resp_page_size = data["page_size"]

                    # Propriété : page et page_size reflètent les paramètres de la requête
                    assert resp_page == page, (
                        f"page attendu={page}, obtenu={resp_page}"
                    )
                    assert resp_page_size == page_size, (
                        f"page_size attendu={page_size}, obtenu={resp_page_size}"
                    )

                    # Propriété : total reflète le nombre réel en base
                    assert total == total_in_db, (
                        f"total attendu={total_in_db}, obtenu={total}"
                    )

                    # Propriété : len(items) ≤ page_size
                    assert len(items) <= page_size, (
                        f"len(items)={len(items)} doit être ≤ page_size={page_size}"
                    )

                    # Propriété : si P * S > total alors items est vide (REQ 8.3)
                    # Interprétation correcte : la page commence au-delà du total
                    # (page-1)*page_size >= total → items vide
                    page_start = (page - 1) * page_size
                    if page_start >= total_in_db and total_in_db > 0:
                        assert len(items) == 0, (
                            f"Attendu items=[] car page_start={page_start} >= total={total_in_db}, "
                            f"obtenu {len(items)} items"
                        )

                    # Cas total=0 : items doit toujours être vide
                    if total_in_db == 0:
                        assert len(items) == 0, (
                            f"Attendu items=[] car total=0, obtenu {len(items)} items"
                        )

        finally:
            app.dependency_overrides.pop(get_current_user, None)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Test unitaire : paramètres invalides → HTTP 422
# ---------------------------------------------------------------------------


def test_invalid_page_returns_422():
    """
    page < 1 doit retourner HTTP 422 (validation Pydantic).
    **Validates: Requirements 8.1**
    """
    user_id = str(ObjectId())

    async def _run():
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.core.auth import get_current_user

        user_doc = _make_user_doc(user_id)
        token = _make_token(user_id)

        async def mock_get_current_user():
            return user_doc

        app.dependency_overrides[get_current_user] = mock_get_current_user
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/v1/patients?page=0",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 422, (
                    f"page=0 doit retourner 422, obtenu {resp.status_code}"
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


def test_invalid_page_size_returns_422():
    """
    page_size hors [1, 100] doit retourner HTTP 422 (validation Pydantic).
    **Validates: Requirements 8.1**
    """
    user_id = str(ObjectId())

    async def _run():
        from httpx import AsyncClient, ASGITransport
        from backend.main import app
        from backend.core.auth import get_current_user

        user_doc = _make_user_doc(user_id)
        token = _make_token(user_id)

        async def mock_get_current_user():
            return user_doc

        app.dependency_overrides[get_current_user] = mock_get_current_user
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # page_size=0 → invalide
                resp = await client.get(
                    "/api/v1/patients?page_size=0",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 422, (
                    f"page_size=0 doit retourner 422, obtenu {resp.status_code}"
                )

                # page_size=101 → invalide
                resp = await client.get(
                    "/api/v1/patients?page_size=101",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 422, (
                    f"page_size=101 doit retourner 422, obtenu {resp.status_code}"
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())
