"""
test_api_routes.py
==================
HTTP route-level tests for the SimuVerse FastAPI backend.

Uses Starlette's TestClient to drive requests against the real ASGI application
without starting a network server.  All simulation behaviour comes from the
real SimModel — no mocking.

Tests
-----
  TestHealth           – GET /api/health returns 200 with status=ok
  TestCreateRun        – POST /api/runs happy path and validation errors
  TestGetRunStatus     – GET /api/runs/{run_id} fields and 404
  TestStepRun          – step endpoint returns diff with correct tick
  TestRunLifecycle     – start, pause, stop, delete on a live run
  TestInterventionRoute – intervention types list and apply endpoint

Run from the backend directory:
    source .venv/bin/activate
    pytest tests/test_api_routes.py -v
"""

from __future__ import annotations

import os
import warnings

import pytest
from starlette.testclient import TestClient

warnings.filterwarnings("ignore")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from app.main import app  # noqa: E402  (imports after env setup)


# ── Shared test client ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Starlette TestClient wired to the real FastAPI ASGI app.

    Module-scoped so the singleton RunRegistry is shared across tests in this
    file — created runs stay accessible between test methods.
    """
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_run(client: httpx.Client, environment: str = "office",
                goal: str = "complete_proposal",
                team_type: str = "smooth") -> str:
    """Create a run and return its run_id.  Fails the test if the request fails."""
    resp = client.post("/api/runs", json={
        "environment": environment,
        "goal": goal,
        "team_type": team_type,
        "save_history": False,
    })
    assert resp.status_code == 200, f"create_run failed: {resp.text}"
    data = resp.json()
    assert "run_id" in data
    return data["run_id"]


# ── 1. Health check ───────────────────────────────────────────────────────────

class TestHealth:

    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_body_has_status_ok(self, client):
        resp = client.get("/api/health")
        body = resp.json()
        assert body.get("status") == "ok"

    def test_health_body_has_version(self, client):
        resp = client.get("/api/health")
        body = resp.json()
        assert "version" in body


# ── 2. POST /api/runs ─────────────────────────────────────────────────────────

class TestCreateRun:

    def test_create_run_returns_200(self, client):
        resp = client.post("/api/runs", json={
            "environment": "office",
            "goal": "complete_proposal",
            "team_type": "smooth",
            "save_history": False,
        })
        assert resp.status_code == 200

    def test_create_run_returns_run_id(self, client):
        resp = client.post("/api/runs", json={
            "environment": "cafe",
            "goal": "choose_restaurant",
            "team_type": "balanced",
            "save_history": False,
        })
        data = resp.json()
        assert "run_id" in data
        assert isinstance(data["run_id"], str)
        assert len(data["run_id"]) > 0

    def test_create_run_returns_seed(self, client):
        resp = client.post("/api/runs", json={
            "environment": "office",
            "goal": "complete_proposal",
            "team_type": "tension",
            "save_history": False,
        })
        data = resp.json()
        assert "seed" in data
        assert isinstance(data["seed"], int)

    def test_create_run_escape_scenario(self, client):
        resp = client.post("/api/runs", json={
            "environment": "escape",
            "goal": "solve_puzzle",
            "team_type": "pressure",
            "save_history": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data

    def test_create_run_seeded_is_deterministic(self, client):
        """Same seed must produce the same run_id prefix (scenario/team wired correctly)."""
        body = {"environment": "office", "goal": "complete_proposal",
                "team_type": "smooth", "seed": 42, "save_history": False}
        a = client.post("/api/runs", json=body).json()
        b = client.post("/api/runs", json=body).json()
        # run_ids are random UUIDs so they differ, but config must match
        assert a["scenario_id"] == b["scenario_id"]
        assert a["resolved_team_type"] == b["resolved_team_type"]

    def test_create_run_invalid_environment_returns_400(self, client):
        resp = client.post("/api/runs", json={
            "environment": "NONEXISTENT_ENVIRONMENT_XYZ",
            "goal": "complete_proposal",
            "team_type": "smooth",
            "save_history": False,
        })
        assert resp.status_code == 400

    def test_create_run_invalid_team_type_returns_400(self, client):
        resp = client.post("/api/runs", json={
            "environment": "office",
            "goal": "complete_proposal",
            "team_type": "INVALID_TEAM_XYZ",
            "save_history": False,
        })
        assert resp.status_code == 400

    def test_create_run_missing_environment_returns_400(self, client):
        resp = client.post("/api/runs", json={"team_type": "smooth", "save_history": False})
        assert resp.status_code == 400


# ── 3. GET /api/runs/{run_id} ─────────────────────────────────────────────────

class TestGetRunStatus:

    def test_get_existing_run_returns_200(self, client):
        run_id = _create_run(client)
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200

    def test_get_run_body_has_required_fields(self, client):
        run_id = _create_run(client)
        data = client.get(f"/api/runs/{run_id}").json()
        for field in ("run_id", "status", "seed", "tick", "agents", "scenario"):
            assert field in data, f"Missing field: {field}"

    def test_get_run_tick_starts_at_zero(self, client):
        run_id = _create_run(client)
        data = client.get(f"/api/runs/{run_id}").json()
        assert data["tick"] == 0

    def test_get_nonexistent_run_returns_404(self, client):
        resp = client.get("/api/runs/definitely_not_a_real_run_id_00000")
        assert resp.status_code == 404


# ── 4. POST /api/runs/{run_id}/step ──────────────────────────────────────────

class TestStepRun:

    def test_step_returns_200(self, client):
        run_id = _create_run(client)
        resp = client.post(f"/api/runs/{run_id}/step")
        assert resp.status_code == 200

    def test_step_increments_tick(self, client):
        run_id = _create_run(client)
        data = client.post(f"/api/runs/{run_id}/step").json()
        assert data["tick"] == 1

    def test_step_returns_diff(self, client):
        run_id = _create_run(client)
        data = client.post(f"/api/runs/{run_id}/step").json()
        assert "diff" in data
        diff = data["diff"]
        assert "agents" in diff
        assert "events" in diff
        assert "metrics" in diff

    def test_step_advances_tick_on_each_call(self, client):
        run_id = _create_run(client)
        for expected_tick in range(1, 4):
            data = client.post(f"/api/runs/{run_id}/step").json()
            assert data["tick"] == expected_tick

    def test_step_nonexistent_run_returns_404(self, client):
        resp = client.post("/api/runs/definitely_not_a_real_run_id_00000/step")
        assert resp.status_code == 404


# ── 5. Run lifecycle: start / pause / stop / delete ──────────────────────────

class TestRunLifecycle:

    def test_start_run_returns_200(self, client):
        run_id = _create_run(client)
        resp = client.post(f"/api/runs/{run_id}/start")
        assert resp.status_code == 200

    def test_start_run_sets_status_running(self, client):
        run_id = _create_run(client)
        data = client.post(f"/api/runs/{run_id}/start").json()
        assert data["status"] == "running"

    def test_pause_run_sets_status_paused(self, client):
        run_id = _create_run(client)
        client.post(f"/api/runs/{run_id}/start")
        data = client.post(f"/api/runs/{run_id}/pause").json()
        assert data["status"] == "paused"

    def test_stop_run_sets_status_stopped(self, client):
        run_id = _create_run(client)
        data = client.post(f"/api/runs/{run_id}/stop").json()
        assert data["status"] == "stopped"

    def test_delete_run_returns_deleted_true(self, client):
        run_id = _create_run(client)
        data = client.delete(f"/api/runs/{run_id}").json()
        assert data.get("deleted") is True

    def test_deleted_run_returns_404_on_get(self, client):
        run_id = _create_run(client)
        client.delete(f"/api/runs/{run_id}")
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 404


# ── 6. Intervention route ────────────────────────────────────────────────────

class TestInterventionRoute:

    def test_intervention_types_endpoint_returns_200(self, client):
        resp = client.get("/api/interventions/types")
        assert resp.status_code == 200
        data = resp.json()
        assert "interventions" in data
        assert len(data["interventions"]) > 0

    def test_reveal_info_on_live_run_succeeds(self, client):
        run_id = _create_run(client, environment="office",
                             goal="complete_proposal", team_type="tension")
        # Step once so the model has a tick
        client.post(f"/api/runs/{run_id}/step")
        resp = client.post("/api/interventions/apply", json={
            "run_id": run_id,
            "type": "reveal_info",
            "params": {"agent_id": "A1", "item": "budget"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_intervention_on_nonexistent_run_returns_404(self, client):
        resp = client.post("/api/interventions/apply", json={
            "run_id": "not_a_real_run_id",
            "type": "reveal_info",
            "params": {"agent_id": "A1", "item": "budget"},
        })
        assert resp.status_code == 404
