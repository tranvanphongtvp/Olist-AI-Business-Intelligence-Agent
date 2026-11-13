"""Các node của đồ thị agent.

Luồng:
    load_schema -> plan_sql -> execute_sql -(lỗi, còn lượt)-> plan_sql
                                    |
                                    v
    analyze -> verify -(số không khớp, còn lượt)-> analyze
                  |
                  v
    human_review -(từ chối)-> END
                  |
                  v
    report -> END
"""

from __future__ import annotations

import json
from typing import Any, Literal

import psycopg
from langgraph.graph import END
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agent import verify
from agent.db import describe_schema, run_query
from agent.llm import get_llm
from agent.sql_guard import UnsafeSQLError
from agent.state import AgentState, QueryRecord

MAX_SQL_ATTEMPTS = 2
MAX_VERIFY_ATTEMPTS = 1
ROWS_FOR_LLM = 50  # giới hạn số dòng đưa vào prompt để tiết kiệm token


class SQLItem(BaseModel):
    purpose: str = Field(description="Mục đích truy vấn, viết bằng tiếng Việt")
    sql: str = Field(description="Một câu SELECT dùng tên đầy đủ schema analytics")


class SQLPlan(BaseModel):
    queries: list[SQLItem] = Field(min_length=1, max_length=5)


PLANNER_SYSTEM = """Bạn là chuyên gia SQL PostgreSQL cho dữ liệu bán hàng Olist.
Quy tắc bắt buộc:
- Chỉ viết câu SELECT. Không được viết INSERT, UPDATE, DELETE, DROP hay bất kỳ lệnh sửa dữ liệu nào.
- Chỉ truy vấn schema analytics, dùng tên đầy đủ, ví dụ analytics.v_order_items_delivered.
- Doanh thu = tổng cột price của analytics.v_order_items_delivered (không gồm phí ship).
- Đếm khách bằng customer_unique_id, không dùng customer_id.
- Với so sánh theo thời gian, dùng cột sales_month.

Các view có sẵn:
{schema}
"""

ANALYST_SYSTEM = """Bạn là nhà phân tích dữ liệu bán hàng.
Chỉ dùng số liệu có trong dữ liệu được cung cấp. Không tự bịa số.
Viết phân tích bằng tiếng Việt, ngắn gọn, nêu rõ xu hướng và điểm bất thường.
Nếu dữ liệu không đủ để trả lời, hãy nói rõ điều đó."""

REPORT_SYSTEM = """Bạn viết báo cáo kinh doanh bằng tiếng Việt, định dạng Markdown.
Chỉ dùng các số đã có trong phần phân tích. Không thêm số mới.
Nếu có cảnh báo kiểm chứng, ghi chú rõ ở cuối báo cáo."""


def _llm_data(results: list[QueryRecord]) -> str:
    """Rút gọn kết quả thành JSON để đưa vào prompt."""
    payload = []
    for r in results:
        payload.append(
            {
                "purpose": r["purpose"],
                "columns": r["columns"],
                "rows": r["rows"][:ROWS_FOR_LLM],
                "error": r["error"],
            }
        )
    return json.dumps(payload, ensure_ascii=False, default=str)


def load_schema(state: AgentState) -> dict[str, Any]:
    return {"schema_text": describe_schema()}


def plan_sql(state: AgentState) -> dict[str, Any]:
    # function_calling: được cả OpenAI và Groq hỗ trợ.
    # Không dùng json_schema vì Groq chưa được kiểm chứng với kiểu này.
    llm = get_llm().with_structured_output(SQLPlan, method="function_calling")
    prompt = [
        ("system", PLANNER_SYSTEM.format(schema=state["schema_text"])),
        ("human", state["question"]),
    ]
    if state.get("errors"):
        prompt.append(
            (
                "human",
                "Lần trước có lỗi, hãy sửa và viết lại:\n" + "\n".join(state["errors"]),
            )
        )
    plan: SQLPlan = llm.invoke(prompt)
    return {
        "planned": [item.model_dump() for item in plan.queries],
        "sql_attempts": state.get("sql_attempts", 0) + 1,
    }


def execute_sql(state: AgentState) -> dict[str, Any]:
    results: list[QueryRecord] = []
    errors: list[str] = []
    for item in state["planned"]:
        try:
            res = run_query(item["sql"])
            results.append(
                {
                    "purpose": item["purpose"],
                    "sql": item["sql"],
                    "columns": res.columns,
                    "rows": res.rows,
                    "error": None,
                }
            )
        except (UnsafeSQLError, psycopg.Error) as err:
            message = str(err).strip()
            results.append(
                {
                    "purpose": item["purpose"],
                    "sql": item["sql"],
                    "columns": [],
                    "rows": [],
                    "error": message,
                }
            )
            errors.append(f"[{item['purpose']}] {message}\nSQL: {item['sql']}")
    return {"results": results, "errors": errors}


def route_after_execute(state: AgentState) -> Literal["plan_sql", "analyze"]:
    if state.get("errors") and state.get("sql_attempts", 0) < MAX_SQL_ATTEMPTS:
        return "plan_sql"
    return "analyze"


def analyze(state: AgentState) -> dict[str, Any]:
    llm = get_llm()
    prompt = [
        ("system", ANALYST_SYSTEM),
        (
            "human",
            f"Câu hỏi: {state['question']}\n\nDữ liệu:\n{_llm_data(state['results'])}",
        ),
    ]
    if state.get("verification_warnings"):
        prompt.append(
            (
                "human",
                "Các số sau không tìm thấy trong dữ liệu, hãy sửa hoặc bỏ đi: "
                + ", ".join(state["verification_warnings"]),
            )
        )
    response = llm.invoke(prompt)
    return {"findings": str(response.content)}


def verify_findings(state: AgentState) -> dict[str, Any]:
    pool = verify.data_values([r["rows"] for r in state["results"] if not r["error"]])
    warnings = verify.unsupported_numbers(state["findings"], pool)
    return {
        "verification_warnings": warnings,
        "verify_attempts": state.get("verify_attempts", 0) + 1,
    }


def route_after_verify(state: AgentState) -> Literal["analyze", "human_review"]:
    if state.get("verification_warnings") and state.get("verify_attempts", 0) <= MAX_VERIFY_ATTEMPTS:
        return "analyze"
    return "human_review"


def human_review(state: AgentState) -> dict[str, Any]:
    """Tạm dừng đồ thị và chờ người duyệt. Giá trị resume là 'approve' hoặc 'reject'."""
    decision = interrupt(
        {
            "question": "Duyệt báo cáo này? Trả lời 'approve' hoặc 'reject'.",
            "findings": state["findings"],
            "warnings": state.get("verification_warnings", []),
        }
    )
    return {"approved": str(decision).strip().lower() == "approve"}


def route_after_review(state: AgentState) -> Literal["report", "__end__"]:
    return "report" if state.get("approved") else END


def report(state: AgentState) -> dict[str, Any]:
    llm = get_llm()
    warnings = state.get("verification_warnings") or []
    note = (
        "Lưu ý: các số sau chưa được kiểm chứng trong dữ liệu: " + ", ".join(warnings)
        if warnings
        else "Tất cả số liệu đã được kiểm chứng trong dữ liệu truy vấn."
    )
    response = llm.invoke(
        [
            ("system", REPORT_SYSTEM),
            ("human", f"Câu hỏi: {state['question']}\n\nPhân tích:\n{state['findings']}\n\n{note}"),
        ]
    )
    return {"report": str(response.content)}
