"""Kiểm tra số liệu trong báo cáo có thật sự nằm trong dữ liệu truy vấn không.

Đây là kiểm tra xác định (không dùng LLM), nên kết quả lặp lại được và không tốn tiền.
Giới hạn: chỉ bắt được số không có trong dữ liệu gốc. Số được LLM tính toán
(ví dụ tỷ lệ phần trăm) sẽ bị báo là chưa kiểm chứng, và người duyệt cần xem lại.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)*(?![\w])")

# Bỏ qua các số nhỏ và năm, vì chúng xuất hiện trong câu chữ mà không phải số liệu
IGNORE_BELOW = 10.0
YEAR_RANGE = (2000, 2030)
REL_TOLERANCE = 0.005  # 0,5%


def parse_number(token: str) -> float:
    """Chuyển chuỗi số sang float, hiểu cả kiểu 1.234,56 (VN) lẫn 1,234.56 (EN)."""
    sign = -1.0 if token.startswith("-") else 1.0
    s = token.lstrip("-")

    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        # Dấu xuất hiện sau cùng là dấu thập phân, dấu còn lại là phân cách nghìn
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        parts = s.split(sep)
        if len(parts) > 2 or len(parts[-1]) == 3:
            s = s.replace(sep, "")  # phân cách nghìn
        else:
            s = s.replace(sep, ".")  # thập phân

    return sign * float(s)


def extract_numbers(text: str) -> list[float]:
    return [parse_number(m.group()) for m in NUMBER_RE.finditer(text)]


def data_values(results: Iterable[list[list]]) -> list[float]:
    """Gom tất cả giá trị số trong các bảng kết quả."""
    values: list[float] = []
    for rows in results:
        for row in rows:
            for cell in row:
                if isinstance(cell, bool):
                    continue
                if isinstance(cell, (int, float)):
                    values.append(float(cell))
    return values


def _matches(value: float, pool: list[float]) -> bool:
    for d in pool:
        if abs(value - d) <= max(0.01, REL_TOLERANCE * abs(d)):
            return True
    return False


def unsupported_numbers(text: str, pool: list[float]) -> list[str]:
    """Trả về các số trong văn bản không tìm thấy trong dữ liệu."""
    issues: list[str] = []
    for token in NUMBER_RE.findall(text):
        value = parse_number(token)
        if abs(value) < IGNORE_BELOW:
            continue
        if YEAR_RANGE[0] <= value <= YEAR_RANGE[1] and value.is_integer():
            continue
        if not _matches(value, pool) and not _matches(abs(value), pool):
            issues.append(token)
    return issues
