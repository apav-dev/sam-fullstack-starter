"""Thin S3 wrapper for the data bucket (uploads + job outputs)."""

from __future__ import annotations

import os

BUCKET = os.environ.get("DATA_BUCKET", "")

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        import boto3

        _s3 = boto3.client("s3")
    return _s3


def configured() -> bool:
    return bool(BUCKET)


def presigned_upload_url(key: str, content_type: str, expires_in: int = 900) -> str:
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def presigned_download_url(key: str, filename: str, expires_in: int = 900) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=expires_in,
    )


def download_bytes(key: str) -> bytes:
    resp = _client().get_object(Bucket=BUCKET, Key=key)
    return resp["Body"].read()


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    _client().put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type)
