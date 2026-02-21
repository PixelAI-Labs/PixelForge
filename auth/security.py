"""Password hashing and JWT token helpers."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import hashlib
import secrets

import bcrypt
import jwt

# ---- Configuration -----------------------------------------------

def _default_secret() -> str:
    """Return a deterministic dev-only secret that is >= 32 bytes."""
    return hashlib.sha256(b"pixelforge-dev-secret-change-in-production").hexdigest()

SECRET_KEY = os.getenv("PIXELFORGE_JWT_SECRET") or _default_secret()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 60 * 60 * 24  # 24 hours


# ---- Password helpers --------------------------------------------

def hash_password(password: str) -> str:
    """Return bcrypt hash of the password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Check a plaintext password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ---- JWT helpers -------------------------------------------------

def create_access_token(user_id: str, username: str) -> str:
    """Create a signed JWT access token."""
    payload: Dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT.  Returns payload dict or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
