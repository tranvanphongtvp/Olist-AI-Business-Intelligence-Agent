"""Kiểm tra SQL do LLM sinh ra trước khi chạy.

Lớp này là tầng thứ hai. Tầng thứ nhất là tài khoản agent_ro chỉ đọc ở DB.
Kể cả khi lớp này bỏ sót, DB vẫn từ chối ghi.

Các quy tắc:
- Đúng một câu lệnh, và phải là SELECT (hoặc UNION của các SELECT).
- Không có câu lệnh ghi, sửa cấu trúc hay điều khiển transaction.
- Mọi bảng phải nằm trong schema analytics, hoặc là CTE trong chính câu lệnh.
- Không gọi các hàm nguy hiểm (ví dụ pg_sleep, đọc file trên server).
- Kết quả luôn bị giới hạn số dòng.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

ALLOWED_SCHEMA = "analytics"
MAX_ROWS = 500

FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Transaction,
    exp.Commit,
)

FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "dblink",
}


class UnsafeSQLError(ValueError):
    """SQL không đạt yêu cầu an toàn. Thông báo lỗi được gửi lại cho LLM để sửa."""


def validate(sql: str) -> str:
    """Kiểm tra SQL và trả về câu lệnh đã được giới hạn số dòng.

    Ném UnsafeSQLError nếu SQL không an toàn hoặc không hợp lệ.
    """
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as err:
        raise UnsafeSQLError(f"SQL không hợp lệ: {err}") from err

    if len(statements) != 1:
        raise UnsafeSQLError("Chỉ được chạy đúng một câu lệnh.")

    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise UnsafeSQLError("Chỉ cho phép câu lệnh SELECT.")

    if next(tree.find_all(*FORBIDDEN_NODES), None) is not None:
        raise UnsafeSQLError("Câu lệnh chứa thao tác không được phép (ghi, sửa, xóa hoặc đổi cấu trúc).")

    cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not table.db and table.name in cte_names:
            continue
        if table.db != ALLOWED_SCHEMA:
            name = f"{table.db}.{table.name}" if table.db else table.name
            raise UnsafeSQLError(
                f"Bảng '{name}' không được phép. Chỉ truy vấn schema {ALLOWED_SCHEMA} "
                f"với tên đầy đủ, ví dụ {ALLOWED_SCHEMA}.v_order_items_delivered."
            )

    for func in tree.find_all(exp.Func):
        name = (func.name or "").lower()
        if name in FORBIDDEN_FUNCTIONS:
            raise UnsafeSQLError(f"Hàm '{name}' không được phép.")

    body = tree.sql(dialect="postgres")
    return f"SELECT * FROM ({body}) AS limited_result LIMIT {MAX_ROWS}"
