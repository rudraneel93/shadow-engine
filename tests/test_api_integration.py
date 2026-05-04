"""End-to-end API workflow test — validates the full pipeline."""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app with a temporary data directory."""
    import os
    import tempfile

    tmpdir = tempfile.mkdtemp()
    # Set environment before importing the app
    os.environ["SHADOW_ENGINE_STORAGE_PATH"] = tmpdir
    os.environ["SHADOW_ENGINE_API_KEY"] = "test-key"
    os.environ["SHADOW_ENGINE_REDIS_URL"] = "redis://localhost:6379"
    os.environ["SHADOW_EXPERIMENTAL"] = "1"

    from shadow_engine.api_server.server import app

    client = TestClient(app)
    yield client

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestFullAPIWorkflow:
    """Test the complete API pipeline end-to-end."""

    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_bootstrap(self, client):
        r = client.post("/bootstrap", params={"repo": "."},
                        headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "bootstrapped"
        assert data["symbols_indexed"] >= 0
        assert data["files_indexed"] >= 0

    def test_context_generation(self, client):
        r = client.get("/context",
                       params={"task": "fix the login rate-limiting bug"},
                       headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert "context" in data
        assert "Shadow Engineer" in data["context"]

    def test_search(self, client):
        r = client.get("/search",
                       params={"query": "ShadowEngine"},
                       headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_suggest(self, client):
        r = client.get("/suggest",
                       params={"task": "fix the login bug"},
                       headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert "problem_type" in data
        assert "recommended_approach" in data

    def test_experiment(self, client):
        r = client.post("/experiment",
                        params={"task": "fix the login bug", "variants": 2},
                        headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert "total_variants" in data

    def test_ingest_session(self, client):
        payload = {
            "session_id": "api-test-001",
            "outcome": "success",
            "prompt": "fix the login bug",
            "approach": "Targeted Fix",
            "model": "test-model",
            "files_changed": ["src/auth.py", "tests/test_auth.py"],
            "tests_passed": 10,
            "tests_failed": 0,
            "duration_seconds": 30.0,
            "token_count": 5000,
        }
        r = client.post("/sessions/ingest",
                        json=payload,
                        headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ingested"

    def test_report(self, client):
        r = client.get("/report",
                       headers={"X-API-Key": "test-key"})
        assert r.status_code == 200

    def test_stats(self, client):
        r = client.get("/stats",
                       headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert "total_symbols" in data

    def test_metrics(self, client):
        r = client.get("/metrics",
                       headers={"X-API-Key": "test-key"})
        assert r.status_code == 200


class TestAPISecurity:
    """Tests for API security: auth, rate limiting, path traversal."""

    def test_missing_api_key_returns_401(self, client):
        r = client.get("/stats")
        assert r.status_code == 401

    def test_invalid_api_key_returns_401(self, client):
        r = client.get("/stats", headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401

    def test_path_traversal_blocked(self, client):
        r = client.post("/bootstrap",
                        params={"repo": "../../../private"},
                        headers={"X-API-Key": "test-key"})
        # Path sandboxing blocks access — non-200 response expected
        assert r.status_code != 200

    def test_invalid_outcome_rejected(self, client):
        payload = {
            "session_id": "api-test-002",
            "outcome": "invalid_outcome",
            "prompt": "test",
        }
        r = client.post("/sessions/ingest",
                        json=payload,
                        headers={"X-API-Key": "test-key"})
        assert r.status_code == 422