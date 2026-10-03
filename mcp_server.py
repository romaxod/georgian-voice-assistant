"""Step 2.3: the ჯიხვი FAQ lookup as an MCP server (stdio transport).

The search itself stays in faq.py. This file only puts it behind the Model Context Protocol, so any
MCP client (the MCP Inspector now, graph.py in step 2.4, or Claude Desktop) can discover the tool and
call it without importing our Python code.

stdio transport: the client starts this file as a subprocess and they exchange JSON-RPC messages over
its stdin/stdout. So stdout belongs to the protocol: never print() here. Logs go to stderr.

Run:  python mcp_server.py                     waits for a client on stdin (Ctrl+C to stop)
      npx -y @modelcontextprotocol/inspector .venv/bin/python mcp_server.py
                                                opens the Inspector in the browser
"""
import logging
import sqlite3
import sys
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from faq import lookup_faq as search_faq

MAX_TOPIC_CHARS = 200  # same limit as graph.py: a search query is a few words

# basicConfig writes to stderr by default; set it explicitly because stdout would corrupt the protocol.
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[faq-server] %(message)s")
log = logging.getLogger("faq-server")

# `instructions` is sent to the client when it connects; a host app may add it to the model's prompt.
mcp = MCPServer(
    "jikhvi-faq",
    version="0.1.0",
    instructions="Read-only search over the FAQ of ჯიხვი, a fictional Georgian mobile operator.",
)


# The return type becomes the tool's outputSchema, and the result is sent twice: as JSON text in
# `content` (for clients that only read text) and as `structuredContent` (for code that wants fields).
class FaqEntry(BaseModel):
    id: str
    topic: str
    question: str
    answer: str


class LookupResult(BaseModel):
    results: list[FaqEntry]
    note: str | None = Field(None, description="Set when nothing matched.")


# The function's name, docstring and type hints become the tool's name, description and inputSchema.
# The SDK validates every call against that schema before the function runs. Annotations are hints for
# the client (e.g. "safe to call without asking"), not something the protocol enforces.
@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False))
def lookup_faq(
    topic: Annotated[str, Field(
        min_length=1, max_length=MAX_TOPIC_CHARS,
        description="2-4 Georgian keywords for what the customer asks about, e.g. "
                    "\"როუმინგი ევროპა\" or \"eSIM აქტივაცია\". Keywords, not the whole question.",
    )],
) -> LookupResult:
    """Search the ჯიხვი FAQ: plans and prices, extra internet, roaming, international calls, SIM and
    eSIM, PIN/PUK, balance, number porting, contract, branches and hours, contacting an operator,
    5G coverage. Returns up to 3 entries, best match first; an empty list means nothing matched."""
    if not topic.strip():  # min_length=1 still lets "   " through
        raise ToolError("topic must contain at least one word")
    try:
        results = search_faq(topic)
    except sqlite3.Error as e:
        # ToolError = a failure we expected: the client gets isError=true with this message. Any other
        # exception would reach the client only as "Error executing tool lookup_faq".
        log.error("lookup_faq(%r) failed: %r", topic, e)
        raise ToolError(f"the FAQ database failed ({type(e).__name__})") from e
    log.info("lookup_faq(%r) -> %d result(s)", topic, len(results))
    if not results:
        return LookupResult(results=[], note="nothing matched; don't guess, offer a human operator")
    return LookupResult(results=[FaqEntry(**r) for r in results])


if __name__ == "__main__":
    mcp.run()  # default transport is stdio
