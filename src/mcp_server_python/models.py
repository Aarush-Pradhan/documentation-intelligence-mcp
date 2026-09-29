"""Typed models shared by documentation services and MCP adapters."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentationSearchResult:
    """One documentation search result."""

    title: str
    url: str
    snippet: str
    library: str = ""
    source: str = ""

    @property
    def link(self) -> str:
        """Compatibility name used by the existing MCP adapter."""

        return self.url


@dataclass(frozen=True, init=False)
class DocumentationPage:
    """Fetched and extracted documentation, or a fetch failure."""

    title: str | None
    url: str
    library: str | None
    content: str | None
    source: str | None
    error: str | None

    def __init__(
        self,
        url: str,
        content: str | None = None,
        error: str | None = None,
        title: str | None = None,
        library: str | None = None,
        source: str | None = None,
    ) -> None:
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "library", library)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "error", error)


# Kept as a public compatibility name for callers from Phase 3.
DocumentationResult = DocumentationPage


@dataclass(frozen=True)
class DocumentationSource:
    """Source metadata preserved in a generated documentation answer."""

    title: str | None
    url: str


@dataclass(frozen=True)
class GeneratedAnswer:
    """An LLM answer grounded in supplied documentation sources."""

    answer: str
    sources: list[DocumentationSource]


@dataclass(frozen=True)
class DocumentationComparison:
    """Structured comparison content generated from documentation context."""

    summary: str
    similarities: list[str]
    differences: list[str]
    practical_notes: list[str]


@dataclass(frozen=True)
class ComparisonResponse:
    """Comparison content with source metadata owned by the application."""

    summary: str
    similarities: list[str]
    differences: list[str]
    practical_notes: list[str]
    sources: dict[str, list[DocumentationSource]]
