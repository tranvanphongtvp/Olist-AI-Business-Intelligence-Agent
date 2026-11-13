"""State dùng chung giữa các node trong LangGraph."""

from __future__ import annotations

from typing import Any, TypedDict


class QueryRecord(TypedDict):
    purpose: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    error: str | None


class AgentState(TypedDict, total=False):
    question: str
    schema_text: str

    # Vòng lặp SQL
    planned: list[dict[str, str]]  # [{purpose, sql}] do LLM sinh ra
    results: list[QueryRecord]
    errors: list[str]
    sql_attempts: int

    # Phân tích và kiểm chứng
    findings: str
    verification_warnings: list[str]
    verify_attempts: int

    # Duyệt của người và báo cáo cuối
    approved: bool
    report: str
