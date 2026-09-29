"""Documentation page retrieval and content extraction."""

import asyncio

import httpx
import trafilatura

from .documentation_registry import (
    UnknownLibraryError,
    resolve_library,
    validate_documentation_url,
)
from .models import DocumentationPage, DocumentationResult


async def fetch_documentation(
    url: str, client: httpx.AsyncClient, library: str | None = None
) -> DocumentationResult:
    """Fetch a documentation page and extract readable text from it."""

    canonical_library = library
    if library is not None:
        try:
            canonical_library = resolve_library(library)
        except UnknownLibraryError as exc:
            return DocumentationResult(url=url, error=str(exc))
        if not validate_documentation_url(canonical_library, url):
            return DocumentationResult(
                url=url,
                error="URL is not an official documentation domain",
            )
    elif not _is_https_url(url):
        return DocumentationResult(url=url, error="invalid documentation URL")

    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException:
        return DocumentationResult(
            url=url, library=canonical_library, error="request timed out"
        )
    except httpx.HTTPStatusError as exc:
        return DocumentationResult(
            url=url, library=canonical_library, error=f"HTTP {exc.response.status_code}"
        )
    except httpx.HTTPError as exc:
        return DocumentationResult(
            url=url, library=canonical_library, error=f"request failed: {exc}"
        )

    try:
        content = await asyncio.wait_for(
            asyncio.to_thread(_extract_content, response.text), timeout=10.0
        )
    except asyncio.TimeoutError:
        return DocumentationResult(
            url=url,
            library=canonical_library,
            error="content extraction timed out",
        )
    except Exception as exc:
        return DocumentationResult(
            url=url,
            library=canonical_library,
            error=f"content extraction failed: {exc}",
        )

    if not content or not content.strip():
        return DocumentationResult(
            url=url,
            library=canonical_library,
            error="no readable content was extracted",
        )
    metadata = trafilatura.extract_metadata(response.text)
    title = metadata.title if metadata is not None else None
    source = httpx.URL(url).host or ""
    return DocumentationPage(
        url=url,
        content=content.strip(),
        library=canonical_library,
        source=source,
        title=title,
    )


def _is_https_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except (TypeError, ValueError):
        return False
    return parsed.scheme == "https" and bool(parsed.host) and not parsed.userinfo


def _extract_content(html: str) -> str | None:
    """Extract readable text without blocking the MCP event loop."""

    return trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        include_formatting=False,
        favor_recall=False,
    )