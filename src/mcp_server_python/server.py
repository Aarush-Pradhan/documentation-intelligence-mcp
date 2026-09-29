"""MCP server registration for documentation lookup."""

import asyncio
from dataclasses import asdict
from typing import Any

import httpx
from fastmcp import FastMCP

from .config import ConfigurationError
from .documentation import fetch_documentation
from .documentation_registry import (
    UnknownLibraryError,
    get_supported_libraries,
    resolve_library,
)
from .llm import LLMError, generate_answer, generate_comparison
from .models import (
    ComparisonResponse,
    DocumentationPage,
    DocumentationSource,
)
from .search import SearchError, search_documentation

# Compatibility alias for code that patched the Phase 3 adapter.
search_web = search_documentation

mcp = FastMCP("docs")

MAX_SEARCH_RESULTS = 10
MAX_ASK_SOURCES = 5
MAX_SOURCE_CONTEXT_CHARS = 12_000
MAX_TOTAL_CONTEXT_CHARS = 30_000


@mcp.tool()
async def get_docs(query: str, library: str) -> str:
    """Search a supported library's documentation and extract its web pages."""

    try:
        library_key = resolve_library(library)
    except UnknownLibraryError as exc:
        return str(exc)
    try:
        results = await search_web(query, library_key, limit=1)
    except ConfigurationError as exc:
        return f"Configuration error: {exc}"
    except SearchError as exc:
        return f"Search error: {exc}"

    if not results:
        return f"No documentation results found for '{query}' in {library_key}."

    sources: list[str] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for result in results:
            page = await fetch_documentation(result.url, client, library_key)
            if page.content:
                sources.append(f"SOURCE: {result.url}\n{page.content}")
            else:
                sources.append(f"SOURCE: {result.url}\nUNAVAILABLE: {page.error}")
    return "\n\n".join(sources)


@mcp.tool()
async def search_docs(
    library: str, query: str, max_results: int = 5
) -> dict[str, Any]:
    """Search official documentation without fetching page contents."""

    clean_library = library.strip() if isinstance(library, str) else ""
    clean_query = query.strip() if isinstance(query, str) else ""
    response: dict[str, Any] = {
        "library": clean_library,
        "query": clean_query,
        "results": [],
    }

    if not clean_library:
        response["error"] = "Library is required."
        return response
    if not clean_query:
        response["error"] = "Query must not be empty."
        return response
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        response["error"] = "max_results must be an integer between 1 and 10."
        return response
    if not 1 <= max_results <= MAX_SEARCH_RESULTS:
        response["error"] = "max_results must be between 1 and 10."
        return response

    try:
        library_key = resolve_library(clean_library)
    except UnknownLibraryError as exc:
        response["error"] = str(exc)
        return response

    response["library"] = library_key
    try:
        results = await search_documentation(
            clean_query, library_key, limit=max_results
        )
    except ConfigurationError as exc:
        response["error"] = f"Configuration error: {exc}"
        return response
    except SearchError as exc:
        response["error"] = f"Search error: {exc}"
        return response
    except Exception:
        response["error"] = "Unexpected documentation search failure."
        return response

    response["results"] = [asdict(result) for result in results]
    return response


@mcp.tool()
async def get_documentation(library: str, url: str) -> dict[str, Any]:
    """Fetch readable content from one official documentation page."""

    clean_library = library.strip() if isinstance(library, str) else ""
    clean_url = url.strip() if isinstance(url, str) else ""
    response: dict[str, Any] = {"library": clean_library, "url": clean_url}

    if not clean_library:
        response["error"] = "Library is required."
        return response
    if not clean_url:
        response["error"] = "URL is required."
        return response

    try:
        library_key = resolve_library(clean_library)
    except UnknownLibraryError as exc:
        response["error"] = str(exc)
        return response

    response["library"] = library_key
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            page = await fetch_documentation(clean_url, client, library_key)
    except Exception:
        response["error"] = "Unexpected documentation fetch failure."
        return response

    if page.error:
        response["error"] = page.error
        return response

    response.update(
        {
            "title": page.title,
            "content": page.content,
            "source": page.source,
        }
    )
    return response


@mcp.tool()
async def ask_docs(
    library: str, question: str, max_sources: int = 3
) -> dict[str, Any]:
    """Answer a question using retrieved official documentation context."""

    clean_library = library.strip() if isinstance(library, str) else ""
    clean_question = question.strip() if isinstance(question, str) else ""
    response: dict[str, Any] = {
        "library": clean_library,
        "question": clean_question,
        "sources": [],
    }

    if not clean_library:
        response["error"] = "Library is required."
        return response
    if not clean_question:
        response["error"] = "Question must not be empty."
        return response
    if isinstance(max_sources, bool) or not isinstance(max_sources, int):
        response["error"] = "max_sources must be an integer between 1 and 5."
        return response
    if not 1 <= max_sources <= MAX_ASK_SOURCES:
        response["error"] = "max_sources must be between 1 and 5."
        return response

    try:
        library_key = resolve_library(clean_library)
    except UnknownLibraryError as exc:
        response["error"] = str(exc)
        return response
    response["library"] = library_key

    try:
        results = await search_documentation(
            clean_question, library_key, limit=max_sources
        )
    except ConfigurationError as exc:
        response["error"] = f"Configuration error: {exc}"
        return response
    except SearchError as exc:
        response["error"] = f"Search error: {exc}"
        return response
    except Exception:
        response["error"] = "Unexpected documentation search failure."
        return response

    if not results:
        response["error"] = "No official documentation was found."
        return response

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            pages = await _fetch_context(results, library_key, client)
    except Exception:
        response["error"] = "Unexpected documentation fetch failure."
        return response

    if not pages:
        response["error"] = "Documentation could not be retrieved."
        return response

    try:
        generated = await generate_answer(clean_question, pages)
    except ConfigurationError as exc:
        response["error"] = f"Configuration error: {exc}"
        return response
    except LLMError as exc:
        response["error"] = f"Answer generation error: {exc}"
        return response
    except Exception:
        response["error"] = "Unexpected answer generation failure."
        return response

    response["answer"] = generated.answer
    response["sources"] = [
        {"title": page.title, "url": page.url}
        for page in pages
    ]
    return response


@mcp.tool()
async def compare_docs(
    library_a: str,
    library_b: str,
    topic: str,
    max_sources_per_library: int = 2,
) -> dict[str, Any]:
    """Compare two supported libraries using their official documentation."""

    clean_a = library_a.strip() if isinstance(library_a, str) else ""
    clean_b = library_b.strip() if isinstance(library_b, str) else ""
    clean_topic = topic.strip() if isinstance(topic, str) else ""
    response: dict[str, Any] = {
        "library_a": clean_a,
        "library_b": clean_b,
        "topic": clean_topic,
        "sources": {"library_a": [], "library_b": []},
    }
    if not clean_a or not clean_b:
        response["error"] = "Both libraries are required."
        return response
    if not clean_topic:
        response["error"] = "Topic must not be empty."
        return response
    if isinstance(max_sources_per_library, bool) or not isinstance(
        max_sources_per_library, int
    ):
        response["error"] = (
            "max_sources_per_library must be an integer between 1 and 3."
        )
        return response
    if not 1 <= max_sources_per_library <= 3:
        response["error"] = "max_sources_per_library must be between 1 and 3."
        return response

    try:
        canonical_a = resolve_library(clean_a)
        canonical_b = resolve_library(clean_b)
    except UnknownLibraryError as exc:
        response["error"] = str(exc)
        return response
    if canonical_a == canonical_b:
        response["error"] = "The two libraries must be different."
        return response
    response["library_a"] = canonical_a
    response["library_b"] = canonical_b
    response["sources"] = {canonical_a: [], canonical_b: []}

    try:
        results_a, results_b = await asyncio.gather(
            search_documentation(clean_topic, canonical_a, max_sources_per_library),
            search_documentation(clean_topic, canonical_b, max_sources_per_library),
        )
    except ConfigurationError as exc:
        response["error"] = f"Configuration error: {exc}"
        return response
    except SearchError as exc:
        response["error"] = f"Search error: {exc}"
        return response
    except Exception:
        response["error"] = "Unexpected documentation search failure."
        return response

    if not results_a:
        response["error"] = f"Insufficient documentation found for {canonical_a}."
        return response
    if not results_b:
        response["error"] = f"Insufficient documentation found for {canonical_b}."
        return response

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            context_a, context_b = await asyncio.gather(
                _fetch_context(results_a, canonical_a, client),
                _fetch_context(results_b, canonical_b, client),
            )
    except Exception:
        response["error"] = "Unexpected documentation fetch failure."
        return response
    if not context_a:
        response["error"] = f"Documentation could not be retrieved for {canonical_a}."
        return response
    if not context_b:
        response["error"] = f"Documentation could not be retrieved for {canonical_b}."
        return response

    try:
        comparison = await generate_comparison(
            clean_topic, canonical_a, context_a, canonical_b, context_b
        )
    except ConfigurationError as exc:
        response["error"] = f"Configuration error: {exc}"
        return response
    except LLMError as exc:
        response["error"] = f"Comparison generation error: {exc}"
        return response
    except Exception:
        response["error"] = "Unexpected comparison generation failure."
        return response

    typed_response = ComparisonResponse(
        summary=comparison.summary,
        similarities=comparison.similarities,
        differences=comparison.differences,
        practical_notes=comparison.practical_notes,
        sources={
            canonical_a: [
                DocumentationSource(page.title, page.url) for page in context_a
            ],
            canonical_b: [
                DocumentationSource(page.title, page.url) for page in context_b
            ],
        },
    )
    response["comparison"] = {
        "summary": typed_response.summary,
        "similarities": typed_response.similarities,
        "differences": typed_response.differences,
        "practical_notes": typed_response.practical_notes,
    }
    response["sources"] = {
        key: [asdict(source) for source in sources]
        for key, sources in typed_response.sources.items()
    }
    return response


async def _fetch_context(
    results: list[Any], library: str, client: httpx.AsyncClient
) -> list[DocumentationPage]:
    """Fetch successful pages and apply the shared deterministic context limits."""

    pages: list[DocumentationPage] = []
    total_context_chars = 0
    for result in results:
        try:
            page = await fetch_documentation(result.url, client, library)
        except Exception:
            continue
        if not page.content:
            continue
        remaining = MAX_TOTAL_CONTEXT_CHARS - total_context_chars
        if remaining <= 0:
            break
        content = page.content[: min(MAX_SOURCE_CONTEXT_CHARS, remaining)]
        pages.append(
            DocumentationPage(
                url=page.url,
                title=page.title or result.title,
                library=page.library or library,
                content=content,
                source=page.source or result.source,
            )
        )
        total_context_chars += len(content)
    return pages


def main() -> None:
    """Start the MCP server over stdio."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()