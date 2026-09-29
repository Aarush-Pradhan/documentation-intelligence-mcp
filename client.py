import asyncio
import json
import os
import sys
import textwrap
from collections.abc import Sequence

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


try:
  reconfigure = getattr(sys.stdout, "reconfigure", None)
  if callable(reconfigure):
    reconfigure(encoding="utf-8", errors="replace")
except OSError:
  pass


SEPARATOR = "=" * 76


def _terminal_symbol(symbol: str, fallback: str) -> str:
  encoding = sys.stdout.encoding or "utf-8"
  try:
    symbol.encode(encoding)
  except UnicodeEncodeError:
    return fallback
  return symbol


CHECKMARK = _terminal_symbol("✓", "[ok]")
BULLET = _terminal_symbol("•", "-")
ARROW = _terminal_symbol("→", "->")

server_params = StdioServerParameters(
  command=sys.executable,
  args=["mcp_server.py"],
  env=dict(os.environ),
  cwd=os.path.dirname(os.path.abspath(__file__)),
)


def print_tool_discovery(tool_names: list[str]) -> None:
  """Display dynamically discovered tools in a stable order."""

  print(SEPARATOR)
  print("DOCUMENTATION INTELLIGENCE MCP SERVER")
  print("Available MCP Tools")
  print()
  for tool_name in sorted(tool_names):
    print(f"{CHECKMARK} {tool_name}")
  print(SEPARATOR)


def _wrapped_text(value: object, width: int = 72) -> str:
  return textwrap.fill(
    str(value), width=width, break_long_words=False, break_on_hyphens=False
  )


def _print_bullets(values: object) -> None:
  if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
    print(f"{BULLET} None reported")
    return
  for value in values:
    print(
      textwrap.fill(
        str(value),
        width=72,
        initial_indent=f"{BULLET} ",
        subsequent_indent="  ",
        break_long_words=False, break_on_hyphens=False,
      )
    )


def _display_library_name(value: object) -> str:
  names = {
    "fastapi": "FastAPI", "pydantic": "Pydantic",
    "llama-index": "LlamaIndex", "openai": "OpenAI",
  }
  text = str(value)
  return names.get(text.lower(), text)


def _print_sources(sources: object) -> None:
  if not isinstance(sources, dict):
    print("None reported")
    return
  for library, library_sources in sources.items():
    print(_display_library_name(library))
    if not isinstance(library_sources, list) or not library_sources:
      print(f"{ARROW} None reported")
      print()
      continue
    for source in library_sources:
      url = source.get("url") if isinstance(source, dict) else source
      print(f"{ARROW} {url}")
    print()


def _print_error(message: object) -> None:
  print(SEPARATOR)
  print("ERROR")
  print()
  print(_wrapped_text(message))
  print(SEPARATOR)


def _parse_tool_response(
  contents: Sequence[object],
) -> tuple[dict[str, object] | None, str]:
  raw_parts = [
    content.text for content in contents if isinstance(content, TextContent)
  ]
  raw = "\n".join(raw_parts)
  try:
    payload = json.loads(raw)
  except (json.JSONDecodeError, TypeError):
    return None, raw
  return payload if isinstance(payload, dict) else None, raw


def print_comparison(contents: Sequence[object]) -> None:
  """Render a structured comparison response without printing raw JSON."""

  payload, raw = _parse_tool_response(contents)
  if payload is None:
    _print_error(f"Comparison response could not be parsed:\n\n{raw or 'No response content received.'}")
    return
  if payload.get("error"):
    _print_error(payload["error"])
    return

  comparison = payload.get("comparison")
  if not isinstance(comparison, dict):
    _print_error("The comparison response did not contain comparison data.")
    return

  print(SEPARATOR)
  print("DOCUMENTATION COMPARISON")
  print(f"Library A : {_display_library_name(payload.get('library_a', ''))}")
  print(f"Library B : {_display_library_name(payload.get('library_b', ''))}")
  print(f"Topic : {payload.get('topic', '')}")
  print()
  print("---")
  print("## SUMMARY")
  print(_wrapped_text(comparison.get("summary", "No summary reported.")))
  print()
  print("---")
  print("## SIMILARITIES")
  _print_bullets(comparison.get("similarities"))
  print()
  print("---")
  print("## DIFFERENCES")
  _print_bullets(comparison.get("differences"))
  print()
  print("---")
  print("## PRACTICAL NOTES")
  _print_bullets(comparison.get("practical_notes"))
  print()
  print("---")
  print("## SOURCES")
  _print_sources(payload.get("sources"))
  print(SEPARATOR)
  print("COMPARISON COMPLETE")
  print(SEPARATOR)


async def main() -> None:
  async with stdio_client(server_params) as (read_stream, write_stream):
    async with ClientSession(read_stream, write_stream) as session:
      await session.initialize()
      tools_response = await session.list_tools()
      print_tool_discovery([tool.name for tool in tools_response.tools])

      try:
        result = await session.call_tool(
          "compare_docs",
          arguments={
            "library_a": "fastapi",
            "library_b": "uv",
            "topic": "installation",
            "max_sources_per_library": 2,
          },
        )
      except Exception:
        _print_error("The comparison request failed.")
        return
      print_comparison(result.content)


if __name__ == "__main__":
  asyncio.run(main())