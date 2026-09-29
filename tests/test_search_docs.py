import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from mcp_server_python.config import ConfigurationError
from mcp_server_python.models import DocumentationSearchResult
from mcp_server_python.search import SearchError
from mcp_server_python.server import mcp, search_docs


class SearchDocsToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_resolves_library_and_returns_structured_results(self):
        result = DocumentationSearchResult(
            title="Install uv",
            url="https://docs.astral.sh/uv/getting-started/installation/",
            snippet="Install uv",
            library="uv",
            source="docs.astral.sh",
        )
        with patch(
            "mcp_server_python.server.search_documentation",
            new=AsyncMock(return_value=[result]),
        ) as search:
            response = await search_docs("UV", " installation ", max_results=3)

        self.assertEqual(response["library"], "uv")
        self.assertEqual(response["query"], "installation")
        self.assertEqual(response["results"], [
            {
                "title": "Install uv",
                "url": "https://docs.astral.sh/uv/getting-started/installation/",
                "snippet": "Install uv",
                "library": "uv",
                "source": "docs.astral.sh",
            }
        ])
        search.assert_awaited_once_with("installation", "uv", limit=3)

    async def test_supported_library_names_are_case_insensitive(self):
        with patch(
            "mcp_server_python.server.search_documentation",
            new=AsyncMock(return_value=[]),
        ) as search:
            response = await search_docs("OpenAI", "installation")

        self.assertEqual(response, {
            "library": "openai",
            "query": "installation",
            "results": [],
        })
        search.assert_awaited_once_with("installation", "openai", limit=5)

    async def test_empty_and_unsupported_inputs_return_clear_errors(self):
        for query in ("", "   "):
            response = await search_docs("uv", query)
            self.assertEqual(response["results"], [])
            self.assertEqual(response["error"], "Query must not be empty.")

        response = await search_docs("not-a-library", "installation")
        self.assertEqual(response["results"], [])
        self.assertIn("Unsupported library", response["error"])

    async def test_max_results_validation(self):
        for value in (0, 11, -1, "5", True):
            response = await search_docs("uv", "installation", value)
            self.assertEqual(response["results"], [])
            self.assertIn("max_results", response["error"])

        with patch(
            "mcp_server_python.server.search_documentation",
            new=AsyncMock(return_value=[]),
        ) as search:
            await search_docs("uv", "installation", 1)
            await search_docs("uv", "installation", 10)
        self.assertEqual(search.await_args_list[0].kwargs["limit"], 1)
        self.assertEqual(search.await_args_list[1].kwargs["limit"], 10)

    async def test_search_failures_are_returned_without_stack_traces(self):
        failures = (
            ConfigurationError("missing key"),
            SearchError("timed out"),
            RuntimeError("unexpected"),
        )
        for failure in failures:
            with patch(
                "mcp_server_python.server.search_documentation",
                new=AsyncMock(side_effect=failure),
            ):
                response = await search_docs("uv", "installation")
            self.assertEqual(response["results"], [])
            self.assertIn("error", response)
            self.assertNotIn("Traceback", response["error"])

    async def test_empty_results_are_structured(self):
        with patch(
            "mcp_server_python.server.search_documentation",
            new=AsyncMock(return_value=[]),
        ):
            response = await search_docs("uv", "unknown topic")
        self.assertEqual(response, {
            "library": "uv",
            "query": "unknown topic",
            "results": [],
        })


class SearchDocsRegistrationTests(unittest.TestCase):
    def test_get_docs_and_search_docs_are_registered(self):
        self.assertIsNotNone(asyncio.run(mcp.get_tool("get_docs")))
        self.assertIsNotNone(asyncio.run(mcp.get_tool("search_docs")))


if __name__ == "__main__":
    unittest.main()
