"""Điều phối các lần chạy agent và lưu trạng thái vào DB.

Mỗi lần chạy có một run_id. Đồ thị LangGraph lưu checkpoint trong Postgres
(schema checkpoints), nên khi người duyệt trả lời sau vài giờ, API vẫn tiếp tục
đúng chỗ kể cả khi đã khởi động lại.

Kết nối được dùng chung giữa các request nên có khóa (lock) để tránh tranh chấp.
Với lưu lượng hiện tại (vài báo cáo mỗi ngày) đây là lựa chọn đơn giản và đủ dùng.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from agent.config import get_settings
from agent.graph import build_graph
from api.config import get_api_settings


class RunNotFoundError(LookupError):
    pass


class RunStateError(RuntimeError):
    """Hành động không hợp lệ với trạng thái hiện tại của run, ví dụ duyệt khi chưa chờ duyệt."""


class RunService:
    def __init__(self) -> None:
        s = get_settings()
        a = get_api_settings()
        self._conn = psycopg.connect(
            host=s.pg_host,
            port=s.pg_port,
            dbname=s.pg_db,
            user=a.writer_user,
            password=a.writer_password,
            autocommit=True,
            row_factory=dict_row,
            client_encoding="utf8",
        )
        self._saver = PostgresSaver(self._conn)
        self._saver.setup()
        self._graph = build_graph(checkpointer=self._saver)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._conn.close()

    # --- Các thao tác chính ---

    def start(self, question: str) -> dict[str, Any]:
        run_id = uuid.uuid4()
        self._insert(run_id, question)
        config = {"configurable": {"thread_id": str(run_id)}}
        try:
            with self._lock:
                result = self._graph.invoke({"question": question}, config)
        except Exception as err:
            self._update(run_id, status="failed", error=str(err))
            raise

        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            self._update(
                run_id,
                status="awaiting_review",
                findings=payload["findings"],
                warnings=payload["warnings"],
            )
        else:
            self._update(run_id, status="failed", error="Đồ thị kết thúc mà không chờ duyệt.")
        return self.get(run_id)

    def decide(self, run_id: uuid.UUID, decision: str) -> dict[str, Any]:
        run = self.get(run_id)
        if run is None:
            raise RunNotFoundError(str(run_id))
        if run["status"] != "awaiting_review":
            raise RunStateError(f"Run đang ở trạng thái '{run['status']}', không thể duyệt.")

        config = {"configurable": {"thread_id": str(run_id)}}
        with self._lock:
            result = self._graph.invoke(Command(resume=decision), config)

        if result.get("approved"):
            self._update(run_id, status="approved", report=result.get("report"))
        else:
            self._update(run_id, status="rejected")
        return self.get(run_id)

    def get(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text, question, status, findings, warnings,
                       report, error, created_at
                FROM reports.runs
                WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        row["created_at"] = row["created_at"].isoformat()
        return row

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id::text, question, status, created_at
                FROM reports.runs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        for row in rows:
            row["created_at"] = row["created_at"].isoformat()
        return rows

    # --- Ghi DB ---

    def _insert(self, run_id: uuid.UUID, question: str) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reports.runs (run_id, question, status) VALUES (%s, %s, 'running')",
                (run_id, question),
            )

    def _update(self, run_id: uuid.UUID, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values())
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                f"UPDATE reports.runs SET {assignments}, updated_at = now() WHERE run_id = %s",
                [*values, run_id],
            )
