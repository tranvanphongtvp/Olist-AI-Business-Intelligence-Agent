"""Cấu hình riêng cho API: khóa để n8n gọi và tài khoản ghi lịch sử."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Thiếu biến môi trường {name}. Hãy đặt giá trị trong file .env")
    return value


@dataclass(frozen=True)
class ApiSettings:
    api_key: str
    writer_user: str
    writer_password: str


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    return ApiSettings(
        api_key=_required("API_KEY"),
        writer_user=_required("WRITER_DB_USER"),
        writer_password=_required("WRITER_DB_PASSWORD"),
    )
