"""
Tests de propriété pour le script de seed — Diagno-Pilot

# Feature: app-consistency, Property 18: Pour toute DB contenant déjà les utilisateurs, seed ne crée aucun doublon

**Validates: Requirements 10.1, 10.4**

Propriété 18 : Pour toute base de données contenant déjà les utilisateurs de seed,
une nouvelle exécution du script seed.py ne doit créer aucun doublon et doit
terminer sans erreur.
"""
from __future__ import annotations

import asyncio

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# Import the seed function and SEED_USERS from the script
import sys
import os

# Ensure scripts/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from seed import seed, SEED_USERS  # noqa: E402


# ---------------------------------------------------------------------------
# Fake in-memory collection
# ---------------------------------------------------------------------------

class FakeCollection:
    """Minimal async MongoDB collection stub for testing."""

    def __init__(self, initial_docs: list[dict]):
        # Store docs keyed by email for fast lookup
        self._docs: dict[str, dict] = {doc["email"]: doc for doc in initial_docs}
        self.insert_calls: list[dict] = []

    async def find_one(self, query: dict) -> dict | None:
        email = query.get("email")
        if email is None:
            return None
        return self._docs.get(email)

    async def insert_one(self, doc: dict) -> None:
        email = doc["email"]
        self._docs[email] = doc
        self.insert_calls.append(doc)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: generate a subset of seed user emails that are "already in the DB"
# This simulates various pre-existing DB states (empty, partial, full).
pre_existing_emails_strategy = st.lists(
    st.sampled_from([u["email"] for u in SEED_USERS]),
    min_size=0,
    max_size=len(SEED_USERS),
    unique=True,
)


def build_initial_docs(emails: list[str]) -> list[dict]:
    """Build fake existing documents for the given emails."""
    return [
        {
            "email": email,
            "password_hash": "existing_hash",
            "full_name": "Existing User",
            "role": "medecin",
        }
        for email in emails
    ]


# ---------------------------------------------------------------------------
# Property 18 : Seed idempotent — no duplicates when users already exist
# ---------------------------------------------------------------------------

@given(pre_existing_emails=pre_existing_emails_strategy)
@h_settings(max_examples=100, deadline=None)
def test_seed_idempotent_no_duplicates(pre_existing_emails: list[str]):
    """
    # Feature: app-consistency, Property 18: Pour toute DB contenant déjà les utilisateurs, seed ne crée aucun doublon

    **Validates: Requirements 10.1, 10.4**

    For any DB state containing a subset of seed users, running seed() again
    must NOT insert any document whose email already exists in the collection.
    The total number of documents per email must remain exactly 1.
    """
    initial_docs = build_initial_docs(pre_existing_emails)
    col = FakeCollection(initial_docs)

    # Run the seed against the fake collection
    created, skipped = asyncio.run(seed(users_col=col))

    # Verify: no email appears more than once in the final collection
    all_emails = list(col._docs.keys())
    assert len(all_emails) == len(set(all_emails)), (
        f"Duplicate emails found after seed: {all_emails}"
    )

    # Verify: every seed user email is present exactly once
    seed_emails = {u["email"] for u in SEED_USERS}
    for email in seed_emails:
        assert email in col._docs, f"Seed user {email!r} missing after seed"

    # Verify: no insert was made for already-existing users
    inserted_emails = {doc["email"] for doc in col.insert_calls}
    pre_existing_set = set(pre_existing_emails)
    overlap = inserted_emails & pre_existing_set
    assert not overlap, (
        f"Seed inserted documents for already-existing emails: {overlap}"
    )

    # Verify: created + skipped == total seed users
    assert created + skipped == len(SEED_USERS), (
        f"created={created} + skipped={skipped} != {len(SEED_USERS)}"
    )

    # Verify: skipped count matches pre-existing users
    assert skipped == len(pre_existing_emails), (
        f"Expected {len(pre_existing_emails)} skipped, got {skipped}"
    )


# ---------------------------------------------------------------------------
# Property 18b : Seed fully idempotent — running twice produces no new inserts
# ---------------------------------------------------------------------------

def test_seed_fully_idempotent_second_run():
    """
    # Feature: app-consistency, Property 18: Pour toute DB contenant déjà les utilisateurs, seed ne crée aucun doublon

    **Validates: Requirements 10.1, 10.4**

    Running seed() twice on the same collection must produce 0 inserts on the
    second run (all users already exist after the first run).
    """
    col = FakeCollection([])

    # First run: should create all users
    created1, skipped1 = asyncio.run(seed(users_col=col))
    assert created1 == len(SEED_USERS)
    assert skipped1 == 0

    # Reset insert tracking for second run
    col.insert_calls = []

    # Second run: should skip all users
    created2, skipped2 = asyncio.run(seed(users_col=col))
    assert created2 == 0
    assert skipped2 == len(SEED_USERS)
    assert col.insert_calls == [], "Second seed run must not insert any documents"
