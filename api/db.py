"""DynamoDB access for users and runs.

When the table env vars are unset (local dev / unit tests), falls back to
in-memory dicts so the API runs without AWS. In Lambda the env vars are always
set by template.yaml.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

USERS_TABLE = os.environ.get("USERS_TABLE", "")
RUNS_TABLE = os.environ.get("RUNS_TABLE", "")

RUN_TTL_DAYS = int(os.environ.get("RUN_TTL_DAYS", "7"))

# In-memory fallback stores (local dev only)
_mem_users: dict[str, dict[str, Any]] = {}
_mem_runs: dict[str, dict[str, Any]] = {}

_dynamodb = None


def _table(name: str):
    global _dynamodb
    if _dynamodb is None:
        import boto3

        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(name)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl_epoch() -> int:
    return int(time.time()) + RUN_TTL_DAYS * 86_400


# ── Users ─────────────────────────────────────────────────────────────────────
def create_user(user: dict[str, Any]) -> None:
    user.setdefault("created_at", _now_iso())
    if USERS_TABLE:
        _table(USERS_TABLE).put_item(Item=user)
    else:
        _mem_users[user["user_id"]] = user


def get_user(user_id: str) -> Optional[dict[str, Any]]:
    if USERS_TABLE:
        resp = _table(USERS_TABLE).get_item(Key={"user_id": user_id})
        return resp.get("Item")
    return _mem_users.get(user_id)


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    email = email.lower()
    if USERS_TABLE:
        from boto3.dynamodb.conditions import Key

        resp = _table(USERS_TABLE).query(
            IndexName="EmailIndex", KeyConditionExpression=Key("email").eq(email)
        )
        items = resp.get("Items", [])
        return items[0] if items else None
    return next((u for u in _mem_users.values() if u["email"] == email), None)


def count_users() -> int:
    if USERS_TABLE:
        # Scan is acceptable here: called only on signup, table is small.
        resp = _table(USERS_TABLE).scan(Select="COUNT")
        return int(resp.get("Count", 0))
    return len(_mem_users)


def safe_user(user: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets before returning a user object to the client."""
    return {k: v for k, v in user.items() if k != "password_hash"}


# ── Runs (async job state) ────────────────────────────────────────────────────
def create_run(run_id: str, **fields: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "run_id": run_id,
        "status": "queued",
        "created_at": _now_iso(),
        "ttl": _ttl_epoch(),
        **fields,
    }
    if RUNS_TABLE:
        _table(RUNS_TABLE).put_item(Item=item)
    else:
        _mem_runs[run_id] = item
    return item


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    if RUNS_TABLE:
        resp = _table(RUNS_TABLE).get_item(Key={"run_id": run_id})
        return resp.get("Item")
    return _mem_runs.get(run_id)


def update_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    if RUNS_TABLE:
        # Dynamic SET expression; attribute-name aliases dodge reserved words
        # like "status".
        names = {f"#k{i}": k for i, k in enumerate(fields)}
        values = {f":v{i}": v for i, v in enumerate(fields.values())}
        expr = ", ".join(f"#k{i} = :v{i}" for i in range(len(fields)))
        _table(RUNS_TABLE).update_item(
            Key={"run_id": run_id},
            UpdateExpression=f"SET {expr}",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    else:
        _mem_runs.setdefault(run_id, {"run_id": run_id}).update(fields)
