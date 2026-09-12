"""API integration tests for Execution Timeline API (Stage 8)."""

import unittest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class APIRouteTests(unittest.TestCase):
    def test_health_check_returns_200(self) -> None:
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("llm_configured", data)

    def test_list_scenarios_returns_scenarios(self) -> None:
        response = client.get("/api/scenarios")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 4)
        keys = [s["key"] for s in data]
        self.assertIn("inventory_supplier_failure", keys)

    def test_start_run_and_retrieve_state_and_events(self) -> None:
        payload = {
            "goal": "Revenue dropped significantly today. Investigate why.",
            "scenario": "inventory_supplier_failure",
            "step_delay_seconds": 0.0,
        }
        start_res = client.post("/api/runs", json=payload)
        self.assertEqual(start_res.status_code, 200)
        state_data = start_res.json()
        run_id = state_data["run_id"]
        self.assertIsNotNone(run_id)
        self.assertEqual(state_data["status"], "completed")

        # GET /api/runs/{run_id}
        get_res = client.get(f"/api/runs/{run_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["run_id"], run_id)

        # GET /api/runs/{run_id}/events
        events_res = client.get(f"/api/runs/{run_id}/events")
        self.assertEqual(events_res.status_code, 200)
        events = events_res.json()
        self.assertGreater(len(events), 0)

    def test_async_live_run_polling_flow(self) -> None:
        payload = {
            "goal": "Revenue dropped significantly today. Investigate why.",
            "scenario": "inventory_supplier_failure",
            "step_delay_seconds": 0.05,
        }
        start_res = client.post("/api/runs", json=payload)
        self.assertEqual(start_res.status_code, 200)
        state_data = start_res.json()
        run_id = state_data["run_id"]
        self.assertIn(state_data["status"], ["running", "completed"])

        # Poll until completed or awaiting approval
        import time
        for _ in range(50):
            res = client.get(f"/api/runs/{run_id}")
            if res.json()["status"] in ["completed", "awaiting_approval", "failed"]:
                break
            time.sleep(0.05)

        get_res = client.get(f"/api/runs/{run_id}")
        self.assertIn(get_res.json()["status"], ["completed", "awaiting_approval", "failed"])

    def test_high_risk_approval_flow_via_api(self) -> None:
        # Create a run with low threshold to force approval on purchase request
        payload = {
            "goal": "Revenue dropped significantly today. Investigate why.",
            "scenario": "inventory_supplier_failure",
            "approval_threshold_inr": "1",  # Every purchase request requires approval
            "step_delay_seconds": 0.0,
        }
        start_res = client.post("/api/runs", json=payload)
        self.assertEqual(start_res.status_code, 200)
        state_data = start_res.json()
        run_id = state_data["run_id"]
        
        if state_data["status"] == "awaiting_approval":
            appr_res = client.post(f"/api/runs/{run_id}/approval", json={"approved": True, "step_delay_seconds": 0.0})
            self.assertEqual(appr_res.status_code, 200)
            res_data = appr_res.json()
            self.assertEqual(res_data["status"], "completed")

    def test_unknown_scenario_returns_400(self) -> None:
        res = client.post("/api/runs", json={"goal": "Test goal", "scenario": "non_existent"})
        self.assertEqual(res.status_code, 400)

    def test_unknown_run_returns_404(self) -> None:
        res = client.get("/api/runs/non-existent-id")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
