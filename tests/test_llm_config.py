"""Kiểm tra chọn nhà cung cấp LLM. Không gọi mạng."""

import os
import unittest
from unittest import mock

from agent.config import GROQ_BASE_URL, get_settings


def _env(**overrides):
    base = {
        "POSTGRES_DB": "olist",
        "AGENT_DB_USER": "agent_ro",
        "AGENT_DB_PASSWORD": "pw",
    }
    base.update(overrides)
    return mock.patch.dict(os.environ, base, clear=True)


class ProviderSelectionTests(unittest.TestCase):
    def setUp(self):
        get_settings.cache_clear()

    def tearDown(self):
        get_settings.cache_clear()

    def test_openai_is_default(self):
        with _env(OPENAI_API_KEY="k", OPENAI_MODEL="m"):
            s = get_settings()
            self.assertEqual(s.llm_provider, "openai")

    def test_groq_provider_uses_groq_base_url(self):
        from agent.llm import get_llm

        with _env(LLM_PROVIDER="groq", GROQ_API_KEY="gk", GROQ_MODEL="gm"):
            llm = get_llm()
            self.assertEqual(llm.openai_api_base, GROQ_BASE_URL)
            self.assertEqual(llm.model_name, "gm")

    def test_openai_provider_does_not_use_groq_url(self):
        from agent.llm import get_llm

        with _env(LLM_PROVIDER="openai", OPENAI_API_KEY="k", OPENAI_MODEL="om"):
            llm = get_llm()
            self.assertNotEqual(llm.openai_api_base, GROQ_BASE_URL)
            self.assertEqual(llm.model_name, "om")

    def test_missing_key_for_selected_provider_is_reported(self):
        with _env(LLM_PROVIDER="groq", GROQ_MODEL="gm"):
            with self.assertRaises(RuntimeError) as ctx:
                get_settings()
            self.assertIn("GROQ_API_KEY", str(ctx.exception))

    def test_unknown_provider_is_rejected(self):
        with _env(LLM_PROVIDER="anthropic"):
            with self.assertRaises(RuntimeError):
                get_settings()


if __name__ == "__main__":
    unittest.main()
