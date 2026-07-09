"""Worker Lambda: demo async job (word-count an uploaded S3 object).

Invoked by the API Lambda with InvocationType="Event". Replace the body of
_execute() with real work; the status-tracking scaffold is the reusable part.

Event shape: {"run_id": str, "s3_key": str}
"""

from __future__ import annotations

import traceback
from typing import Any

from api import db, storage


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    run_id = event["run_id"]
    try:
        _execute(run_id, event)
    except Exception as exc:
        db.update_run(
            run_id,
            status="error",
            error_msg=str(exc),
            error_detail=traceback.format_exc()[:4000],
        )
    return {"run_id": run_id}


def _execute(run_id: str, event: dict[str, Any]) -> None:
    db.update_run(run_id, status="running")

    data = storage.download_bytes(event["s3_key"])
    text = data.decode("utf-8", errors="replace")
    result = {
        "bytes": len(data),
        "words": len(text.split()),
        "lines": text.count("\n") + 1 if text else 0,
    }

    db.update_run(run_id, status="done", result=result)
