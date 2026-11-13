"""Nạp các file CSV đầu vào vào schema raw (lớp bronze).

Chạy sau khi Postgres đã khởi động (docker compose up -d):
    set -a; source .env; set +a
    .venv/bin/python -m scripts.load_raw

Toàn bộ việc nạp chạy trong MỘT transaction:
- TRUNCATE rồi COPY lại từng bảng, nên chạy nhiều lần vẫn cho kết quả giống nhau.
- Nếu bất kỳ bảng nào sai số dòng, transaction bị rollback và DB giữ nguyên trạng thái cũ.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

from scripts.data_io import EXPECTED_ROWS, RAW_DIR, SOURCES

CHUNK = 1024 * 1024  # 1 MB


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        # Chỉ định UTF8 để file SQL và CSV có tiếng Việt không bị lỗi encoding,
        # kể cả khi cluster được tạo với encoding khác.
        client_encoding="utf8",
    )


def copy_file(cur: psycopg.Cursor, table: str, path: Path) -> None:
    """Stream file CSV vào bảng theo từng khối để không nạp cả file vào RAM."""
    with cur.copy(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
        with path.open("rb") as f:
            while chunk := f.read(CHUNK):
                copy.write(chunk)


def check_files() -> list[str]:
    return [f for files in SOURCES.values() for f in files if not (RAW_DIR / f).exists()]


def main() -> int:
    missing = check_files()
    if missing:
        print(f"Thiếu file trong {RAW_DIR}: {missing}", file=sys.stderr)
        return 1

    try:
        with connect() as conn, conn.cursor() as cur:
            for name, files in SOURCES.items():
                table = f"raw.{name}"
                expected = EXPECTED_ROWS[name]

                cur.execute(f"TRUNCATE {table}")
                for filename in files:
                    copy_file(cur, table, RAW_DIR / filename)

                cur.execute(f"SELECT count(*) FROM {table}")
                (actual,) = cur.fetchone()
                status = "OK" if actual == expected else "LỆCH"
                print(f"{table:28s} {actual:>10,d} / kỳ vọng {expected:>10,d}  {status}")

                if actual != expected:
                    # Ném lỗi bên trong `with` để psycopg rollback toàn bộ
                    raise ValueError(f"{table}: {actual:,} dòng, kỳ vọng {expected:,}")
    except ValueError as err:
        print(f"Hủy nạp, DB giữ nguyên trạng thái cũ. Lý do: {err}", file=sys.stderr)
        return 1

    print("Nạp raw thành công.")
    return 0


if __name__ == "__main__":
    sys.exit(main())