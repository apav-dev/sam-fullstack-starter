"""Auth endpoints: signup, login, me, optional Okta SSO exchange."""

from __future__ import annotations

import os
import uuid
from typing import Any

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from api import db
from api.auth_utils import (
    create_token,
    get_current_user,
    hash_password,
    okta_enabled,
    validate_okta_id_token,
    verify_password,
    OKTA_CLIENT_ID,
    OKTA_ISSUER,
)

router = APIRouter()


def _allowed_signup_domains() -> list[str]:
    raw = os.environ.get("ALLOWED_SIGNUP_EMAIL_DOMAINS", "").strip()
    if not raw:
        return []
    return [d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()]


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OktaExchangeRequest(BaseModel):
    id_token: str


def _build_response(user: dict[str, Any]) -> dict[str, Any]:
    token = create_token(
        user["user_id"], user["email"], user.get("name", ""), user.get("role", "user")
    )
    return {"token": token, "user": db.safe_user(user)}


@router.post("/auth/signup")
def signup(req: SignupRequest) -> dict[str, Any]:
    email = req.email.lower()

    domains = _allowed_signup_domains()
    if domains and email.split("@")[-1] not in domains:
        raise HTTPException(
            status_code=403,
            detail=f"Signups are restricted to: {', '.join(domains)}",
        )
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if db.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    role = "admin" if db.count_users() == 0 else "user"
    user = {
        "user_id": str(uuid.uuid4()),
        "email": email,
        "name": req.name.strip(),
        "role": role,
        "password_hash": hash_password(req.password),
    }
    db.create_user(user)
    return _build_response(user)


@router.post("/auth/login")
def login(req: LoginRequest) -> dict[str, Any]:
    user = db.get_user_by_email(req.email.lower())
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _build_response(user)


@router.get("/auth/me")
def me(payload: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user = db.get_user(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {"user": db.safe_user(user)}


@router.get("/auth/okta/config")
def okta_config() -> dict[str, Any]:
    if not okta_enabled():
        return {"enabled": False}
    return {"enabled": True, "issuer": OKTA_ISSUER, "clientId": OKTA_CLIENT_ID}


@router.post("/auth/okta/exchange")
def okta_exchange(req: OktaExchangeRequest) -> dict[str, Any]:
    try:
        claims = validate_okta_id_token(req.id_token)
    except pyjwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Okta token: {exc}")

    email = str(claims.get("email", "")).lower()
    if not email:
        raise HTTPException(status_code=401, detail="Okta token missing email claim")

    user = db.get_user_by_email(email)
    if not user:
        # Auto-provision SSO users; empty password_hash means SSO-only account.
        user = {
            "user_id": str(uuid.uuid4()),
            "email": email,
            "name": str(claims.get("name", email)),
            "role": "user",
            "password_hash": "",
        }
        db.create_user(user)
    return _build_response(user)
