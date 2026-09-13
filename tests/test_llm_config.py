"""Tests for safe LLM configuration API, secret non-leakage, and deterministic fallback."""

import unittest
from fastapi.testclient import TestClient

from backend.config import get_settings, reset_llm_settings, update_llm_settings
from backend.main import app

client = TestClient(app)


class LLMConfigApiTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_llm_settings()

    def tearDown(self) -> None:
        reset_llm_settings()

    def test_missing_credentials_returns_safe_unconfigured_status(self) -> None:
        res = client.get("/api/llm/config")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["is_configured"])
        self.assertFalse(data["has_api_key"])
        self.assertEqual(data["connection_status"], "not_configured")
        self.assertNotIn("api_key", data)
        self.assertNotIn("llm_api_key", data)

    def test_valid_configuration_submission_hides_secret(self) -> None:
        payload = {
            "provider": "ollama",
            "api_key": "super-secret-key-12345",
            "model": "llama3.1",
            "base_url": "http://localhost:11434/v1",
            "test_connection": False,
        }
        res = client.post("/api/llm/config", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["is_configured"])
        self.assertTrue(data["has_api_key"])
        self.assertEqual(data["provider"], "ollama")
        self.assertEqual(data["model"], "llama3.1")
        # Ensure secret is NEVER present anywhere in response body
        self.assertNotIn("super-secret-key-12345", res.text)
        self.assertNotIn("api_key", data)

        # GET /api/llm/config must also NEVER leak secret
        get_res = client.get("/api/llm/config")
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        self.assertTrue(get_data["is_configured"])
        self.assertTrue(get_data["has_api_key"])
        self.assertNotIn("super-secret-key-12345", get_res.text)

    def test_invalid_configuration_returns_safe_error_without_secret(self) -> None:
        payload = {
            "provider": "groq",
            "api_key": "invalid-groq-key-xyz",
            "model": "llama-3.3-70b-versatile",
            "base_url": "http://127.0.0.1:9999/v1",  # Unreachable host
            "test_connection": True,
        }
        res = client.post("/api/llm/config", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["connection_status"], "error")
        self.assertIn("Could not connect", data["status_message"] or "")
        self.assertNotIn("invalid-groq-key-xyz", res.text)

    def test_secret_never_in_health_check_or_timeline_events(self) -> None:
        update_llm_settings(
            provider="ollama",
            api_key="my-super-secret-passphrase",
            model="llama3.1",
        )
        health_res = client.get("/api/health")
        self.assertEqual(health_res.status_code, 200)
        self.assertNotIn("my-super-secret-passphrase", health_res.text)

        # Start a run and inspect timeline events
        run_payload = {
            "goal": "Revenue dropped significantly today. Investigate why.",
            "scenario": "inventory_supplier_failure",
            "step_delay_seconds": 0.0,
        }
        run_res = client.post("/api/runs", json=run_payload)
        self.assertEqual(run_res.status_code, 200)
        run_id = run_res.json()["run_id"]

        events_res = client.get(f"/api/runs/{run_id}/events")
        self.assertEqual(events_res.status_code, 200)
        self.assertNotIn("my-super-secret-passphrase", events_res.text)

    def test_deterministic_fallback_continues_working_when_unconfigured(self) -> None:
        reset_llm_settings()
        payload = {
            "goal": "Checkout error rate spiked after release DEP-502. Investigate why.",
            "scenario": "deployment_service_failure",
            "step_delay_seconds": 0.0,
        }
        res = client.post("/api/runs", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["status"], ["completed", "awaiting_approval"])


    def test_clear_llm_config_resets_to_deterministic_mode(self) -> None:
        update_llm_settings(provider="ollama", api_key="test-key", model="llama3.1")
        self.assertTrue(get_settings().llm_is_configured)

        del_res = client.delete("/api/llm/config")
        self.assertEqual(del_res.status_code, 200)
        del_data = del_res.json()
        self.assertFalse(del_data["is_configured"])
        self.assertFalse(del_data["has_api_key"])
        self.assertFalse(get_settings().llm_is_configured)


if __name__ == "__main__":
    unittest.main()
