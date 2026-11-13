"""Kiểm tra toàn bộ đồ thị bằng LLM giả, không gọi OpenAI.

Cần Postgres đang chạy với đúng dữ liệu đã nạp và view đã tạo. Test tự bỏ qua
nếu chưa cấu hình biến môi trường.
"""

import os
import unittest
import uuid
from unittest import mock

from langchain_core.messages import AIMessage
from langgraph.types import Command

from agent.nodes import SQLItem, SQLPlan

REQUIRED = ["POSTGRES_DB", "AGENT_DB_USER", "AGENT_DB_PASSWORD"]


class FakeLLM:
    """Giả lập ChatOpenAI cho cả hai kiểu gọi: có cấu trúc và văn bản thường."""

    def __init__(self, sql, findings):
        self.sql = sql
        self.findings = findings

    def with_structured_output(self, schema, **_kwargs):
        plan = SQLPlan(queries=[SQLItem(purpose="doanh thu", sql=self.sql)])
        return mock.Mock(invoke=lambda _prompt: plan)

    def invoke(self, _prompt):
        return AIMessage(content=self.findings)


@unittest.skipUnless(all(os.getenv(k) for k in REQUIRED), "cần cấu hình Postgres để chạy test này")
class GraphOfflineTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("OPENAI_API_KEY", "test-key")
        os.environ.setdefault("OPENAI_MODEL", "test-model")
        from agent.config import get_settings

        get_settings.cache_clear()

    def _run(self, findings, decision):
        from agent.graph import build_graph

        sql = "SELECT round(sum(price), 2) AS revenue FROM analytics.v_order_items_delivered"
        fake = FakeLLM(sql, findings)
        with mock.patch("agent.nodes.get_llm", return_value=fake):
            graph = build_graph()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            result = graph.invoke({"question": "Doanh thu đã giao là bao nhiêu?"}, config)
            self.assertIn("__interrupt__", result, "đồ thị phải tạm dừng chờ duyệt")
            payload = result["__interrupt__"][0].value
            self.assertIn("findings", payload)
            result = graph.invoke(Command(resume=decision), config)
        return result

    def test_approved_run_produces_report(self):
        result = self._run("Doanh thu đã giao là 13.221.498,11.", "approve")
        self.assertTrue(result["approved"])
        self.assertTrue(result["report"])
        self.assertEqual(result["verification_warnings"], [])

    def test_rejected_run_produces_no_report(self):
        result = self._run("Doanh thu đã giao là 13.221.498,11.", "reject")
        self.assertFalse(result["approved"])
        self.assertFalse(result.get("report"))

    def test_invented_number_triggers_warning_at_review(self):
        result = self._run("Doanh thu đã giao là 777.777.777.", "reject")
        self.assertTrue(result["verification_warnings"])


if __name__ == "__main__":
    unittest.main()
