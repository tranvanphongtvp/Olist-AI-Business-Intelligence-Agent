"""Tạo hoặc cập nhật các view trong schema analytics.

Chạy sau khi đã nạp raw:
    set -a; source .env; set +a
    PYTHONIOENCODING=utf-8 .venv/Scripts/python -m scripts.build_views

Chạy các file trong sql/views/ theo thứ tự tên file. Mỗi file chạy trong
một transaction. Các view dùng CREATE OR REPLACE nên chạy lại vẫn an toàn.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.load_raw import connect

VIEWS_DIR = Path(__file__).resolve().parent.parent / "sql" / "views"


def main() -> int:
    files = sorted(VIEWS_DIR.glob("*.sql"))
    if not files:
        print(f"Không tìm thấy file SQL nào trong {VIEWS_DIR}", file=sys.stderr)
        return 1

    with connect() as conn:
        for path in files:
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
            print(f"Đã chạy {path.name}")
    print("Tạo view analytics thành công.")
    return 0


if __name__ == "__main__":
    sys.exit(main())