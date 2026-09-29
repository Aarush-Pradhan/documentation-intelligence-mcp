"""Central registry for supported documentation libraries."""

from dataclasses import dataclass
from urllib.parse import urlsplit


class UnknownLibraryError(ValueError):
    """Raised when a library is not present in the documentation registry."""


@dataclass(frozen=True)
class DocumentationLibrary:
    """Documentation metadata for one supported library."""

    canonical_name: str
    display_name: str
    docs_url: str
    allowed_domains: tuple[str, ...]


_LIBRARIES: dict[str, DocumentationLibrary] = {
    "openai": DocumentationLibrary(
        canonical_name="openai",
        display_name="OpenAI",
        docs_url="https://platform.openai.com/docs",
        allowed_domains=("platform.openai.com",),
    ),
    "langchain": DocumentationLibrary(
        canonical_name="langchain",
        display_name="LangChain",
        docs_url="https://docs.langchain.com",
        allowed_domains=("docs.langchain.com",),
    ),
    "llama-index": DocumentationLibrary(
        canonical_name="llama-index",
        display_name="LlamaIndex",
        docs_url="https://docs.llamaindex.ai/en/stable",
        allowed_domains=("docs.llamaindex.ai",),
    ),
    "uv": DocumentationLibrary(
        canonical_name="uv",
        display_name="uv",
        docs_url="https://docs.astral.sh/uv",
        allowed_domains=("docs.astral.sh",),
    ),
    "fastapi": DocumentationLibrary(
        canonical_name="fastapi",
        display_name="FastAPI",
        docs_url="https://fastapi.tiangolo.com",
        allowed_domains=("fastapi.tiangolo.com",),
    ),
    "pydantic": DocumentationLibrary(
        canonical_name="pydantic",
        display_name="Pydantic",
        docs_url="https://docs.pydantic.dev/latest",
        allowed_domains=("docs.pydantic.dev",),
    ),
}

_LIBRARY_ALIASES = {
    "llamaindex": "llama-index",
}


def _supported_library_message() -> str:
    return ", ".join(sorted(_LIBRARIES))


def resolve_library(name: str) -> str:
    """Return the canonical identifier for a case-insensitive library name."""

    canonical_name = name.strip().lower()
    canonical_name = _LIBRARY_ALIASES.get(canonical_name, canonical_name)
    if canonical_name not in _LIBRARIES:
        raise UnknownLibraryError(
            f"Unsupported library '{name}'. Supported libraries: "
            f"{_supported_library_message()}."
        )
    return canonical_name


def get_library(name: str) -> DocumentationLibrary:
    """Return registry metadata for a supported library."""

    return _LIBRARIES[resolve_library(name)]


def get_supported_libraries() -> tuple[str, ...]:
    """Return all supported canonical library identifiers."""

    return tuple(sorted(_LIBRARIES))


def is_supported_library(name: str) -> bool:
    """Return whether a library name resolves to a registry entry."""

    try:
        resolve_library(name)
    except UnknownLibraryError:
        return False
    return True


def validate_documentation_url(library: str, url: str) -> bool:
    """Return whether a URL uses HTTPS and belongs to the library's domains."""

    entry = get_library(library)
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError:
        return False

    if parsed.scheme.lower() != "https" or not hostname or parsed.username:
        return False

    normalized_hostname = hostname.rstrip(".").lower()
    return any(
        normalized_hostname == domain
        or normalized_hostname.endswith(f".{domain}")
        for domain in entry.allowed_domains
    )