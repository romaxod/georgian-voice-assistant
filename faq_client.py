"""Step 2.4: the client side of the ჯიხვი FAQ MCP server. graph.py's lookup node calls the tool here.

FaqClient starts mcp_server.py as a subprocess (stdio transport) and keeps that one connection open
for the whole chat, because starting the server costs a few seconds and a lookup only milliseconds.
Every way the call can fail across the process boundary becomes a FaqToolError:

    the server answered isError (e.g. its database failed)   retryable: the server is fine, the call may work
    no answer within LOOKUP_TIMEOUT (server hung)             not retryable; restart the server
    the connection closed (server killed or crashed)          not retryable; restart the server
    the server can't start, or never connected                not retryable
    the answer doesn't have the shape we expect               not retryable (a bug on one side)

"Retryable" means calling again on the same connection may help. After a timeout or a closed
connection it can't: the server has to be restarted first.

The MCP SDK uses anyio task groups, which must be closed by the same task that opened them. LangGraph
runs each node in its own task, so the lookup node can't restart the server itself: it only marks the
connection broken, and the chat loop (the task that owns the connection) restarts it before the next
turn with ensure_connected().

Run:  python faq_client.py ბარათი      start the server, call lookup_faq once, print the entries
"""
import asyncio
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import Client, MCPError, StdioServerParameters
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT

SERVER_SCRIPT = Path(__file__).parent / "mcp_server.py"
TOOL_NAME = "lookup_faq"
CONNECT_TIMEOUT = 20  # seconds to start the server and finish the handshake (measured: 3-4 s on /mnt/c)
LOOKUP_TIMEOUT = 5    # seconds for one tool call (measured: a few ms); the reply is spoken, so keep it short


class FaqToolError(Exception):
    """The FAQ lookup failed. `retryable` says whether calling again right away may help."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class FaqClient:
    """One MCP connection to mcp_server.py. Use as `async with FaqClient() as faq:`, then
    `await faq.lookup(topic)`. The task that enters it must also call ensure_connected() and exit it."""

    def __init__(self, server_args: list[str] | None = None):
        # sys.executable is the venv's python, so the server runs with the same packages as we do.
        self.params = StdioServerParameters(command=sys.executable,
                                            args=server_args or [str(SERVER_SCRIPT)])
        self._client: Client | None = None
        self._stack: AsyncExitStack | None = None  # closes the Client (and stops the subprocess)
        self.broken = False   # set by lookup() when the connection should be restarted
        self.last_error = ""  # why the last connect failed, for the chat to print

    async def __aenter__(self) -> "FaqClient":
        await self.ensure_connected()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._close()

    @property
    def connected(self) -> bool:
        return self._client is not None and not self.broken

    async def ensure_connected(self) -> bool:
        """(Re)start the server if there's no working connection. Returns whether there is one now.
        Never raises: a failure is kept in last_error, and lookup() will then hand off."""
        if self.connected:
            return True
        await self._close()  # an old, broken connection: stop its subprocess first
        stack = AsyncExitStack()
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                # Entering Client starts the subprocess and runs the MCP handshake (initialize, or
                # server/discover on a 2026-07-28 server).
                self._client = await stack.enter_async_context(Client(self.params))
        except Exception as e:  # noqa: BLE001  (any failure to start is reported the same way)
            await stack.aclose()
            self._client = None
            self.last_error = describe_error(e)
            return False
        self._stack, self.broken, self.last_error = stack, False, ""
        return True

    async def _close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:  # noqa: BLE001  (closing a dead connection may complain; it's gone anyway)
                pass
        self._client, self._stack = None, None

    async def lookup(self, topic: str) -> list[dict]:
        """Call the lookup_faq tool. Returns its entries (dicts with id, topic, question, answer),
        or raises FaqToolError."""
        if not self.connected:
            raise FaqToolError(f"the FAQ server isn't running ({self.last_error or 'connection lost'})",
                               retryable=False)
        try:
            result = await self._client.call_tool(TOOL_NAME, {"topic": topic},
                                                  read_timeout_seconds=LOOKUP_TIMEOUT)
        except MCPError as e:
            # The SDK reports transport problems as JSON-RPC errors with these codes.
            # A hung or dead server won't answer a retry; the chat loop restarts it before the next turn.
            self.broken = True
            if e.code == REQUEST_TIMEOUT:
                raise FaqToolError(f"the FAQ server didn't answer within {LOOKUP_TIMEOUT} s",
                                   retryable=False) from e
            if e.code == CONNECTION_CLOSED:
                raise FaqToolError("the connection to the FAQ server closed", retryable=False) from e
            raise FaqToolError(f"MCP error {e.code}: {e.error.message}", retryable=False) from e

        if result.is_error:
            # The tool ran and reported a failure (a ToolError on the server); the text says why.
            text = " ".join(getattr(block, "text", "") for block in result.content).strip()
            raise FaqToolError(f"the FAQ server reported: {text or 'an error'}", retryable=True)
        # The other process is a trust boundary: check the shape before the graph uses it.
        entries = (result.structured_content or {}).get("results")
        if not isinstance(entries, list) or not all(isinstance(e, dict) and "answer" in e for e in entries):
            raise FaqToolError("the FAQ server returned an unexpected result", retryable=False)
        return entries


def describe_error(error: BaseException) -> str:
    """A one-line reason. Errors raised inside the SDK's task groups arrive wrapped in (nested)
    ExceptionGroups, so unwrap them to the first real error."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    if isinstance(error, TimeoutError):
        return f"no handshake within {CONNECT_TIMEOUT} s"
    if isinstance(error, MCPError):
        return f"MCP error {error.code}: {error.error.message}"
    return f"{type(error).__name__}: {error}"


async def _demo(topic: str) -> None:
    started = time.perf_counter()
    async with FaqClient() as faq:
        if not faq.connected:
            sys.exit(f"Error: couldn't start the FAQ server: {faq.last_error}")
        connected = time.perf_counter()
        try:
            entries = await faq.lookup(topic)
        except FaqToolError as e:
            sys.exit(f"Error: {e}")
        done = time.perf_counter()
    for entry in entries:
        print(f"{entry['id']}: {entry['question']}")
    print(f"({len(entries)} entries; connect {connected - started:.2f} s, call {(done - connected) * 1000:.0f} ms)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python faq_client.py <topic>")
    asyncio.run(_demo(sys.argv[1]))
