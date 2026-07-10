"""Phase-1 smoke test: liveness endpoint works with no DB/network.

The DB-readiness endpoint (/health/db) is exercised in the integration suite
(Phase 2+) against a real Postgres; here we only assert the process serves.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_liveness():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_metadata():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "CallSense"
    assert body["version"] == "0.1.0"
