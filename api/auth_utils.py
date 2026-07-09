"""Auth primitives: password hashing, JWT issue/verify, FastAPI dependencies.

Email/password auth uses PBKDF2-SHA256 (stdlib) + HS256 JWTs (PyJWT).
Okta SSO is optional: set OKTA_ISSUER and OKTA_CLIENT_ID to enable; when unset
the JWKS client is never built, so there is zero cold-start cost.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ── Config ────────────────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-do-not-use-in-prod-0123456789")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", str(24 * 7)))

_PBKDF2_ITERS = 260_000
_SALT_BYTES = 32

# ── Okta (optional SSO) ───────────────────────────────────────────────────────
OKTA_ISSUER = os.environ.get("OKTA_ISSUER", "").rstrip("/")
OKTA_CLIENT_ID = os.environ.get("OKTA_CLIENT_ID", "")

_jwks_client: Optional["jwt.PyJWKClient"] = None


def okta_enabled() -> bool:
    return bool(OKTA_ISSUER and OKTA_CLIENT_ID)


def _get_jwks_client() -> "jwt.PyJWKClient":
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"{OKTA_ISSUER}/v1/keys", cache_keys=True, lifespan=3600
        )
    return _jwks_client


def validate_okta_id_token(id_token: str) -> dict[str, Any]:
    """Validate an Okta id_token (RS256 via JWKS). Raises jwt exceptions on failure."""
    if not okta_enabled():
        raise HTTPException(status_code=400, detail="Okta SSO is not configured")
    signing_key = _get_jwks_client().get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=OKTA_CLIENT_ID,
        issuer=OKTA_ISSUER,
    )


# ── Password hashing (PBKDF2-SHA256) ──────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return base64.b64encode(salt + dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        raw = base64.b64decode(stored.encode())
    except Exception:
        return False
    salt, expected = raw[:_SALT_BYTES], raw[_SALT_BYTES:]
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return secrets.compare_digest(dk, expected)


# ── JWT ───────────────────────────────────────────────────────────────────────
def create_token(user_id: str, email: str, name: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ── FastAPI dependencies ──────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


def _extract_payload(
    creds: Optional[HTTPAuthorizationCredentials],
) -> Optional[dict[str, Any]]:
    if creds is None or not creds.credentials:
        return None
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWTError:
        return None


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict[str, Any]:
    payload = _extract_payload(creds)
    if payload is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload


def get_optional_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[dict[str, Any]]:
    return _extract_payload(creds)


def require_admin(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
