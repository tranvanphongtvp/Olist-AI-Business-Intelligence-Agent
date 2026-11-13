"""Đọc cấu hình từ biến môi trường (.env).

Không ghi cứng khóa API hay tên model trong code. Tên model phải được đặt trong .env
vì danh sách model thay đổi theo thời gian.

LLM_PROVIDER chọn nhà cung cấp: "openai" (mặc định) hoặc "groq".
Groq có API tương thích OpenAI, nên cùng một client được dùng cho cả hai.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Tự đọc .env ở thư mục gốc project, không cần `source .env` trước khi chạy.
# override=False: biến đã có sẵn trong môi trường (VD: docker, CI) vẫn được ưu tiên.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
PROVIDERS = ("openai", "groq")


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Thiếu biến môi trường {name}. Hãy đặt giá trị trong file .env")
    return value


@dataclass(frozen=True)
class Settings:
    # Database
    pg_host: str
    pg_port: int
    pg_db: str
    agent_user: str
    agent_password: str

    # LLM
    llm_provider: str
    openai_api_key: str
    openai_model: str
    groq_api_key: str
    groq_model: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider not in PROVIDERS:
        raise RuntimeError(f"LLM_PROVIDER phải là một trong {PROVIDERS}, hiện là '{provider}'")

    # Chỉ bắt buộc các biến của nhà cung cấp đang được chọn
    if provider == "openai":
        openai_key, openai_model = _required("OPENAI_API_KEY"), _required("OPENAI_MODEL")
        groq_key, groq_model = "", ""
    else:
        openai_key, openai_model = "", ""
        groq_key, groq_model = _required("GROQ_API_KEY"), _required("GROQ_MODEL")

    return Settings(
        pg_host=os.getenv("POSTGRES_HOST", "localhost"),
        pg_port=int(os.getenv("POSTGRES_PORT", "5432")),
        pg_db=_required("POSTGRES_DB"),
        agent_user=_required("AGENT_DB_USER"),
        agent_password=_required("AGENT_DB_PASSWORD"),
        llm_provider=provider,
        openai_api_key=openai_key,
        openai_model=openai_model,
        groq_api_key=groq_key,
        groq_model=groq_model,
    )
