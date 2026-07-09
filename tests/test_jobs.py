"""Job flow test using the in-memory db + a stubbed storage layer."""

import time

import pytest
from fastapi.testclient import TestClient

from api import db, storage
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    db._mem_users.clear()
    db._mem_runs.clear()
    monkeypatch.setattr(storage, "download_bytes", lambda key: b"hello brave new world\n")
    yield


def _auth_headers():
    r = client.post(
        "/api/auth/signup",
        json={"email": "a@b.com", "password": "password123", "name": "A"},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_job_lifecycle():
    headers = _auth_headers()
    r = client.post("/api/jobs", json={"s3_key": "uploads/x/y.txt"}, headers=headers)
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    # Local mode runs the processor in a thread — poll briefly.
    for _ in range(50):
        run = client.get(f"/api/jobs/{run_id}", headers=headers).json()
        if run["status"] in ("done", "error"):
            break
        time.sleep(0.05)

    assert run["status"] == "done"
    assert run["result"]["words"] == 4

    assert client.get("/api/jobs/nope", headers=headers).status_code == 404
    assert client.get(f"/api/jobs/{run_id}").status_code == 401
