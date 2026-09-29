import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from mcp_server_python.documentation import DocumentationPage
from mcp_server_python.llm import LLMError
from mcp_server_python.models import (
    DocumentationSearchResult,
    DocumentationSource,
    GeneratedAnswer,
)
from mcp_server_python.server import (
    MAX_SOURCE_CONTEXT_CHARS,
    MAX_TOTAL_CONTEXT_CHARS,
    ask_docs,
    mcp,
)


class FakeHttpClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class AskDocsToolTests(unittest.IsolatedAsyncioTestCase):
    def _result(self, index=1):
        return DocumentationSearchResult(
            title=f"Documentation {index}",
            url=f"https://docs.astral.sh/uv/page-{index}",
            snippet="snippet",
            library="uv",
            source="docs.astral.sh",
        )

    def _page(self, result, content="Relevant documentation"):
        return DocumentationPage(
            url=result.url,
            title=result.title,
            library="uv",
            content=content,
            source=result.source,
        )

    async def test_success_orchestrates_search_fetch_and_llm(self):
        result = self._result()
        page = self._page(result)
        generated = GeneratedAnswer(
            answer="Use the documented command.",
            sources=[DocumentationSource("invented", "https://evil.example")],
        )
        with (
            patch(
                "mcp_server_python.server.search_documentation",
                new=AsyncMock(return_value=[result]),
            ) as search,
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(return_value=page),
            ) as fetch,
            patch(
                "mcp_server_python.server.generate_answer",
                new=AsyncMock(return_value=generated),
            ) as generate,
            patch(
                "mcp_server_python.server.httpx.AsyncClient",
                return_value=FakeHttpClient(),
            ),
        ):
            response = await ask_docs("UV", " How do I install uv? ", 1)

        self.assertEqual(response["library"], "uv")
        self.assertEqual(response["question"], "How do I install uv?")
        self.assertEqual(response["answer"], "Use the documented command.")
        self.assertEqual(response["sources"], [
            {"title": result.title, "url": result.url}
        ])
        search.assert_awaited_once_with("How do I install uv?", "uv", limit=1)
        fetch.assert_awaited_once()
        generate.assert_awaited_once_with("How do I install uv?", [page])

    async def test_validation_rejects_bad_inputs(self):
        for question in ("", "   "):
            response = await ask_docs("uv", question)
            self.assertIn("Question must not be empty", response["error"])
        response = await ask_docs("not-a-library", "question")
        self.assertIn("Unsupported library", response["error"])
        for max_sources in (0, 6, -1, "3", True):
            response = await ask_docs("uv", "question", max_sources)
            self.assertIn("max_sources", response["error"])

    async def test_no_search_results_do_not_call_llm(self):
        with (
            patch(
                "mcp_server_python.server.search_documentation",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "mcp_server_python.server.generate_answer",
                new=AsyncMock(),
            ) as generate,
        ):
            response = await ask_docs("uv", "unknown topic")
        self.assertEqual(response["error"], "No official documentation was found.")
        generate.assert_not_awaited()

    async def test_failed_sources_are_skipped_when_another_source_succeeds(self):
        first = self._result(1)
        second = self._result(2)
        good_page = self._page(second)
        with (
            patch(
                "mcp_server_python.server.search_documentation",
                new=AsyncMock(return_value=[first, second]),
            ),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(side_effect=[
                    DocumentationPage(first.url, error="HTTP 503"),
                    good_page,
                ]),
            ),
            patch(
                "mcp_server_python.server.generate_answer",
                new=AsyncMock(
                    return_value=GeneratedAnswer("answer", [])
                ),
            ),
            patch(
                "mcp_server_python.server.httpx.AsyncClient",
                return_value=FakeHttpClient(),
            ),
        ):
            response = await ask_docs("uv", "question", 2)
        self.assertEqual(response["answer"], "answer")
        self.assertEqual(response["sources"], [
            {"title": second.title, "url": second.url}
        ])

    async def test_all_failed_sources_do_not_call_llm(self):
        result = self._result()
        with (
            patch(
                "mcp_server_python.server.search_documentation",
                new=AsyncMock(return_value=[result]),
            ),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(
                    return_value=DocumentationPage(result.url, error="timeout")
                ),
            ),
            patch(
                "mcp_server_python.server.generate_answer",
                new=AsyncMock(),
            ) as generate,
            patch(
                "mcp_server_python.server.httpx.AsyncClient",
                return_value=FakeHttpClient(),
            ),
        ):
            response = await ask_docs("uv", "question")
        self.assertEqual(response["error"], "Documentation could not be retrieved.")
        generate.assert_not_awaited()

    async def test_context_is_truncated_and_metadata_is_preserved(self):
        first = self._result(1)
        second = self._result(2)
        huge = "x" * (MAX_SOURCE_CONTEXT_CHARS + 100)
        pages = [self._page(first, huge), self._page(second, huge)]
        with (
            patch(
                "mcp_server_python.server.search_documentation",
                new=AsyncMock(return_value=[first, second]),
            ),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(side_effect=pages),
            ),
            patch(
                "mcp_server_python.server.generate_answer",
                new=AsyncMock(return_value=GeneratedAnswer("answer", [])),
            ) as generate,
            patch(
                "mcp_server_python.server.httpx.AsyncClient",
                return_value=FakeHttpClient(),
            ),
        ):
            response = await ask_docs("uv", "question", 2)

        context = generate.await_args.args[1]
        self.assertEqual(len(context[0].content), MAX_SOURCE_CONTEXT_CHARS)
        self.assertLessEqual(
            sum(len(page.content) for page in context),
            MAX_TOTAL_CONTEXT_CHARS,
        )
        self.assertEqual(response["sources"], [
            {"title": first.title, "url": first.url},
            {"title": second.title, "url": second.url},
        ])

    async def test_llm_failure_is_returned_safely(self):
        result = self._result()
        with (
            patch(
                "mcp_server_python.server.search_documentation",
                new=AsyncMock(return_value=[result]),
            ),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(return_value=self._page(result)),
            ),
            patch(
                "mcp_server_python.server.generate_answer",
                new=AsyncMock(side_effect=LLMError("timed out")),
            ),
            patch(
                "mcp_server_python.server.httpx.AsyncClient",
                return_value=FakeHttpClient(),
            ),
        ):
            response = await ask_docs("uv", "question")
        self.assertIn("Answer generation error", response["error"])
        self.assertNotIn("Traceback", response["error"])


class AskDocsRegistrationTests(unittest.TestCase):
    def test_all_four_tools_are_registered(self):
        for name in ("get_docs", "search_docs", "get_documentation", "ask_docs"):
            self.assertIsNotNone(asyncio.run(mcp.get_tool(name)))


if __name__ == "__main__":
    unittest.main()
