"""Auth router — /auth/register  &  /auth/login."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from auth.dependencies import get_current_user
from auth.models import User
from auth.security import create_access_token, hash_password, verify_password
from auth.store import UserStore

router = APIRouter(prefix="/auth", tags=["auth"])

# Shared user store — injected via app state in create_app
_user_store: UserStore | None = None


def init_user_store(store: UserStore) -> None:
    """Must be called once during app startup."""
    global _user_store
    _user_store = store


def _store() -> UserStore:
    if _user_store is None:
        raise RuntimeError("UserStore not initialised")
    return _user_store


# ---- schemas ---------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    email: str = Field(min_length=5)
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


class MeResponse(BaseModel):
    user_id: str
    username: str
    email: str


# ---- endpoints --------------------------------------------------

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest) -> AuthResponse:
    store = _store()

    if store.email_exists(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    if store.username_exists(req.username):
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
    )
    store.add(user)

    token = create_access_token(user.user_id, user.username)
    return AuthResponse(access_token=token, user_id=user.user_id, username=user.username)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest) -> AuthResponse:
    store = _store()
    user = store.get_by_email(req.email)

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.user_id, user.username)
    return AuthResponse(access_token=token, user_id=user.user_id, username=user.username)


@router.get("/me", response_model=MeResponse)
async def me(current_user: Dict[str, Any] = Depends(get_current_user)) -> MeResponse:
    store = _store()
    user = store.get_by_id(current_user["sub"])
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(user_id=user.user_id, username=user.username, email=user.email)
