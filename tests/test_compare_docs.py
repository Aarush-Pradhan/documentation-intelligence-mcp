import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from mcp_server_python.documentation import DocumentationPage
from mcp_server_python.llm import LLMError
from mcp_server_python.models import (
    DocumentationComparison,
    DocumentationSearchResult,
)
from mcp_server_python.server import (
    MAX_SOURCE_CONTEXT_CHARS,
    MAX_TOTAL_CONTEXT_CHARS,
    compare_docs,
    mcp,
)


class FakeHttpClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class CompareDocsToolTests(unittest.IsolatedAsyncioTestCase):
    def _result(self, library, index=1):
        domain = "fastapi.tiangolo.com" if library == "fastapi" else "docs.pydantic.dev"
        return DocumentationSearchResult(
            title=f"{library} documentation {index}",
            url=f"https://{domain}/page-{index}",
            snippet="snippet",
            library=library,
            source=domain,
        )

    def _page(self, result, content="documentation"):
        return DocumentationPage(
            url=result.url,
            title=result.title,
            library=result.library,
            content=content,
            source=result.source,
        )

    async def test_success_separates_context_and_constructs_trusted_sources(self):
        fastapi_result = self._result("fastapi")
        pydantic_result = self._result("pydantic")
        fastapi_page = self._page(fastapi_result, "FastAPI dependency docs")
        pydantic_page = self._page(pydantic_result, "Pydantic dependency docs")

        async def search(query, library, limit):
            return [fastapi_result] if library == "fastapi" else [pydantic_result]

        async def fetch(url, client, library):
            return fastapi_page if library == "fastapi" else pydantic_page

        with (
            patch("mcp_server_python.server.search_documentation", new=AsyncMock(side_effect=search)) as search_mock,
            patch("mcp_server_python.server.fetch_documentation", new=AsyncMock(side_effect=fetch)),
            patch(
                "mcp_server_python.server.generate_comparison",
                new=AsyncMock(
                    return_value=DocumentationComparison(
                        "Both support validation.",
                        ["Both document validation."],
                        ["Their APIs differ."],
                        ["Choose based on the documented workflow."],
                    )
                ),
            ) as generate,
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=FakeHttpClient()),
        ):
            response = await compare_docs(
                "FastAPI", "Pydantic", " dependency injection ", 1
            )

        self.assertEqual(response["library_a"], "fastapi")
        self.assertEqual(response["library_b"], "pydantic")
        self.assertEqual(response["topic"], "dependency injection")
        self.assertEqual(response["comparison"]["summary"], "Both support validation.")
        self.assertEqual(response["sources"], {
            "fastapi": [{"title": fastapi_page.title, "url": fastapi_page.url}],
            "pydantic": [{"title": pydantic_page.title, "url": pydantic_page.url}],
        })
        self.assertEqual(search_mock.await_count, 2)
        generate.assert_awaited_once()
        context_a, context_b = generate.await_args.args[2], generate.await_args.args[4]
        self.assertEqual(context_a[0].content, "FastAPI dependency docs")
        self.assertEqual(context_b[0].content, "Pydantic dependency docs")

    async def test_validation_rejects_unsupported_same_empty_and_invalid_inputs(self):
        response = await compare_docs("fastapi", "fastapi", "topic")
        self.assertIn("different", response["error"])
        response = await compare_docs("unknown", "pydantic", "topic")
        self.assertIn("Unsupported library", response["error"])
        for topic in ("", "   "):
            response = await compare_docs("fastapi", "pydantic", topic)
            self.assertIn("Topic must not be empty", response["error"])
        for value in (0, 4, -1, "2", True):
            response = await compare_docs("fastapi", "pydantic", "topic", value)
            self.assertIn("max_sources_per_library", response["error"])

    async def test_missing_results_identify_the_library(self):
        first = self._result("fastapi")

        async def search(query, library, limit):
            return [first] if library == "fastapi" else []

        with patch(
            "mcp_server_python.server.search_documentation",
            new=AsyncMock(side_effect=search),
        ), patch("mcp_server_python.server.generate_comparison", new=AsyncMock()) as generate:
            response = await compare_docs("fastapi", "pydantic", "topic")
        self.assertIn("pydantic", response["error"])
        generate.assert_not_awaited()

    async def test_partial_page_failure_keeps_other_sources(self):
        fastapi_result = self._result("fastapi")
        pydantic_result = self._result("pydantic")
        good_page = self._page(pydantic_result)

        async def search(query, library, limit):
            return [fastapi_result] if library == "fastapi" else [pydantic_result]

        async def fetch(url, client, library):
            return DocumentationPage(fastapi_result.url, error="HTTP 503") if library == "fastapi" else good_page

        with (
            patch("mcp_server_python.server.search_documentation", new=AsyncMock(side_effect=search)),
            patch("mcp_server_python.server.fetch_documentation", new=AsyncMock(side_effect=fetch)),
            patch("mcp_server_python.server.generate_comparison", new=AsyncMock(return_value=DocumentationComparison("summary", [], [], []))),
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=FakeHttpClient()),
        ):
            response = await compare_docs("fastapi", "pydantic", "topic")
        self.assertIn("fastapi", response["error"])

    async def test_all_sources_failed_for_one_library_does_not_call_llm(self):
        fastapi_result = self._result("fastapi")
        pydantic_result = self._result("pydantic")

        async def search(query, library, limit):
            return [fastapi_result] if library == "fastapi" else [pydantic_result]

        async def fetch(url, client, library):
            return DocumentationPage(url, error="timeout") if library == "fastapi" else self._page(pydantic_result)

        with (
            patch("mcp_server_python.server.search_documentation", new=AsyncMock(side_effect=search)),
            patch("mcp_server_python.server.fetch_documentation", new=AsyncMock(side_effect=fetch)),
            patch("mcp_server_python.server.generate_comparison", new=AsyncMock()) as generate,
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=FakeHttpClient()),
        ):
            response = await compare_docs("fastapi", "pydantic", "topic")
        self.assertIn("fastapi", response["error"])
        generate.assert_not_awaited()

    async def test_context_limits_are_enforced(self):
        fastapi_result = self._result("fastapi")
        pydantic_result = self._result("pydantic")
        huge = "x" * (MAX_SOURCE_CONTEXT_CHARS + 100)

        async def search(query, library, limit):
            return [fastapi_result] if library == "fastapi" else [pydantic_result]

        async def fetch(url, client, library):
            result = fastapi_result if library == "fastapi" else pydantic_result
            return self._page(result, huge)

        with (
            patch("mcp_server_python.server.search_documentation", new=AsyncMock(side_effect=search)),
            patch("mcp_server_python.server.fetch_documentation", new=AsyncMock(side_effect=fetch)),
            patch("mcp_server_python.server.generate_comparison", new=AsyncMock(return_value=DocumentationComparison("summary", [], [], []))) as generate,
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=FakeHttpClient()),
        ):
            await compare_docs("fastapi", "pydantic", "topic")
        context_a, context_b = generate.await_args.args[2], generate.await_args.args[4]
        self.assertEqual(len(context_a[0].content), MAX_SOURCE_CONTEXT_CHARS)
        self.assertEqual(len(context_b[0].content), MAX_SOURCE_CONTEXT_CHARS)
        self.assertLessEqual(len(context_a[0].content), MAX_TOTAL_CONTEXT_CHARS)
        self.assertLessEqual(len(context_b[0].content), MAX_TOTAL_CONTEXT_CHARS)

    async def test_llm_failure_is_safe(self):
        fastapi_result = self._result("fastapi")
        pydantic_result = self._result("pydantic")

        async def search(query, library, limit):
            return [fastapi_result] if library == "fastapi" else [pydantic_result]

        async def fetch(url, client, library):
            return self._page(fastapi_result if library == "fastapi" else pydantic_result)

        with (
            patch("mcp_server_python.server.search_documentation", new=AsyncMock(side_effect=search)),
            patch("mcp_server_python.server.fetch_documentation", new=AsyncMock(side_effect=fetch)),
            patch("mcp_server_python.server.generate_comparison", new=AsyncMock(side_effect=LLMError("timeout"))),
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=FakeHttpClient()),
        ):
            response = await compare_docs("fastapi", "pydantic", "topic")
        self.assertIn("Comparison generation error", response["error"])
        self.assertNotIn("Traceback", response["error"])


class CompareDocsRegistrationTests(unittest.TestCase):
    def test_all_five_tools_are_registered(self):
        for name in ("get_docs", "search_docs", "get_documentation", "ask_docs", "compare_docs"):
            self.assertIsNotNone(asyncio.run(mcp.get_tool(name)))


if __name__ == "__main__":
    unittest.main()
