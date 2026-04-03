"""
Seed script — creates default users in MongoDB.

Usage (from workspace root):
    python scripts/seed.py

Or via Docker:
    docker-compose run --rm seed python /workspace/scripts/seed.py

Default accounts created:
    admin@diagno-pilot.com   / Admin1234!   (role: admin)
    medecin@diagno-pilot.com / Medecin1234! (role: medecin)
"""

import asyncio
import os
import sys

import bcrypt
from dotenv import load_dotenv

load_dotenv()

import motor.motor_asyncio

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/diagno_pilot")
DB_NAME = MONGODB_URI.split("/")[-1].split("?")[0]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


SEED_USERS = [
    {
        "email": "admin@diagno-pilot.com",
        "password": "Admin1234!",
        "full_name": "Administrateur",
        "role": "admin",
    },
    {
        "email": "medecin@diagno-pilot.com",
        "password": "Medecin1234!",
        "full_name": "Dr. Kofi Mensah",
        "role": "medecin",
    },
]


async def seed(users_col=None):
    """Run the seed. Accepts an optional collection for testing (dependency injection)."""
    own_client = None
    if users_col is None:
        # serverSelectionTimeoutMS=60s lets the driver wait for RS primary election
        own_client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGODB_URI, serverSelectionTimeoutMS=60000
        )
        db = own_client[DB_NAME]
        users_col = db["users"]

    created = 0
    skipped = 0

    for user in SEED_USERS:
        existing = await users_col.find_one({"email": user["email"]})
        if existing:
            print(f"  skip  {user['email']} (already exists)")
            skipped += 1
            continue

        await users_col.insert_one({
            "email": user["email"],
            "password_hash": hash_password(user["password"]),
            "full_name": user["full_name"],
            "role": user["role"],
        })
        print(f"  created  {user['email']}  role={user['role']}")
        created += 1

    if own_client is not None:
        own_client.close()

    print(f"\nDone — {created} created, {skipped} skipped.")
    return created, skipped


if __name__ == "__main__":
    try:
        asyncio.run(seed())
    except Exception as exc:
        print(f"[seed] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
