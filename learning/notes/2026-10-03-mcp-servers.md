# MCP: protocol, servers and the Python SDK

Date: 2026-10-03. Checked against the MCP docs and spec (pages opened today, see section 7C), the Python SDK v2 migration page, the Inspector repo docs, and by running `mcp_server.py` by hand. Installed: `mcp==2.3.0`, `mcp-types==2.3.0`. MCP moves fast: the newest spec revision is **2026-07-28**; the installed SDK still speaks **2025-11-25** (see section 1, "Version note"). Line-by-line code is in `docs/code/mcp_server.py.md`. Earlier notes: [where MCP fits](2026-10-02-agentic-architectures.md), [function calling](2026-10-03-function-calling-responses-api.md).

## 1. What you're learning, and why it matters

**Problem.** In 1.4 the tool schema and the Python function lived inside our own program (`chat.py`/`graph.py`). Every app that wants the FAQ search must copy that code, and every new tool means editing the app. **MCP (Model Context Protocol)** is an open standard so a tool can live in its own process; any MCP-aware app discovers its tools at runtime and calls them. Think "USB-C for tools": one plug, many apps.

**Host, client, server** (architecture page):
- **Host:** the AI application (Claude Desktop, Claude Code, our `graph.py` in 2.4). It talks to the LLM and decides what to do.
- **Client:** a component inside the host that keeps **one connection to one server**. Two servers means two clients.
- **Server:** a program that exposes capabilities (tools, resources, prompts). "Local" or "remote" describes where it runs, not what it is.
- **Short answer:** "An MCP server exposes tools and data over a standard protocol. An MCP client lives inside the host application, holds one connection to one server, discovers what the server offers and calls it on the model's behalf. The host is the app that owns the LLM and the user; it creates one client per server."

**Messages.** MCP uses **JSON-RPC 2.0**, three message kinds: a *request* (`method`, `params`, an `id`), a *response* (same `id`, `result` or `error`), a *notification* (no `id`, nobody replies). The `id` pairs answers with questions.

**Lifecycle (what 2.3.0 does today).** I sent these lines to our server's stdin by hand and got real answers:
1. client -> `initialize` (its `protocolVersion`, capabilities, `clientInfo`); server answers with its own version, capabilities, `serverInfo` and the `instructions` string (ours: "Read-only search over the FAQ of ჯიხვი...").
2. client -> notification `notifications/initialized`.
3. client -> `tools/list`, later `tools/call` with `name` and `arguments`.
4. Shutdown: the client closes stdin; the server exits.

**Version note.** The 2026-07-28 spec removed the `initialize` handshake: every request now carries `_meta` with the protocol version and capabilities, and a `server/discover` request replaces it (stateless protocol). The installed 2.3.0 server answered `initialize` with `protocolVersion: 2025-11-25` and replied `-32601 Method not found` to `server/discover`. Spec pages say clients probe `server/discover` first and fall back to `initialize`. Expect the details to keep changing; the `tools/list` / `tools/call` ideas stay.

**Primitives** a server can expose: **tools** (model-controlled: the LLM decides to call them), **resources** (app-controlled: data the app attaches as context, e.g. file contents), **prompts** (user-controlled: reusable templates the user picks). We expose one tool only: the scope guardrail in PROJECT_CONTEXT.md says one read-only MCP tool. (Our SDK server advertises empty prompts/resources capabilities; that is just the default.)

**Tool definition.** `name`, `description`, `inputSchema` (JSON Schema), optional `outputSchema`, optional `annotations`. A result has `content` (list of blocks, e.g. `{"type":"text","text":...}`), optionally `structuredContent` (JSON matching `outputSchema`; the spec says also send it as text for older clients), and `isError`.
- **Two kinds of error.** *Protocol error* = JSON-RPC `error` (unknown tool, malformed request; the model can rarely fix it). *Tool execution error* = a normal result with `isError: true` and a message the model can read and react to (bad input, API failure). Clients SHOULD show the second kind to the model.
- **Versus OpenAI function calling (1.4):** there you send the schema with each request and run the function yourself. In MCP the schema **and** the execution live in the server process; the host fetches the schema with `tools/list` and forwards the model's call with `tools/call`. The model still sees an ordinary function-calling tool; the host translates.
- **Annotations** (`readOnlyHint`, `idempotentHint`, `destructiveHint`, `openWorldHint`) are **hints**. The spec: clients "MUST consider tool annotations to be untrusted unless they come from trusted servers"; the SDK docstring says never base tool-use decisions on them from untrusted servers. Ours say read-only, idempotent, closed-world; a host may use that to skip a confirmation prompt, only if it trusts us.

**Security.** A server's `description` goes straight into the model's context, so a malicious server can hide instructions there (**tool poisoning**, a form of prompt injection); tool *results* are another injection channel. Rules: connect only to servers you trust; **least privilege** (read-only tools, no write/transfer tools without need); allow-list which servers and tools a host can use; show tool inputs to the user; keep a **human confirmation** for anything that changes state; log tool calls for audit; servers validate every input and rate-limit (the spec's Security Considerations list). Production angle: an assistant that can only look up FAQ entries cannot change an account even if the model is tricked.

**Transports.**
- **stdio:** the client starts the server as a subprocess; one JSON-RPC message per line on stdin/stdout. **stdout is reserved for the protocol**; logs go to **stderr** (spec: the server MUST NOT write anything to stdout that is not a valid MCP message). Best for local tools: no network, no auth.
- **Streamable HTTP:** HTTP POST to a single MCP endpoint (often `/mcp`), optional SSE streaming; for remote/shared servers; auth via headers/OAuth. The older HTTP+SSE transport is legacy/deprecated.
- Choose stdio for a local, one-user tool like ours; HTTP when many clients or machines need it (deployment).

**Python SDK v2 (`mcp` 2.3.0).**
- Server: `from mcp.server import MCPServer`; `@mcp.tool()` turns function name -> tool `name`, docstring -> `description`, type hints -> `inputSchema`. `Annotated[str, Field(min_length=1, max_length=200)]` becomes `minLength`/`maxLength`, and the SDK validates every call **before** your function runs. A Pydantic return type becomes `outputSchema`; the result is sent as JSON text and as `structuredContent`. `mcp.run()` defaults to stdio.
- Errors: `ToolError` (import from `mcp.server.mcpserver.exceptions`) = anticipated failure, the message reaches the client, logged at INFO. Any other exception: the client only sees "Error executing tool <name>" and the server logs a traceback. Use it so internal details (paths, SQL) never leak to the model.
- Client: `from mcp import Client, StdioServerParameters`; `async with Client(StdioServerParameters(command=..., args=[...], cwd=...)) as client:` then `await client.call_tool("lookup_faq", {"topic": "ბარათი"})` returns a `CallToolResult` with `.is_error`, `.content`, `.structured_content`. (`async`/`await` is taught in step 2.4; for now read it as "wait for the subprocess".)
- **Version gotcha:** most tutorials use `from mcp.server.fastmcp import FastMCP` (v1). In v2 that import raises `ModuleNotFoundError`; the class is now `MCPServer` ([migration guide](https://py.sdk.modelcontextprotocol.io/v2/migration/)). Separately, **FastMCP** (gofastmcp.com, maintained by Prefect, repo `PrefectHQ/fastmcp`, originally by jlowin) is a different, actively maintained package whose early API was folded into the official SDK in 2024. Search results mix the two; check which `import` a tutorial uses.

## 2. In this repo

`mcp_server.py` wraps `faq.lookup_faq` in one tool. The search logic stays in `faq.py`: one implementation, MCP is only a boundary. `chat.py`/`graph.py` still import `faq.py` directly until 2.4 switches the graph to an MCP client. Real outputs from this step:
- `tools/list` (via Inspector CLI): `inputSchema.properties.topic` = `{"type":"string","minLength":1,"maxLength":200,...}`, `required:["topic"]`; `outputSchema` `LookupResult` with `$defs.FaqEntry`; `annotations` `readOnlyHint/idempotentHint: true`, `openWorldHint: false`.
- `tools/call` with `topic=ბარათი`: `isError:false`, `structuredContent` with 3 entries (sim-lost, sim-replace, balance-topup), `content` = one text block; stderr: `[faq-server] lookup_faq('ბარათი') -> 3 result(s)`.
- Break tests:

| Input | Result | Who rejected it |
|---|---|---|
| `"   "` | `ToolError`: "topic must contain at least one word" | our function |
| 300 chars | `isError:true`, "String should have at most 200 characters [type=string_too_long]" | SDK; our code never ran |
| no `topic` | "Field required" | SDK |
| `topic = 5` | "Input should be a valid string" | SDK |
| tool `block_card` (Python client) | `isError:true`, "Unknown tool: block_card" | SDK (Inspector CLI stops earlier, client-side `tool_not_found`) |
| DB dir missing | "Error executing tool lookup_faq: the FAQ database failed (OperationalError)" | our `ToolError`, cause hidden |
| `x' OR '1'='1` | `{"results": [], "note": "nothing matched; ..."}` | parameterized query |

- **stdout test:** a `print("searching for", topic)` inside the tool made the 2.3.0 client log `Failed to parse JSONRPC message from server` (pydantic `json_invalid`), skip the line, and the call still worked. The SDK is lenient, but it is a protocol violation: stricter clients may disconnect, and a printed line that looks like JSON-RPC could be misread.

## 3. How the pieces fit

```
user -> host (graph.py, 2.4) --LLM--> decides to call lookup_faq
          |  MCP client (1 per server)
          |  stdin/stdout, JSON-RPC lines   (stderr = logs)
          v
       mcp_server.py (MCPServer) -> faq.py -> SQLite
```

## 4. Related tools

- **Plain function calling (1.4):** simplest for one app; MCP pays off when tools are shared across apps or owned by another team.
- **FastMCP (Prefect):** third-party framework with extras (proxying, auth, testing); we use the official SDK to stay close to the spec.
- **LangChain/LangGraph adapters** (`langchain-mcp-adapters`) turn MCP tools into LangChain tools; relevant in 2.4, not verified here.
- **OpenAPI/REST:** also describes tools, but has no discovery-by-model, annotations or stdio story.

## 5. Inspector

`npx -y @modelcontextprotocol/inspector <command> <args>`; for us `npx -y @modelcontextprotocol/inspector .venv/bin/python mcp_server.py`. Source: Inspector repo README and `docs/environment-variables.md` (opened today; the repo is the **v2** line, npm latest seen 2.9.0).
- **Web UI (default):** a Node backend plus browser app. Defaults (v2 docs): UI on `http://localhost:6274`, MCP Apps sandbox on 6275 (v1 had a 6277 proxy; v2 does not list one). The backend spawns processes, so it is guarded by a **random API token per launch**, shown in the launch banner (`MCP_INSPECTOR_API_TOKEN` sets a fixed one; `DANGEROUSLY_OMIT_AUTH=true` disables it, don't). It binds `127.0.0.1` only. Use it to connect, press List Tools, fill the form, Call, and read the server's stderr notifications.
- **`--cli` mode:** same, headless: `--method tools/list`, `--method tools/call --tool-name lookup_faq --tool-arg topic=ბარათი`, `--method initialize` (connect-only probe). If the server has its own flags, put `--` between target and Inspector options (smoke-testing doc).
- **Quirks seen here:** `--tool-arg "topic="` fails ("Invalid parameter format... Use key=value format."), so the CLI can't send an empty string; an unknown tool fails client-side (`tool_not_found`) before any call; a result with `isError` makes the CLI exit non-zero (`tool_is_error`), handy in scripts. Stderr from the server mixes into your terminal; split it (`2>log`, see the CLI basics note).
- `--tui` is a third, terminal UI mode.

## 6. Hands-on exercises

1. **Raw protocol.** `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"hand","version":"0"}}}' '{"jsonrpc":"2.0","method":"notifications/initialized"}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | .venv/bin/python mcp_server.py 2>/dev/null`. Check: two JSON lines back (ids 1 and 2); id 1 contains `instructions`; no answer for the notification.
2. **Second tool.** Add a read-only `@mcp.tool()` (e.g. `list_topics`) to a copy of the server. Check: `--method tools/list` shows two tools, and its docstring is the description.
3. **ValueError vs ToolError.** Make the function `raise ValueError("secret path /x")`. Check: the client sees only "Error executing tool lookup_faq", and the server's stderr has the traceback. Swap in `ToolError` and compare.
4. **Break the validator.** Call with 300 chars and with `topic=5`; confirm the stderr line `lookup_faq(...)` never appears (function didn't run).
5. **Claude Code as host.** From the repo: `claude mcp add faq -- /mnt/c/prog/"ABSTR ASSN"/georgian-voice-assistant/.venv/bin/python /mnt/c/prog/"ABSTR ASSN"/georgian-voice-assistant/mcp_server.py` (syntax per Claude Code docs: options before the name, `--` before the command; default scope is local). Then `claude mcp list` should show it connected. Remove with `claude mcp remove faq`. Not run here; the server needs `cwd`-independent paths (it imports `faq.py` next to itself, which works).

## 7. Self-check

1. Which is the host and which is the client in `graph.py` + `mcp_server.py`, and why one client per server?
2. Why must a stdio server never `print()` to stdout?
3. A 300-character topic comes back `isError: true` but our function never ran. Who checked it?
4. `ToolError` vs `ValueError`: what does the client see in each case?
5. Why can't you trust `readOnlyHint` from any server?
6. Why do we pick stdio, and when would you pick Streamable HTTP?

<details><summary>Answers</summary>

1. `graph.py` is the host (owns the LLM and user); the MCP client inside it holds the connection to `mcp_server.py`. One client per server keeps connections and capabilities separate. 2. stdout carries the JSON-RPC messages; other text corrupts the stream. Log to stderr. 3. The SDK validated the arguments against `inputSchema` before calling the function. 4. `ToolError`: the client sees your message with `isError: true`. `ValueError`: only "Error executing tool lookup_faq", details stay in the server log. 5. Annotations are self-declared by the server; a malicious one can claim read-only. 6. stdio: local subprocess, no network or auth, one user. HTTP: remote or shared servers with many clients, needs authentication.
</details>

## 8. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | the repo's server, hands-on | 45 min |
| B. Another AI tutor | quizzing on concepts and security | 30 min |
| C. Primary docs | exact protocol facts | 1-2 h |
| D. Course/video | big picture, building a server and client | 2 h |

**Start here:** C (Architecture page + Tools page), then D (the DeepLearning.AI course).

**A.** Paste in a main session: "Read learning/notes/2026-10-03-mcp-servers.md and walk me through exercises 1-4 against mcp_server.py, one at a time, explaining each output."

**B.** NotebookLM (add the C links as sources) or ChatGPT/Gemini. Prompt: "Using only https://modelcontextprotocol.io/docs/learn/architecture, https://modelcontextprotocol.io/specification/latest/server/tools and https://modelcontextprotocol.io/specification/latest/basic/transports, quiz me on host vs client vs server, tool errors (isError vs JSON-RPC error), stdio vs Streamable HTTP and tool poisoning. One question at a time, then correct me."

**C.** All opened 2026-10-03.
- Architecture overview: https://modelcontextprotocol.io/docs/learn/architecture (host/client/server, layers, primitives, worked JSON-RPC examples)
- Spec, Tools: https://modelcontextprotocol.io/specification/latest/server/tools (schemas, structuredContent, two error kinds, security)
- Spec, Transports: https://modelcontextprotocol.io/specification/latest/basic/transports and its stdio page https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio (stdout/stderr rules)
- Lifecycle (legacy handshake that 2.3.0 still uses): https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle ; versioning: https://modelcontextprotocol.io/specification/latest/basic/lifecycle (redirects to the "Versioning and Compatibility" page)
- Python SDK docs: https://py.sdk.modelcontextprotocol.io/ and the v2 migration guide https://py.sdk.modelcontextprotocol.io/v2/migration/
- Inspector: https://github.com/modelcontextprotocol/inspector (README, `docs/environment-variables.md`, `docs/cli-smoke-testing.md`)
- Claude Code MCP page: https://code.claude.com/docs/en/mcp (`claude mcp add`, `.mcp.json`)
- FastMCP (the other project): https://gofastmcp.com

**D.**
- "MCP: Build Rich-Context AI Apps with Anthropic", DeepLearning.AI with Anthropic, instructor Elie Schoppik, intermediate, about 2 h, free at the time of checking: https://www.deeplearning.ai/short-courses/mcp-build-rich-context-ai-apps-with-anthropic/ (it likely teaches the v1 `FastMCP` API; apply the rename).
- "Introduction to Model Context Protocol", Anthropic Academy, free, Python SDK, tools/resources/prompts, Inspector: https://anthropic.skilljar.com/introduction-to-model-context-protocol
- A YouTube video: I couldn't confirm one by title and creator. Search "MCP Python SDK build a server tutorial" and check the video's date, since pre-2026 videos use the v1 import.
