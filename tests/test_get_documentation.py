import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from mcp_server_python.config import ConfigurationError
from mcp_server_python.documentation import fetch_documentation
from mcp_server_python.models import DocumentationPage
from mcp_server_python.search import SearchError
from mcp_server_python.server import get_documentation, mcp


class FakeHttpClient:
    def __init__(self):
        self.get = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class GetDocumentationToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_page_is_serialized_and_library_is_resolved(self):
        page = DocumentationPage(
            url="https://docs.astral.sh/uv/installation/",
            title="Installation",
            library="uv",
            content="Install uv",
            source="docs.astral.sh",
        )
        client = FakeHttpClient()
        with (
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=client),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(return_value=page),
            ) as fetch,
        ):
            response = await get_documentation(
                "UV", " https://docs.astral.sh/uv/installation/ "
            )

        self.assertEqual(response, {
            "library": "uv",
            "url": "https://docs.astral.sh/uv/installation/",
            "title": "Installation",
            "content": "Install uv",
            "source": "docs.astral.sh",
        })
        fetch.assert_awaited_once_with(
            "https://docs.astral.sh/uv/installation/", client, "uv"
        )

    async def test_unsupported_library_is_rejected(self):
        with patch("mcp_server_python.server.httpx.AsyncClient") as client:
            response = await get_documentation(
                "not-a-library", "https://example.com/docs"
            )
        self.assertIn("Unsupported library", response["error"])
        client.assert_not_called()

    async def test_invalid_urls_are_rejected_before_http_fetch(self):
        client = FakeHttpClient()
        invalid_urls = (
            "https://evil-openai.com/docs",
            "https://platform.openai.com.evil.com/docs",
            "https://example.com/docs",
            "not a url",
            "http://platform.openai.com/docs",
            "javascript://platform.openai.com/docs",
        )
        with patch(
            "mcp_server_python.server.httpx.AsyncClient", return_value=client
        ):
            for url in invalid_urls:
                response = await get_documentation("openai", url)
                self.assertIn("error", response)
        client.get.assert_not_awaited()

    async def test_case_insensitive_library_and_official_subdomain_are_allowed(self):
        page = DocumentationPage(
            url="https://guide.docs.astral.sh/uv/",
            title="Guide",
            library="uv",
            content="Readable content",
            source="guide.docs.astral.sh",
        )
        client = FakeHttpClient()
        with (
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=client),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(return_value=page),
            ),
        ):
            response = await get_documentation(
                "uV", "https://guide.docs.astral.sh/uv/"
            )
        self.assertEqual(response["library"], "uv")
        self.assertEqual(response["source"], "guide.docs.astral.sh")

    async def test_fetch_errors_are_returned_without_stack_traces(self):
        errors = (
            ConfigurationError("missing key"),
            SearchError("not expected but safe"),
            RuntimeError("unexpected"),
        )
        for error in errors:
            client = FakeHttpClient()
            with (
                patch("mcp_server_python.server.httpx.AsyncClient", return_value=client),
                patch(
                    "mcp_server_python.server.fetch_documentation",
                    new=AsyncMock(side_effect=error),
                ),
            ):
                response = await get_documentation(
                    "uv", "https://docs.astral.sh/uv/"
                )
            self.assertEqual(response["error"], "Unexpected documentation fetch failure.")
            self.assertNotIn("Traceback", response["error"])

    async def test_service_error_is_returned_as_structured_error(self):
        page = DocumentationPage(
            "https://docs.astral.sh/uv/", error="request timed out"
        )
        client = FakeHttpClient()
        with (
            patch("mcp_server_python.server.httpx.AsyncClient", return_value=client),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(return_value=page),
            ),
        ):
            response = await get_documentation("uv", "https://docs.astral.sh/uv/")
        self.assertEqual(response, {
            "library": "uv",
            "url": "https://docs.astral.sh/uv/",
            "error": "request timed out",
        })


class GetDocumentationRegistrationTests(unittest.TestCase):
    def test_all_documentation_tools_are_registered(self):
        self.assertIsNotNone(asyncio.run(mcp.get_tool("get_docs")))
        self.assertIsNotNone(asyncio.run(mcp.get_tool("search_docs")))
        self.assertIsNotNone(asyncio.run(mcp.get_tool("get_documentation")))


if __name__ == "__main__":
    unittest.main()
