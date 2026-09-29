import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from mcp_server_python.documentation import DocumentationResult, fetch_documentation
from mcp_server_python.documentation_registry import (
    UnknownLibraryError,
    get_library,
    get_supported_libraries,
    resolve_library,
    validate_documentation_url,
)
from mcp_server_python.search import SearchResult
from mcp_server_python.server import get_docs


class DocumentationRegistryTests(unittest.TestCase):
    def test_case_insensitive_resolution(self):
        for value in ("openai", "OpenAI", "OPENAI"):
            self.assertEqual(resolve_library(value), "openai")

    def test_all_supported_libraries_resolve(self):
        values = {
            "LangChain": "langchain",
            "LlamaIndex": "llama-index",
            "uv": "uv",
            "FastAPI": "fastapi",
            "Pydantic": "pydantic",
        }
        for value, expected in values.items():
            self.assertEqual(resolve_library(value), expected)

    def test_unknown_library_has_supported_list(self):
        with self.assertRaisesRegex(UnknownLibraryError, "fastapi"):
            resolve_library("unknown")

    def test_supported_library_listing(self):
        self.assertEqual(
            get_supported_libraries(),
            ("fastapi", "langchain", "llama-index", "openai", "pydantic", "uv"),
        )

    def test_official_urls_are_accepted(self):
        for name in get_supported_libraries():
            self.assertTrue(validate_documentation_url(name, get_library(name).docs_url))

    def test_invalid_urls_are_rejected(self):
        invalid_urls = (
            "https://example.com/docs",
            "https://evil-openai.com/docs",
            "https://platform.openai.com.evil.com/docs",
            "not a url",
            "http://platform.openai.com/docs",
            "javascript://platform.openai.com/docs",
        )
        for url in invalid_urls:
            self.assertFalse(validate_documentation_url("openai", url))

    def test_get_docs_preserves_uv_resolution(self):
        self._assert_get_docs_resolution(
            "UV", "uv", "https://docs.astral.sh/uv"
        )

    def test_get_docs_preserves_openai_resolution(self):
        self._assert_get_docs_resolution(
            "OpenAI", "openai", "https://platform.openai.com/docs"
        )

    def _assert_get_docs_resolution(
        self, library: str, canonical_name: str, url: str
    ):
        search_result = SearchResult("documentation", url, "snippet")
        with (
            patch(
                "mcp_server_python.server.search_web",
                new=AsyncMock(return_value=[search_result]),
            ),
            patch(
                "mcp_server_python.server.fetch_documentation",
                new=AsyncMock(
                    return_value=DocumentationResult(
                        search_result.link, content="installation"
                    )
                ),
            ) as fetch,
        ):
            result = asyncio.run(get_docs("installation", library))

        self.assertIn(f"SOURCE: {url}", result)
        fetch.assert_awaited_once_with(
            search_result.link, unittest.mock.ANY, canonical_name
        )

    def test_fetch_rejects_unofficial_url_when_library_is_provided(self):
        client = httpx.AsyncClient()
        try:
            result = asyncio.run(
                fetch_documentation("https://example.com", client, "openai")
            )
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(
            result,
            DocumentationResult(
                "https://example.com",
                error="URL is not an official documentation domain",
            ),
        )


if __name__ == "__main__":
    unittest.main()