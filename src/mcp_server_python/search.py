"""Serper-backed documentation search service."""

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .config import ConfigurationError, load_settings
from .documentation_registry import get_library, resolve_library
from .models import DocumentationSearchResult


SERPER_URL = "https://google.serper.dev/search"


class SearchError(RuntimeError):
    """Raised when a Serper search cannot be completed or validated."""


SearchResult = DocumentationSearchResult


async def search_documentation(
    query: str, library: str, limit: int = 2
) -> list[SearchResult]:
    """Search one supported library and return structured documentation results."""

    library_key = resolve_library(library)
    domain = get_library(library_key).allowed_domains[0]
    return await search_web(f"site:{domain} {query}", library_key, limit)


async def search_web(
    query: str, library: str | None = None, limit: int = 2
) -> list[SearchResult]:
    """Search Serper and return cleaned, structured organic results.

    ``library`` is optional for compatibility with the Phase 3 service. New
    callers should use ``search_documentation`` so the site restriction is
    built from the registry.
    """

    try:
        settings = load_settings()
        headers = {"X-API-KEY": settings.serper_api_key}
        payload = {"q": query, "num": limit}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(SERPER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data: Any = response.json()
    except ConfigurationError:
        raise
    except httpx.TimeoutException as exc:
        raise SearchError("The documentation search timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise SearchError(
            f"The documentation search API returned HTTP {exc.response.status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        raise SearchError("The documentation search request failed.") from exc
    except ValueError as exc:
        raise SearchError("The documentation search returned invalid JSON.") from exc

    if not isinstance(data, dict):
        raise SearchError("The documentation search returned an invalid response.")

    organic = data.get("organic")
    if organic is None:
        raise SearchError("The documentation search response is missing organic results.")
    if not isinstance(organic, list):
        raise SearchError("The documentation search returned malformed organic results.")

    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    for item in organic:
        if len(results) >= limit:
            break
        if not isinstance(item, dict):
            continue
        link = _normalize_url(item.get("link"))
        if link is None or link in seen_urls:
            continue
        seen_urls.add(link)
        parsed = urlsplit(link)
        results.append(
            SearchResult(
                title=_text_value(item.get("title"), "Untitled documentation"),
                url=link,
                snippet=_text_value(item.get("snippet"), ""),
                library=library or "",
                source=parsed.hostname or "",
            )
        )
    return results


def _normalize_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password or not parsed.hostname:
        return None
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def _text_value(value: object, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback