# Documentation Intelligence MCP Server

> An MCP server for searching, retrieving, understanding, and comparing official developer documentation using structured tools, asynchronous web retrieval, and grounded LLM generation.

## Overview

**Documentation Intelligence MCP Server** is a Python-based [Model Context Protocol (MCP)] server designed to make official developer documentation easier for AI applications and MCP-compatible clients to access and reason over.

Instead of allowing an LLM to rely entirely on its internal knowledge, the server retrieves documentation from **official library websites**, extracts the relevant content, and provides that information as trusted context to an LLM.

The server currently supports:

* Documentation search
* Official documentation retrieval
* Grounded documentation question answering
* Cross-library documentation comparison
* Structured source attribution
* Domain and URL validation
* Asynchronous HTTP requests
* Automated testing

The project is designed with a service-oriented architecture where MCP tools remain thin and reusable services handle search, retrieval, extraction, validation, and LLM interaction.

---

## Why This Project?

Developer documentation changes frequently, while LLMs may contain outdated or incomplete information.

A documentation-aware AI workflow should therefore:

1. Find the relevant official documentation.
2. Retrieve the actual documentation content.
3. Ground the model's response in that content.
4. Preserve the original documentation sources.
5. Prevent arbitrary or untrusted URLs from being fetched.
6. Return structured results that MCP clients can consume reliably.

This project implements that workflow through MCP tools.

---

## Key Features

### 🔎 Documentation Search

Search official documentation for supported libraries using Serper.

```text
search_docs
```

Returns structured search results containing information such as:

* Title
* URL
* Snippet
* Library
* Source/domain

---

### 📄 Documentation Retrieval

Retrieve and extract readable content from an official documentation page.

```text
get_documentation
```

The server:

* Validates the library
* Validates the URL
* Verifies the URL belongs to an approved documentation domain
* Fetches the page asynchronously
* Extracts readable content using Trafilatura
* Returns structured documentation data

---

### 🤖 Grounded Documentation Q&A

Ask questions about a supported library using retrieved official documentation as context.

```text
ask_docs
```

The workflow is:

```text
Question
   ↓
Official documentation search
   ↓
Relevant documentation retrieval
   ↓
Context limiting
   ↓
Groq LLM
   ↓
Grounded answer
   ↓
Verified sources
```

The model is instructed to use the supplied documentation as untrusted reference material rather than treating documentation content as system instructions.

---

### ⚖️ Cross-Library Documentation Comparison

Compare two supported libraries using documentation retrieved independently from both official sources.

```text
compare_docs
```

Example:

```text
FastAPI
    ↓
Official documentation
    ↓
Context A

UV
    ↓
Official documentation
    ↓
Context B

       ↓
     Groq
       ↓
Structured comparison
```

The comparison includes:

* Summary
* Similarities
* Differences
* Practical notes
* Sources for each library

---

### 🔐 URL and Domain Security

Documentation URLs are validated before fetching.

The server uses parsed HTTPS URLs and exact host/subdomain matching to prevent lookalike domains and unrelated hosts from being accessed.

For example, a malicious domain such as:

```text
https://openai.com.example.com
```

is not treated as an official OpenAI documentation domain.

Only documentation domains registered for supported libraries are allowed.

---

### 🧠 Grounded LLM Generation

The LLM does not independently decide which URLs should be cited.

Instead:

```text
Application
    ↓
retrieves documentation
    ↓
creates context
    ↓
LLM generates answer
    ↓
application constructs trusted sources
```

Model-generated source URLs are ignored.

This keeps source attribution under application control.

---

### ⚡ Asynchronous Processing

The project uses asynchronous Python for network-bound operations.

Technologies include:

* `httpx.AsyncClient`
* Async MCP tools
* Async Groq API calls

Trafilatura extraction is executed outside the MCP event loop so synchronous extraction does not block other asynchronous operations.

---

### 🧪 Automated Testing

The project includes tests covering:

* Library validation
* Documentation registry
* Search behavior
* HTTP failures
* Timeouts
* URL validation
* Malicious/lookalike domains
* Documentation extraction
* LLM failures
* Context limits
* Source integrity
* MCP tool behavior
* `ask_docs`
* `compare_docs`

The current test suite contains **55 tests**.

---

# Architecture

The project follows a layered architecture:

```text
                         MCP Client
                             │
                             ▼
                     ┌───────────────┐
                     │   MCP Server  │
                     └───────┬───────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
       search_docs   get_documentation   get_docs
            │                │
            └────────┬───────┘
                     ▼
             Documentation Services
                     │
             ┌───────┴────────┐
             │                │
             ▼                ▼
          Search           Fetch
          Service          Service
             │                │
             ▼                ▼
           Serper         HTTPX
                              │
                         Trafilatura
                              │
                              ▼
                     DocumentationPage
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
             ask_docs                 compare_docs
                │                           │
                └─────────────┬─────────────┘
                              ▼
                         LLM Service
                              │
                              ▼
                            Groq
                              │
                              ▼
                    Structured Response
```

---

# Project Structure

```text
mcp-server-python/
│
├── src/
│   └── mcp_server_python/
│       ├── __init__.py
│       ├── config.py
│       ├── documentation.py
│       ├── documentation_registry.py
│       ├── llm.py
│       ├── models.py
│       ├── search.py
│       └── server.py
│
├── tests/
│   ├── test_ask_docs.py
│   ├── test_compare_docs.py
│   ├── test_comparison_llm.py
│   ├── test_documentation_registry.py
│   ├── test_documentation_services.py
│   ├── test_get_documentation.py
│   ├── test_llm.py
│   └── test_search_docs.py
│
├── client.py
├── mcp_server.py
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
└── README.md
```

---

# Supported Libraries

The documentation registry currently supports:

| Library    | Identifier    |
| ---------- | ------------- |
| OpenAI     | `openai`      |
| LangChain  | `langchain`   |
| LlamaIndex | `llama-index` |
| uv         | `uv`          |
| FastAPI    | `fastapi`     |
| Pydantic   | `pydantic`    |

Library names are resolved case-insensitively.

The `LlamaIndex` alias is also supported.

The registry defines the official documentation domains that may be accessed by the application.

---

# MCP Tools

The server currently exposes five MCP tools.

## 1. `get_docs`

Legacy documentation lookup tool retained for compatibility.

```text
get_docs(query, library)
```

Example:

```text
get_docs("installation", "uv")
```

---

## 2. `search_docs`

Searches official documentation without fetching the resulting pages.

```text
search_docs(
    library,
    query,
    max_results=5
)
```

`max_results` is limited to prevent uncontrolled retrieval.

---

## 3. `get_documentation`

Fetches and extracts a specific official documentation page.

```text
get_documentation(
    library,
    url
)
```

The URL must belong to an approved documentation domain for the selected library.

---

## 4. `ask_docs`

Answers a developer question using retrieved official documentation.

```text
ask_docs(
    library,
    question,
    max_sources=3
)
```

Example:

```text
ask_docs(
    "uv",
    "How do I install uv?"
)
```

The resulting response contains:

```text
library
question
answer
sources
```

---

## 5. `compare_docs`

Compares two libraries using independently retrieved documentation.

```text
compare_docs(
    library_a,
    library_b,
    topic,
    max_sources_per_library=2
)
```

Example:

```text
compare_docs(
    "fastapi",
    "uv",
    "installation"
)
```

The response contains:

```text
library_a
library_b
topic

comparison:
    summary
    similarities
    differences
    practical_notes

sources:
    library_a
    library_b
```

---

# Technology Stack

| Technology    | Purpose                           |
| ------------- | --------------------------------- |
| Python        | Core implementation               |
| FastMCP       | MCP server and tool registration  |
| MCP stdio     | Local MCP communication           |
| httpx         | Asynchronous HTTP requests        |
| Serper        | Documentation search              |
| Trafilatura   | HTML/content extraction           |
| Groq          | LLM generation                    |
| python-dotenv | Environment configuration         |
| uv            | Dependency and project management |
| pytest        | Automated testing                 |

---

# Installation

## Prerequisites

Make sure the following are installed:

* Python 3.11+
* `uv`
* A Serper API key
* A Groq API key

---

## Clone the Repository

```bash
git clone https://github.com/Aarush-Pradhan/documentation-intelligence-mcp.git
cd mcp-server-python
```

---

## Install Dependencies

Using `uv`:

```bash
uv sync
```

---

# Configuration

Create a local `.env` file:

```env
SERPER_API_KEY=your_serper_api_key_here
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b
```

You can use `.env.example` as a template.

### Important

Never commit `.env` or real API keys to Git.

The `.env` file should remain local.

---

# Running the MCP Server

The server uses **stdio transport** for local MCP communication.

Start the server with:

```bash
uv run python mcp_server.py
```

The server is designed to communicate with MCP clients over standard input/output.

Do not print debugging information to stdout because stdout is used by the MCP protocol.

---

# Running the Development Client

The included development client starts the MCP server as a subprocess and communicates with it over stdio.

Run:

```bash
uv run python client.py
```

The client:

1. Starts the MCP server.
2. Establishes an MCP connection.
3. Discovers available tools.
4. Calls the selected tool.
5. Displays the returned result.

---

# Running Tests

Run the complete test suite:

```bash
uv run pytest
```

The project currently contains:

```text
55 tests
```

All tests are designed to run without requiring real Serper or Groq API calls where external services are mocked.

---

# Example Workflow

A typical documentation question follows this flow:

```text
Developer
    │
    │ "How do I install uv?"
    ▼
ask_docs
    │
    ▼
Library validation
    │
    ▼
Serper documentation search
    │
    ▼
Official uv documentation URLs
    │
    ▼
URL/domain validation
    │
    ▼
HTTP fetch
    │
    ▼
Trafilatura extraction
    │
    ▼
Context limiting
    │
    ▼
Groq
    │
    ▼
Grounded answer
    │
    ▼
Trusted source metadata
```

---

# Example Comparison Workflow

For a cross-library comparison:

```text
compare_docs(
    "fastapi",
    "uv",
    "installation"
)
```

The application independently retrieves documentation for each library:

```text
FastAPI
   │
   ├── Search
   ├── Validate
   └── Fetch
          │
          ▼
      Context A


uv
   │
   ├── Search
   ├── Validate
   └── Fetch
          │
          ▼
      Context B

          ↓
     Groq LLM
          ↓
Structured comparison
```

The two documentation contexts are explicitly separated before being supplied to the model.

---

# Context Management

Large documentation pages are not sent to the LLM without limits.

The application applies deterministic context limits.

Current limits include:

```text
Maximum characters per source: 12,000

Maximum total context: 30,000
```

This helps control:

* Context size
* LLM cost
* Request latency
* Uncontrolled input growth

Source metadata is preserved even when content is truncated.

---

# Error Handling

The application handles common failures without exposing internal stack traces.

Examples include:

* Missing API keys
* Unsupported libraries
* Invalid URLs
* Malformed URLs
* Lookalike domains
* Empty search results
* Malformed search responses
* HTTP failures
* HTTP timeouts
* Documentation extraction failures
* LLM failures
* LLM timeouts
* Invalid model output

Errors are returned as safe application-level responses.

---

# Security Considerations

Security is an important part of the documentation retrieval pipeline.

### Official Domain Validation

Only registered documentation domains are allowed.

### URL Validation

URLs are parsed and validated before fetching.

### Lookalike Domain Protection

Domains such as:

```text
example.com.evil.com
evil-example.com
```

are not accepted simply because they contain a trusted domain name.

### No Arbitrary URL Fetching

The application does not allow users or the LLM to arbitrarily instruct the server to fetch external websites.

### Prompt Injection Awareness

Retrieved documentation is treated as **untrusted data**.

Documentation content is explicitly separated from system instructions and user questions.

Instructions embedded inside documentation are not treated as commands.

### Source Integrity

LLM-generated URLs are not trusted.

Sources returned to the MCP client are constructed from documentation pages that were actually retrieved by the application.

---

# Design Principles

The project follows several core principles:

### Separation of Concerns

MCP tools handle protocol-level interaction while services handle application logic.

### Typed Data

Structured models are used instead of passing unstructured dictionaries throughout the application.

### Async I/O

Network-bound operations use asynchronous APIs.

### Security by Validation

External documentation URLs are validated before retrieval.

### Grounded Generation

LLM responses are generated from retrieved official documentation rather than relying solely on model knowledge.

### Source Attribution

Sources are generated from trusted application state rather than model-generated URLs.

### Controlled Context

Documentation size is bounded before being sent to the LLM.

### Testability

External APIs are mocked in automated tests so core application behavior can be tested independently.

---

# Testing Strategy

The test suite covers multiple layers of the application.

### Registry Tests

* Supported libraries
* Case-insensitive names
* Aliases
* Official domains
* Invalid domains

### Search Tests

* Successful searches
* Empty results
* Malformed responses
* HTTP failures
* Timeouts
* Duplicate URLs
* Missing URLs

### Documentation Tests

* Successful retrieval
* URL validation
* Domain validation
* HTTP failures
* Extraction failures
* Timeout behavior

### LLM Tests

* Successful generation
* API failures
* Timeout behavior
* Structured output validation

### `ask_docs` Tests

* Input validation
* Search orchestration
* Fetch failures
* Context limiting
* LLM integration
* Source integrity

### `compare_docs` Tests

* Library validation
* Independent retrieval
* Context separation
* Partial failures
* Complete failures
* Comparison generation
* Source integrity

---

# Project Status

Current MCP tool set:

```text
✓ get_docs
✓ search_docs
✓ get_documentation
✓ ask_docs
✓ compare_docs
```

Current verification:

```text
✓ 55 automated tests
✓ MCP stdio startup
✓ MCP tool discovery
✓ Documentation search
✓ Documentation retrieval
✓ Grounded LLM question answering
✓ Cross-library comparison
✓ Source attribution
✓ URL/domain validation
✓ Error handling
```

---

# Future Improvements

The current version intentionally focuses on a clean and understandable architecture.

Potential future improvements include:

* Search-result caching
* Documentation freshness tracking
* Improved result ranking
* Concurrent multi-page retrieval
* More detailed observability
* CI-based automated testing
* Additional supported documentation libraries
* Version-aware documentation retrieval

These are intentionally outside the current core implementation.

---

# What I Learned

This project explores practical challenges involved in building an MCP-based AI application, including:

* Designing MCP tools around reusable services
* Asynchronous API integration
* External documentation retrieval
* HTML content extraction
* Secure URL validation
* Structured data modeling
* LLM grounding
* Prompt injection considerations
* Context-size management
* Source attribution
* Cross-document reasoning
* Automated testing of AI-assisted workflows

---

# License

This project is intended for educational and portfolio purposes.

Add an appropriate open-source license here if the repository is later published under one.

---

# Author

**Aarush Pradhan**

B.Tech Computer Science & Information Technology

Interested in backend engineering, AI-assisted systems, APIs, and developer tooling.
