"""Presigned S3 upload — dodges the API Gateway request-body size limit.

Client flow:
  1. GET /api/uploads/presign?filename=report.txt&content_type=text/plain
  2. PUT the file bytes to the returned upload_url (same Content-Type, no auth header)
  3. Pass s3_key to whatever endpoint consumes the file (e.g. POST /api/jobs)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api import storage
from api.auth_utils import get_current_user

router = APIRouter()


@router.get("/uploads/presign")
def presign_upload(
    filename: str,
    content_type: str = "application/octet-stream",
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    if not storage.configured():
        raise HTTPException(
            status_code=501,
            detail="DATA_BUCKET is not configured (set it, or run in the deployed stack)",
        )
    safe_name = filename.replace("/", "_")
    s3_key = f"uploads/{uuid.uuid4().hex}/{safe_name}"
    return {
        "upload_url": storage.presigned_upload_url(s3_key, content_type),
        "s3_key": s3_key,
    }
