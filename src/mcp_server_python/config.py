"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


@dataclass(frozen=True)
class Settings:
    """Configuration values used by the documentation server."""

    serper_api_key: str
    groq_api_key: str | None = None


@dataclass(frozen=True)
class GroqSettings:
    """Configuration required by the reusable Groq answer service."""

    api_key: str
    model: str


def load_settings() -> Settings:
    """Load and validate configuration from the environment and `.env`."""

    load_dotenv()
    serper_api_key = os.getenv("SERPER_API_KEY")
    if not serper_api_key:
        raise ConfigurationError(
            "SERPER_API_KEY is required. Add it to the environment or .env file."
        )

    return Settings(
        serper_api_key=serper_api_key,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    )


def load_groq_settings() -> GroqSettings:
    """Load and validate Groq configuration without requiring Serper."""

    load_dotenv()
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ConfigurationError(
            "GROQ_API_KEY is required to generate documentation answers."
        )

    return GroqSettings(
        api_key=groq_api_key,
        model=os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL,
    )