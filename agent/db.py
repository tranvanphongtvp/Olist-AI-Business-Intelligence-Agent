"""Kết nối DB cho agent. Luôn dùng tài khoản agent_ro (chỉ đọc)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import psycopg

from agent.config import get_settings
from agent.sql_guard import validate


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]] = field(default_factory=list)


def _connect() -> psycopg.Connection:
    s = get_settings()
    return psycopg.connect(
        host=s.pg_host,
        port=s.pg_port,
        dbname=s.pg_db,
        user=s.agent_user,
        password=s.agent_password,
        client_encoding="utf8",
    )


def _jsonable(value: Any) -> Any:
    """Đổi kiểu không serialize được (Decimal, ngày giờ) sang kiểu đơn giản.

    LangGraph lưu state bằng serializer, nên dữ liệu trong state phải là kiểu cơ bản.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def run_query(sql: str) -> QueryResult:
    """Kiểm tra SQL rồi chạy. Ném UnsafeSQLError hoặc psycopg.Error nếu thất bại."""
    safe_sql = validate(sql)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(safe_sql)
        columns = [col.name for col in cur.description]
        rows = [[_jsonable(v) for v in row] for row in cur.fetchall()]
    return QueryResult(columns=columns, rows=rows)


def describe_schema() -> str:
    """Trả về mô tả các view trong analytics để đưa vào prompt cho LLM."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'analytics'
            ORDER BY table_name, ordinal_position
            """
        )
        lines: dict[str, list[str]] = {}
        for table, column, dtype in cur.fetchall():
            lines.setdefault(table, []).append(f"{column} ({dtype})")
    return "\n".join(
        f"analytics.{table}: " + ", ".join(cols) for table, cols in lines.items()
    )
