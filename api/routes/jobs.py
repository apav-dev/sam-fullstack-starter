"""Async job pattern: POST starts a worker Lambda, GET polls its status.

In Lambda, the API function fires the processor function with
InvocationType="Event" (fire-and-forget) and returns immediately; the client
polls GET /api/jobs/{run_id}. Locally (PROCESSOR_FUNCTION unset) the processor
runs inline in a background thread so the flow is testable without AWS Lambda.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import db
from api.auth_utils import get_current_user

router = APIRouter()

PROCESSOR_FUNCTION = os.environ.get("PROCESSOR_FUNCTION", "")


class CreateJobRequest(BaseModel):
    s3_key: str


def _invoke_processor(payload: dict[str, Any]) -> None:
    if PROCESSOR_FUNCTION:
        import boto3

        boto3.client("lambda").invoke(
            FunctionName=PROCESSOR_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )
    else:
        from api import processor

        threading.Thread(target=processor.handler, args=(payload,), daemon=True).start()


@router.post("/jobs", status_code=202)
def create_job(
    req: CreateJobRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    db.create_run(run_id, s3_key=req.s3_key, user_id=user["sub"])
    _invoke_processor({"run_id": run_id, "s3_key": req.s3_key})
    return {"run_id": run_id, "status": "queued"}


@router.get("/jobs/{run_id}")
def get_job(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    run = db.get_run(run_id)
    # 404 (not 403) for other users' jobs — don't leak run_id existence
    if not run or (run.get("user_id") != user["sub"] and user.get("role") != "admin"):
        raise HTTPException(status_code=404, detail="Job not found")
    return run
