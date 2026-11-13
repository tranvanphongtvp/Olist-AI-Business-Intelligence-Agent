"""Khởi tạo model cho các node của agent.

Hai nhà cung cấp dùng chung một client (ChatOpenAI), chỉ khác địa chỉ API và khóa.
Đổi nhà cung cấp chỉ cần đổi LLM_PROVIDER trong .env, không cần sửa code.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from agent.config import GROQ_BASE_URL, get_settings


def get_llm() -> ChatOpenAI:
    s = get_settings()
    if s.llm_provider == "groq":
        return ChatOpenAI(
            model=s.groq_model,
            api_key=s.groq_api_key,
            base_url=GROQ_BASE_URL,
            temperature=0,
        )
    return ChatOpenAI(model=s.openai_model, api_key=s.openai_api_key, temperature=0)
