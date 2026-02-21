"""In-memory user store for authentication."""

from __future__ import annotations

from typing import Dict, Optional

from auth.models import User


class UserStore:
    """Simple in-memory user store."""

    def __init__(self) -> None:
        self._users_by_id: Dict[str, User] = {}
        self._users_by_email: Dict[str, User] = {}
        self._users_by_username: Dict[str, User] = {}

    def add(self, user: User) -> None:
        self._users_by_id[user.user_id] = user
        self._users_by_email[user.email.lower()] = user
        self._users_by_username[user.username.lower()] = user

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self._users_by_id.get(user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        return self._users_by_email.get(email.lower())

    def get_by_username(self, username: str) -> Optional[User]:
        return self._users_by_username.get(username.lower())

    def email_exists(self, email: str) -> bool:
        return email.lower() in self._users_by_email

    def username_exists(self, username: str) -> bool:
        return username.lower() in self._users_by_username
