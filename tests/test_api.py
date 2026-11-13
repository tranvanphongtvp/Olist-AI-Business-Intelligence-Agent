"""Kiểm tra API end-to-end với Postgres thật và LLM giả.

Cần Postgres đã có schema, view, và tài khoản reporter. Test tự bỏ qua nếu thiếu cấu hình.
"""

import os
import unittest
import uuid
from unittest import mock

from fastapi.testclient import TestClient

from tests.test_graph_offline import FakeLLM

REQUIRED = ["POSTGRES_DB", "AGENT_DB_USER", "AGENT_DB_PASSWORD", "WRITER_DB_USER", "WRITER_DB_PASSWORD"]
API_KEY = "test-api-key"
SQL = "SELECT round(sum(price), 2) AS revenue FROM analytics.v_order_items_delivered"


@unittest.skipUnless(all(os.getenv(k) for k in REQUIRED), "cần cấu hình Postgres để chạy test này")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENAI_API_KEY", "test-key")
        os.environ.setdefault("OPENAI_MODEL", "test-model")
        os.environ["API_KEY"] = API_KEY
        from agent.config import get_settings
        from api.config import get_api_settings

        get_settings.cache_clear()
        get_api_settings.cache_clear()

        from api import main

        cls.fake = FakeLLM(SQL, "Doanh thu đã giao là 13.221.498,11.")
        cls.patch = mock.patch("agent.nodes.get_llm", return_value=cls.fake)
        cls.patch.start()
        cls.client_ctx = TestClient(main.app)
        cls.client = cls.client_ctx.__enter__()
        cls.headers = {"X-API-Key": API_KEY}

    @classmethod
    def tearDownClass(cls):
        cls.client_ctx.__exit__(None, None, None)
        cls.patch.stop()

    def test_health_is_public(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_requests_without_key_are_rejected(self):
        r = self.client.post("/runs", json={"question": "Doanh thu là bao nhiêu?"})
        self.assertEqual(r.status_code, 401)

    def test_wrong_key_is_rejected(self):
        r = self.client.post(
            "/runs", json={"question": "Doanh thu là bao nhiêu?"}, headers={"X-API-Key": "sai"}
        )
        self.assertEqual(r.status_code, 401)

    def test_approve_flow(self):
        r = self.client.post("/runs", json={"question": "Doanh thu đã giao là bao nhiêu?"}, headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        run = r.json()
        self.assertEqual(run["status"], "awaiting_review")
        self.assertIn("13.221.498,11", run["findings"])
        self.assertEqual(run["warnings"], [])

        r = self.client.post(
            f"/runs/{run['run_id']}/decision", json={"decision": "approve"}, headers=self.headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        done = r.json()
        self.assertEqual(done["status"], "approved")
        self.assertTrue(done["report"])

        r = self.client.get(f"/runs/{run['run_id']}", headers=self.headers)
        self.assertEqual(r.json()["status"], "approved")

    def test_reject_flow(self):
        r = self.client.post("/runs", json={"question": "Doanh thu đã giao là bao nhiêu?"}, headers=self.headers)
        run_id = r.json()["run_id"]
        r = self.client.post(f"/runs/{run_id}/decision", json={"decision": "reject"}, headers=self.headers)
        self.assertEqual(r.json()["status"], "rejected")
        self.assertIsNone(r.json()["report"])

    def test_cannot_decide_twice(self):
        r = self.client.post("/runs", json={"question": "Doanh thu đã giao là bao nhiêu?"}, headers=self.headers)
        run_id = r.json()["run_id"]
        self.client.post(f"/runs/{run_id}/decision", json={"decision": "approve"}, headers=self.headers)
        r = self.client.post(f"/runs/{run_id}/decision", json={"decision": "approve"}, headers=self.headers)
        self.assertEqual(r.status_code, 409)

    def test_unknown_run_returns_404(self):
        r = self.client.get(f"/runs/{uuid.uuid4()}", headers=self.headers)
        self.assertEqual(r.status_code, 404)
        r = self.client.get("/runs/khong-phai-uuid", headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_question_length_is_validated(self):
        r = self.client.post("/runs", json={"question": "ab"}, headers=self.headers)
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
