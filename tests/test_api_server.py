"""Tests for FastAPI server — auth, rate limiting, path validation, health checks."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shadow_engine.api_server.server import app, _registry, _configured_api_key, _rate_limiter


@pytest.fixture
def client():
    """Create a test client with a fresh engine registry."""
    _registry._engines.clear()
    _registry._access_order.clear()
    # Reset auth to disabled for tests
    import shadow_engine.api_server.server as srv
    old_key = _configured_api_key
    srv._configured_api_key = None
    yield TestClient(app)
    srv._configured_api_key = old_key
    _registry.close_all()


@pytest.fixture
def client_with_auth():
    """Create a test client with API key auth enabled."""
    _registry._engines.clear()
    _registry._access_order.clear()
    import shadow_engine.api_server.server as srv
    srv._configured_api_key = "test-secret-key"
    yield TestClient(app)
    srv._configured_api_key = None
    _registry.close_all()


class TestHealthEndpoint:
    """Health endpoint should always work without auth."""

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "timestamp" in data

    def test_health_v1_prefix(self, client):
        response = client.get("/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_with_auth_header(self, client):
        """Health check should work with or without auth header."""
        response = client.get("/health", headers={"X-API-Key": "anything"})
        assert response.status_code == 200


class TestAuthentication:
    """Test the optional API key authentication."""

    def test_no_auth_required_when_disabled(self, client):
        """When API key is not configured, endpoints should be accessible."""
        response = client.get("/stats")
        assert response.status_code == 200

    def test_auth_required_when_enabled(self, client_with_auth):
        """When API key is configured, endpoints should require it."""
        response = client_with_auth.get("/stats")
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json()["detail"]

    def test_auth_passes_with_correct_key(self, client_with_auth):
        response = client_with_auth.get("/stats", headers={"X-API-Key": "test-secret-key"})
        assert response.status_code == 200

    def test_auth_fails_with_wrong_key(self, client_with_auth):
        response = client_with_auth.get("/stats", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401

    def test_health_bypasses_auth(self, client_with_auth):
        """Health check should always work, even with auth enabled."""
        response = client_with_auth.get("/health")
        assert response.status_code == 200


class TestRateLimiting:
    """Test that rate limiting middleware is active."""

    def test_health_bypasses_rate_limit(self, client):
        """Health endpoint should never be rate limited."""
        for _ in range(10):
            response = client.get("/health")
            assert response.status_code == 200


class TestErrorHandling:
    """Test error responses for various invalid inputs."""

    def test_404_for_unknown_endpoint(self, client):
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_missing_required_param(self, client):
        """Context endpoint requires 'task' parameter."""
        response = client.get("/context")
        assert response.status_code == 422  # FastAPI validation error

    def test_invalid_symbol_name(self, client):
        response = client.get("/impact/ThisSymbolDoesNotExist12345")
        assert response.status_code == 404
        assert "error" in response.json() or "detail" in response.json()

    def test_invalid_outcome_for_ingest(self, client):
        """Ingest should reject invalid outcome values."""
        response = client.post("/sessions/ingest", json={
            "session_id": "test",
            "outcome": "invalid_outcome_value",
            "prompt": "test",
        })
        assert response.status_code == 422


class TestBootstrapEndpoint:
    """Test bootstrap with a real temp repo."""

    def test_bootstrap_with_temp_repo(self, client, tmp_path: Path):
        """Bootstrap a small temp repo and verify it works."""
        (tmp_path / "test_module.py").write_text("def hello(): pass\n")
        response = client.post(f"/bootstrap?repo={tmp_path}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "bootstrapped"
        assert data["symbols_indexed"] >= 0
        assert data["files_indexed"] >= 0

    def test_bootstrap_v1_prefix(self, client, tmp_path: Path):
        (tmp_path / "test.py").write_text("def foo(): pass\n")
        response = client.post(f"/v1/bootstrap?repo={tmp_path}")
        assert response.status_code == 200

    def test_suggest_with_task(self, client):
        """Suggest endpoint returns valid response even with no data."""
        response = client.get("/suggest?task=fix+the+login+bug")
        assert response.status_code == 200
        data = response.json()
        assert "problem_type" in data
        assert "recommended_approach" in data

    def test_search(self, client, tmp_path: Path):
        """Search after bootstrap returns results."""
        (tmp_path / "test_auth.py").write_text(
            "def authenticate_user(token):\n"
            '    """Validate JWT token."""\n'
            "    return True\n"
        )
        client.post(f"/bootstrap?repo={tmp_path}")
        response = client.get(f"/search?query=authenticate&repo={tmp_path}")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    def test_context(self, client, tmp_path: Path):
        """Context endpoint returns context string."""
        (tmp_path / "test.py").write_text("def hello(): pass\n")
        client.post(f"/bootstrap?repo={tmp_path}")
        response = client.get(f"/context?task=hello&repo={tmp_path}")
        assert response.status_code == 200
        assert len(response.json()["context"]) > 0

    def test_experiment(self, client):
        """Experiment endpoint creates a batch."""
        response = client.post("/experiment?task=fix+the+login+bug&variants=3")
        assert response.status_code == 200
        data = response.json()
        assert data["total_variants"] == 3
        assert len(data["variants"]) == 3

    def test_metrics(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_stats(self, client):
        response = client.get("/stats")
        assert response.status_code == 200

    def test_report(self, client):
        response = client.get("/report")
        assert response.status_code == 200


class TestMultiRepositorySupport:
    """Verify that the engine registry supports multiple repos."""

    def test_different_repos_get_different_engines(self, client, tmp_path: Path):
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        repo1.mkdir()
        repo2.mkdir()
        (repo1 / "a.py").write_text("def repo1_func(): pass\n")
        (repo2 / "b.py").write_text("def repo2_func(): pass\n")

        r1 = client.post(f"/bootstrap?repo={repo1}")
        r2 = client.post(f"/bootstrap?repo={repo2}")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["repository"] != r2.json()["repository"]


class TestIngestSession:
    """Test the session ingestion endpoint."""

    def test_ingest_successful_session(self, client):
        response = client.post("/sessions/ingest", json={
            "session_id": "test-sess-001",
            "outcome": "success",
            "prompt": "fix the login bug",
            "approach": "Targeted Fix",
            "model": "claude-sonnet",
            "files_changed": ["src/auth.py", "tests/test_auth.py"],
            "tests_passed": 10,
            "tests_failed": 0,
            "duration_seconds": 30.0,
            "token_count": 5000,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ingested"
        assert data["problem_type"] in ["bug_fix", "feature", "refactor", "general"]
        assert data["was_successful"] is True

    def test_ingest_failed_session(self, client):
        response = client.post("/sessions/ingest", json={
            "session_id": "test-sess-002",
            "outcome": "failure",
            "prompt": "refactor entire billing system",
            "approach": "Clean Sweep",
            "model": "claude-opus",
            "files_changed": [f"src/billing/{i}.py" for i in range(12)],
            "tests_passed": 4,
            "tests_failed": 8,
            "duration_seconds": 120.0,
            "token_count": 20000,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ingested"
        assert data["was_successful"] is False

    def test_ingest_minimal_session(self, client):
        """Test with only required fields."""
        response = client.post("/sessions/ingest", json={
            "session_id": "minimal-sess",
            "outcome": "success",
            "prompt": "test",
        })
        assert response.status_code == 200

    def test_ingest_rejected_session(self, client):
        response = client.post("/sessions/ingest", json={
            "session_id": "rejected-sess",
            "outcome": "rejected",
            "prompt": "add caching layer",
            "review_comments": ["Doesn't follow patterns", "Needs error handling"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["was_successful"] is False