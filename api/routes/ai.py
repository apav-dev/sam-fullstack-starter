"""Example Bedrock endpoint — proves the model-access + IAM wiring end to end."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth_utils import get_current_user

router = APIRouter()

BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "us.amazon.nova-lite-v1:0")

_bedrock = None


def _client():
    global _bedrock
    if _bedrock is None:
        import boto3

        _bedrock = boto3.client("bedrock-runtime")
    return _bedrock


class EchoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


@router.post("/ai/echo")
def ai_echo(
    req: EchoRequest,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    try:
        resp = _client().converse(
            modelId=BEDROCK_MODEL,
            messages=[{"role": "user", "content": [{"text": req.prompt}]}],
            inferenceConfig={"maxTokens": 512},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bedrock call failed: {exc}")

    blocks = resp.get("output", {}).get("message", {}).get("content", [])
    text = "".join(b.get("text", "") for b in blocks)
    return {"model": BEDROCK_MODEL, "reply": text}
