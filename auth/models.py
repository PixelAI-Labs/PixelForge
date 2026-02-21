"""Authentication domain models."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    """Registered user."""

    username: str
    email: str
    hashed_password: str
    user_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    is_active: bool = True
