"""MongoDB connection manager.

Provides a single Motor (async) client and a pymongo (sync) client
shared across the application.

Collections
-----------
- users       : registered accounts
- jobs        : generation jobs + embedded attempt records
- artifacts   : images stored as Binary + metadata docs
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient
from pymongo.database import Database as SyncDatabase
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

logger = logging.getLogger(__name__)

# ---- configuration -------------------------------------------------------

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "pixelforge")

# ---- singleton clients ---------------------------------------------------

_async_client: Optional[AsyncIOMotorClient] = None
_sync_client: Optional[MongoClient] = None


def get_async_client() -> AsyncIOMotorClient:
    """Return (or create) the Motor async client."""
    global _async_client
    if _async_client is None:
        _async_client = AsyncIOMotorClient(MONGO_URL)
    return _async_client


def get_sync_client() -> MongoClient:
    """Return (or create) the pymongo sync client."""
    global _sync_client
    if _sync_client is None:
        _sync_client = MongoClient(MONGO_URL)
    return _sync_client


def get_async_db() -> AsyncIOMotorDatabase:
    """Return the async database handle."""
    return get_async_client()[MONGO_DB_NAME]


def get_sync_db() -> SyncDatabase:
    """Return the sync database handle."""
    return get_sync_client()[MONGO_DB_NAME]


# ---- lifecycle helpers ---------------------------------------------------

async def ping_mongo() -> bool:
    """Return True if Mongo is reachable (async)."""
    try:
        await get_async_client().admin.command("ping")
        logger.info("MongoDB connection OK (%s)", MONGO_URL)
        return True
    except ConnectionFailure:
        logger.error("Cannot reach MongoDB at %s", MONGO_URL)
        return False


async def ensure_indexes() -> None:
    """Create required indexes (idempotent)."""
    db = get_async_db()

    async def _create_index_safe(col, keys, **kwargs) -> None:
        try:
            await col.create_index(keys, **kwargs)
        except DuplicateKeyError as exc:
            logger.warning(
                "Skipping index %s on %s due to duplicate legacy data: %s",
                keys,
                col.name,
                exc,
            )
        except OperationFailure as exc:
            logger.warning(
                "Skipping index %s on %s due to unsupported/invalid index spec: %s",
                keys,
                col.name,
                exc,
            )

    # Users
    await _create_index_safe(
        db.users,
        "user_id",
        unique=True,
        partialFilterExpression={"user_id": {"$type": "string"}},
    )
    await _create_index_safe(
        db.users,
        "email",
        unique=True,
        partialFilterExpression={"email": {"$type": "string"}},
    )
    await _create_index_safe(
        db.users,
        "username",
        unique=True,
        partialFilterExpression={"username": {"$type": "string"}},
    )

    # Jobs
    await _create_index_safe(db.jobs, "job_id", unique=True)
    await _create_index_safe(db.jobs, "created_at")

    # Artifacts (images)
    await _create_index_safe(db.artifacts, "artifact_id", unique=True)
    await _create_index_safe(db.artifacts, "job_id")

    # Artifact metadata
    await _create_index_safe(db.artifact_meta, "job_id", unique=True)

    # Edit sessions
    await _create_index_safe(db.edit_sessions, "session_id", unique=True)

    logger.info("MongoDB indexes ensured.")


def close_clients() -> None:
    """Gracefully close both clients."""
    global _async_client, _sync_client
    if _async_client:
        _async_client.close()
        _async_client = None
    if _sync_client:
        _sync_client.close()
        _sync_client = None


def verify_sync_connection() -> bool:
    """Verify MongoDB is reachable using the sync client. Call at startup."""
    try:
        get_sync_client().admin.command("ping")
        logger.info("MongoDB sync connection OK (%s / %s)", MONGO_URL, MONGO_DB_NAME)
        return True
    except Exception as exc:
        logger.error("MongoDB sync connection FAILED: %s", exc)
        return False
