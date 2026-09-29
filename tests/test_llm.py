import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from mcp_server_python.config import ConfigurationError
from mcp_server_python.documentation import DocumentationPage
from mcp_server_python.llm import LLMError, generate_answer


class LLMServiceTests(unittest.IsolatedAsyncioTestCase):
    def _page(self):
        return DocumentationPage(
            url="https://docs.astral.sh/uv/",
            title="uv documentation",
            library="uv",
            content="Use `uv init` to create a project.",
            source="docs.astral.sh",
        )

    def _completion(self, content):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    async def test_success_returns_answer_and_preserves_sources(self):
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=AsyncMock(return_value=self._completion("Use uv init."))
                )
            )
        )
        with (
            patch(
                "mcp_server_python.llm.load_groq_settings",
                return_value=SimpleNamespace(api_key="test-key", model="test-model"),
            ),
            patch("mcp_server_python.llm.AsyncGroq", return_value=client),
        ):
            result = await generate_answer("How do I start?", [self._page()])

        self.assertEqual(result.answer, "Use uv init.")
        self.assertEqual(result.sources[0].url, "https://docs.astral.sh/uv/")
        self.assertEqual(result.sources[0].title, "uv documentation")
        request = client.chat.completions.create.await_args.kwargs
        self.assertEqual(request["model"], "test-model")
        self.assertIn("How do I start?", request["messages"][1]["content"])
        self.assertIn("Use `uv init`", request["messages"][1]["content"])
        self.assertIn("only the documentation context", request["messages"][0]["content"])
        self.assertIn("untrusted DATA", request["messages"][0]["content"])

    async def test_missing_groq_configuration_is_clear(self):
        with patch(
            "mcp_server_python.llm.load_groq_settings",
            side_effect=ConfigurationError("missing Groq key"),
        ):
            with self.assertRaisesRegex(ConfigurationError, "missing Groq key"):
                await generate_answer("question", [self._page()])

    async def test_api_failure_and_timeout_are_safe(self):
        for failure, message in (
            (RuntimeError("provider down"), "request failed"),
            (httpx.ReadTimeout("slow"), "timed out"),
        ):
            client = SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=AsyncMock(side_effect=failure))
                )
            )
            with (
                patch(
                    "mcp_server_python.llm.load_groq_settings",
                    return_value=SimpleNamespace(api_key="test-key", model="test-model"),
                ),
                patch("mcp_server_python.llm.AsyncGroq", return_value=client),
            ):
                with self.assertRaisesRegex(LLMError, message):
                    await generate_answer("question", [self._page()])

    async def test_empty_and_malformed_responses_are_rejected(self):
        for completion in (self._completion(""), SimpleNamespace(choices=[])):
            client = SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(
                        create=AsyncMock(return_value=completion)
                    )
                )
            )
            with (
                patch(
                    "mcp_server_python.llm.load_groq_settings",
                    return_value=SimpleNamespace(api_key="test-key", model="test-model"),
                ),
                patch("mcp_server_python.llm.AsyncGroq", return_value=client),
            ):
                with self.assertRaises(LLMError):
                    await generate_answer("question", [self._page()])

    async def test_question_and_context_are_required(self):
        with self.assertRaisesRegex(LLMError, "question"):
            await generate_answer("   ", [self._page()])
        with self.assertRaisesRegex(LLMError, "context"):
            await generate_answer("question", [])


if __name__ == "__main__":
    unittest.main()
