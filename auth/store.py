"""MongoDB-backed user store for authentication."""

from __future__ import annotations

from typing import Optional

from pymongo.collection import Collection
from pymongo.database import Database as SyncDatabase

from auth.models import User


def _user_to_doc(user: User) -> dict:
    """Serialise a User dataclass to a MongoDB document."""
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email.lower(),
        "hashed_password": user.hashed_password,
        "created_at": user.created_at,
        "is_active": user.is_active,
    }


def _doc_to_user(doc: dict) -> User:
    """Deserialise a MongoDB document to a User dataclass."""
    return User(
        username=doc["username"],
        email=doc["email"],
        hashed_password=doc["hashed_password"],
        user_id=doc["user_id"],
        created_at=doc["created_at"],
        is_active=doc.get("is_active", True),
    )


class UserStore:
    """MongoDB-backed user store (sync pymongo)."""

    def __init__(self, db: SyncDatabase) -> None:
        self._col: Collection = db["users"]

    # ---- writes -------------------------------------------------

    def add(self, user: User) -> None:
        self._col.insert_one(_user_to_doc(user))

    # ---- reads --------------------------------------------------

    def get_by_id(self, user_id: str) -> Optional[User]:
        doc = self._col.find_one({"user_id": user_id})
        return _doc_to_user(doc) if doc else None

    def get_by_email(self, email: str) -> Optional[User]:
        doc = self._col.find_one({"email": email.lower()})
        return _doc_to_user(doc) if doc else None

    def get_by_username(self, username: str) -> Optional[User]:
        doc = self._col.find_one({"username": {"$regex": f"^{username}$", "$options": "i"}})
        return _doc_to_user(doc) if doc else None

    def email_exists(self, email: str) -> bool:
        return self._col.count_documents({"email": email.lower()}, limit=1) > 0

    def username_exists(self, username: str) -> bool:
        return self._col.count_documents(
            {"username": {"$regex": f"^{username}$", "$options": "i"}}, limit=1
        ) > 0
