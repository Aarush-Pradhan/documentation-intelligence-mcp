import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from mcp_server_python.documentation import DocumentationPage
from mcp_server_python.llm import LLMError, generate_comparison


class ComparisonLLMTests(unittest.IsolatedAsyncioTestCase):
    def _page(self, library, url):
        return DocumentationPage(
            url=url,
            title=f"{library} docs",
            library=library,
            content=f"{library} documented behavior",
            source=url.split("/")[2],
        )

    def _client(self, content=None, failure=None):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=AsyncMock(
                        return_value=completion,
                        side_effect=failure,
                    )
                )
            )
        )

    async def test_structured_comparison_and_context_separation(self):
        client = self._client(
            '{"summary":"A and B differ.","similarities":["Both document it."],"differences":["APIs differ."],"practical_notes":["Choose based on needs."]}'
        )
        with (
            patch(
                "mcp_server_python.llm.load_groq_settings",
                return_value=SimpleNamespace(api_key="key", model="model"),
            ),
            patch("mcp_server_python.llm.AsyncGroq", return_value=client),
        ):
            result = await generate_comparison(
                "dependency injection",
                "fastapi",
                [self._page("fastapi", "https://fastapi.tiangolo.com/deps")],
                "pydantic",
                [self._page("pydantic", "https://docs.pydantic.dev/models")],
            )

        self.assertEqual(result.summary, "A and B differ.")
        request = client.chat.completions.create.await_args.kwargs
        prompt = request["messages"][1]["content"]
        self.assertIn("LIBRARY A DOCUMENTATION: fastapi", prompt)
        self.assertIn("LIBRARY B DOCUMENTATION: pydantic", prompt)
        self.assertIn("fastapi documented behavior", prompt)
        self.assertIn("pydantic documented behavior", prompt)

    async def test_malformed_comparison_response_is_rejected(self):
        client = self._client("not-json")
        with (
            patch(
                "mcp_server_python.llm.load_groq_settings",
                return_value=SimpleNamespace(api_key="key", model="model"),
            ),
            patch("mcp_server_python.llm.AsyncGroq", return_value=client),
        ):
            with self.assertRaisesRegex(LLMError, "malformed comparison"):
                await generate_comparison(
                    "topic",
                    "fastapi",
                    [self._page("fastapi", "https://fastapi.tiangolo.com")],
                    "pydantic",
                    [self._page("pydantic", "https://docs.pydantic.dev")],
                )

    async def test_comparison_timeout_is_safe(self):
        client = self._client(failure=httpx.ReadTimeout("slow"))
        with (
            patch(
                "mcp_server_python.llm.load_groq_settings",
                return_value=SimpleNamespace(api_key="key", model="model"),
            ),
            patch("mcp_server_python.llm.AsyncGroq", return_value=client),
        ):
            with self.assertRaisesRegex(LLMError, "timed out"):
                await generate_comparison(
                    "topic",
                    "fastapi",
                    [self._page("fastapi", "https://fastapi.tiangolo.com")],
                    "pydantic",
                    [self._page("pydantic", "https://docs.pydantic.dev")],
                )


if __name__ == "__main__":
    unittest.main()
