import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from mcp_server_python.documentation import fetch_documentation
from mcp_server_python.models import DocumentationPage, DocumentationSearchResult
from mcp_server_python.search import SearchError, search_documentation


class FakeSearchResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


class SearchClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


class DocumentationSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_builds_site_query_and_returns_typed_deduplicated_results(self):
        response = FakeSearchResponse(
            {
                "organic": [
                    {"title": "A", "link": "https://docs.astral.sh/uv/", "snippet": "one"},
                    {"title": "duplicate", "link": "https://docs.astral.sh/uv/", "snippet": "two"},
                    {"title": "B", "link": "https://docs.astral.sh/uv/install"},
                    {"title": "missing url"},
                ]
            }
        )
        with (
            patch("mcp_server_python.search.load_settings") as settings,
            patch(
                "mcp_server_python.search.httpx.AsyncClient",
                return_value=SearchClient(response),
            ),
        ):
            settings.return_value.serper_api_key = "test-key"
            results = await search_documentation("installation", "UV", limit=2)

        self.assertEqual([result.url for result in results], [
            "https://docs.astral.sh/uv/",
            "https://docs.astral.sh/uv/install",
        ])
        self.assertIsInstance(results[0], DocumentationSearchResult)
        self.assertEqual(results[0].library, "uv")
        self.assertEqual(results[0].source, "docs.astral.sh")

    async def test_empty_results_are_returned_as_empty_list(self):
        with (
            patch("mcp_server_python.search.load_settings") as settings,
            patch(
                "mcp_server_python.search.httpx.AsyncClient",
                return_value=SearchClient(FakeSearchResponse({"organic": []})),
            ),
        ):
            settings.return_value.serper_api_key = "test-key"
            self.assertEqual(await search_documentation("x", "uv"), [])

    async def test_search_errors_are_normalized(self):
        cases = (
            (FakeSearchResponse({"organic": "bad"}), "malformed organic"),
            (FakeSearchResponse(ValueError("bad json")), "invalid JSON"),
            (None, "timed out"),
        )
        for response, message in cases:
            with patch("mcp_server_python.search.load_settings") as settings:
                settings.return_value.serper_api_key = "test-key"
                error = httpx.ReadTimeout("timeout") if response is None else None
                with patch(
                    "mcp_server_python.search.httpx.AsyncClient",
                    return_value=SearchClient(response, error),
                ):
                    with self.assertRaises(SearchError) as raised:
                        await search_documentation("x", "uv")
            self.assertIn(message, str(raised.exception))

    async def test_missing_api_key_is_preserved_as_configuration_error(self):
        from mcp_server_python.config import ConfigurationError

        with patch(
            "mcp_server_python.search.load_settings",
            side_effect=ConfigurationError("missing"),
        ):
            with self.assertRaises(ConfigurationError):
                await search_documentation("x", "uv")


class DocumentationFetchTests(unittest.IsolatedAsyncioTestCase):
    def _response(self, html="<html></html>", status=200):
        return httpx.Response(
            status,
            request=httpx.Request("GET", "https://docs.astral.sh/uv"),
            text=html,
        )

    async def test_valid_official_url_returns_page(self):
        client = AsyncMock()
        client.get.return_value = self._response("<html>docs</html>")
        with (
            patch("mcp_server_python.documentation._extract_content", return_value="Readable docs"),
            patch("mcp_server_python.documentation.trafilatura.extract_metadata", return_value=None),
        ):
            page = await fetch_documentation(
                "https://docs.astral.sh/uv", client, "UV"
            )

        self.assertIsInstance(page, DocumentationPage)
        self.assertEqual(page.library, "uv")
        self.assertEqual(page.content, "Readable docs")

    async def test_invalid_and_lookalike_urls_are_rejected(self):
        client = AsyncMock()
        for url in ("not a url", "https://docs.astral.sh.evil.com/uv"):
            page = await fetch_documentation(url, client, "uv")
            self.assertIsNotNone(page.error)
        client.get.assert_not_awaited()

    async def test_http_failure_timeout_and_extraction_failure_are_reported(self):
        client = AsyncMock()
        client.get.return_value = self._response(status=503)
        page = await fetch_documentation("https://docs.astral.sh/uv", client, "uv")
        self.assertEqual(page.error, "HTTP 503")

        client.get.side_effect = httpx.ReadTimeout("timeout")
        page = await fetch_documentation("https://docs.astral.sh/uv", client, "uv")
        self.assertEqual(page.error, "request timed out")

        client.get.side_effect = None
        client.get.return_value = self._response()
        with patch(
            "mcp_server_python.documentation._extract_content",
            side_effect=RuntimeError("broken"),
        ):
            page = await fetch_documentation("https://docs.astral.sh/uv", client, "uv")
        self.assertIn("content extraction failed", page.error)


class DocumentationModelTests(unittest.TestCase):
    def test_models_construct_and_serialize(self):
        from dataclasses import asdict

        result = DocumentationSearchResult(
            "Install", "https://docs.example.test/install", "snippet", "uv", "docs.example.test"
        )
        self.assertEqual(asdict(result)["url"], result.url)
        page = DocumentationPage(
            "https://docs.example.test/install", "content", title="Install", library="uv"
        )
        self.assertEqual(asdict(page)["content"], "content")


if __name__ == "__main__":
    unittest.main()
