# Python async/await and asyncio

Date: 2026-10-03. Checked on Python 3.14.0 (docs pages for 3.14 opened today, `asyncio/runners.py` read in the venv), `anyio` 4.15.1, `mcp` 2.3.0, `langgraph` 1.2.12. Exercise outputs below were run here. Code explanation for `faq_client.py` and `graph.py` is in `docs/code/`; this note teaches the concept. Related: [MCP client side](2026-10-03-mcp-servers.md), [LangGraph async graphs](2026-10-03-langgraph-in-practice.md), [Unix signals](2026-10-03-unix-processes-and-signals.md).

## 1. What you're learning, and why it matters

**Problem.** A program that talks to a network or a subprocess spends most of its time waiting. With plain code, waiting blocks everything: two 1 s requests take 2 s. The MCP Python client only exists as `async` code, so step 2.4 forced the whole graph to become async.

**The idea.** One thread runs many **coroutines**; each one says "I'm waiting, run someone else" at an `await`. Compare threads: the OS switches threads at any moment (you need locks); asyncio switches only at `await` (you see where). Async is for **waiting** (I/O), not for CPU-heavy work.

- **Coroutine function:** `async def f(): ...`. **Calling it does not run it**; it returns a **coroutine object** (`<class 'coroutine'>`). Forgetting `await` gives the warning "coroutine ... was never awaited".
- **`await x`:** run coroutine/task `x` and pause the current coroutine until it is done; other coroutines run meanwhile. Only allowed inside `async def`.
- **Event loop:** the scheduler that runs ready coroutines and wakes sleeping ones when their I/O finishes.
- **`asyncio.run(main())`:** creates a loop, runs one coroutine to the end, closes the loop. Call it once, at the top (`graph.py main()`).
- **Task:** a coroutine scheduled on the loop to run concurrently. `asyncio.create_task(coro())` starts it now; `await task` collects the result. `asyncio.gather(a(), b())` runs several and returns their results in order. `asyncio.TaskGroup` is the newer, safer way (waits for all; cancels siblings on error).
- **`async with`** calls `__aenter__`/`__aexit__` (which may await: open a connection, close it). **`async for`** uses `__aiter__`/`__anext__` (each item may need waiting: `graph.astream(...)` yields node updates as they finish). Both come from PEP 492.
- **`contextlib.AsyncExitStack`:** a stack of context managers you can open in one place and close in another. `async with` ties enter and exit to one block; `FaqClient` opens the MCP client in `ensure_connected()` and closes it in `_close()`, different methods and different times. `await stack.enter_async_context(cm)` enters; `await stack.aclose()` exits everything in reverse.
- **`asyncio.timeout(s)`:** `async with asyncio.timeout(20):` cancels the block after 20 s and raises `TimeoutError`. Used around the server startup handshake.
- **Blocking inside a coroutine freezes everything.** `time.sleep(2)` or `input()` doesn't `await`, so the loop can't run anything else. Fix for real work: `await asyncio.to_thread(blocking_fn)` (runs it in a worker thread).
- **Cancellation.** `task.cancel()` makes the task raise `asyncio.CancelledError` at its current `await`. It is a `BaseException`, not `Exception`, so a plain `except Exception` doesn't swallow it. Rule: clean up (`finally`), then re-raise.

**anyio and structured concurrency.** The MCP SDK uses **anyio**, a layer over asyncio (and Trio) that adds **task groups** and **cancel scopes**. *Structured concurrency*: tasks started in a block must all finish before the block exits, like function calls nest. Consequences:
- A task group / cancel scope must be **exited by the same task that entered it**. I reproduced the error: enter `anyio.create_task_group()` inside one task and close it from another → `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in`.
- Several failures at once arrive as `ExceptionGroup` (or `BaseExceptionGroup`, if one is a `BaseException`), possibly nested. Catch them with **`except*`** (PEP 654), or unwrap by hand like `describe_error()` does (`while isinstance(e, BaseExceptionGroup): e = e.exceptions[0]`).

## 2. In this repo

- `graph.py`: `lookup` is `async def` and awaits `lookup_fn(topic)`; `understand`/`answer` use `await llm.ainvoke(...)`; `clarify`/`check`/`handoff` stay plain `def`. `chat()` is `async def`, started by `asyncio.run(chat(args))`.
- **Design forced by the same-task rule.** LangGraph runs every node in its **own task**. If the lookup node restarted the server, the new connection would be entered in a node task and exited later by the chat task → the error above. So the node only sets `faq.broken = True`; the chat loop (the task that opened the connection) calls `await faq.ensure_connected()` before the next turn.
- **A server that can't start** raised `ExceptionGroup('unhandled errors in a TaskGroup', [ExceptionGroup(..., [MCPError(-32000, 'Connection closed')])])` during `Client.__aenter__` (0.04 to 0.18 s). `describe_error()` unwraps it to the one real error.
- **`input()` is called blocking, on purpose:** between turns nothing else needs to run. `asyncio.to_thread(input)` was rejected: on Ctrl-C, `asyncio.run` waits at shutdown for the default executor thread, which stays blocked reading stdin, so the program hangs.
- **Ctrl-C under asyncio** (Python 3.14 `asyncio/runners.py`, `Runner._on_sigint`): `asyncio.run` replaces Python's SIGINT handler. First Ctrl-C: the handler only **cancels the main task** and returns. Second Ctrl-C: raises `KeyboardInterrupt`. If the main task ends cancelled, `run()` raises `KeyboardInterrupt` itself. Problem: a blocking `input()` was interrupted by the signal, the handler returned normally, and Python retries the interrupted system call (PEP 475), so `input()` kept waiting until Enter. First version printed a `CancelledError` then `KeyboardInterrupt` traceback.
- **Fix:** `read_line()` sets `signal.default_int_handler` with `signal.signal` only while waiting at `input()`, then restores asyncio's handler. `main()` catches `KeyboardInterrupt` from `asyncio.run` and prints `(stopped)`. Measured: Ctrl-C at the prompt exits 0 silently; Ctrl-C during a turn prints `(stopped)`, exit 0, and no server process is left (the `async with FaqClient` exit stopped it).
- **Sync nodes in an async graph:** LangGraph wraps a sync function with `run_in_executor` (`langgraph/_internal/_runnable.py`), so it runs in a thread pool and doesn't block the loop.

## 3. How the pieces fit

```
asyncio.run ──> event loop ──> chat() task (owns FaqClient, opens/closes the MCP connection)
                    │              └─ graph.astream ──> one task per node (lookup awaits MCP; sync nodes -> thread pool)
                    └─ MCP SDK: anyio task group reading/writing the server's pipes
```

## 4. Related tools

- **Threads** (`threading`, `concurrent.futures`): fine for a few blocking calls (the Azure Speech SDK uses callbacks on its own threads); no `await` needed, but shared state needs care.
- **Trio:** the library that invented structured concurrency; anyio speaks both. We use plain asyncio.
- **`multiprocessing`:** for CPU-bound work, which async doesn't help.
- **`nest_asyncio` / Jupyter:** notebooks already run a loop, so `asyncio.run` fails there; use top-level `await`.

## 5. Hands-on exercises

Save each in a scratch folder and run with `.venv/bin/python file.py`.
1. **Sequential vs concurrent.** Coroutine `job(name, s)` that prints, `await asyncio.sleep(s)`, prints. In `main`: `await job("a",1); await job("b",1)` then `await asyncio.gather(job("a",1), job("b",1))`. Check (measured): `sequential 2.0 s`, then `gather 1.0 s` with "a start, b start" before any "done".
2. **Calling doesn't run.** `c = job("c",0); print(type(c))`. Check: `<class 'coroutine'>`, nothing printed by `job`.
3. **Blocking freezes the loop.** A `ticker()` task printing every 0.5 s; in `main`, `await asyncio.sleep(1.2)` then `time.sleep(2)`. Check (measured): ticks 0, 1, 2, a 2 s pause, then `woke` and the rest. Replace with `await asyncio.sleep(2)` and the ticks continue.
4. **Timeout.** `async with asyncio.timeout(1): await asyncio.sleep(10)` inside `try/except TimeoutError`. Check: prints after 1 s.
5. **`except*`.** `raise ExceptionGroup("g", [ValueError("a"), ExceptionGroup("inner", [KeyError("k")])])` with `except* ValueError` and `except* KeyError`. Check (measured): each handler runs once; the KeyError arrives still wrapped in its `inner` group.
6. **Ctrl-C mechanics.** `main()` calls `loop.call_later(0.3, os.kill, os.getpid(), signal.SIGINT)` then `await asyncio.sleep(5)` inside `try/except asyncio.CancelledError: print(...); raise`. Check (measured): prints the CancelledError line, and `asyncio.run` raises `KeyboardInterrupt`.
7. **Same-task rule.** Create `anyio.create_task_group()` via `stack.enter_async_context` inside `asyncio.create_task(...)`, then `await stack.aclose()` from `main`. Check: `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in`.
8. **In the repo.** `.venv/bin/python faq_client.py ბარათი` prints "connect ~3 s, call a few ms". Read the `connect`/`call` split: waiting is nearly all startup.

## 6. Self-check: can you answer these without looking?

1. What does `f()` return when `f` is `async def`, and what happens if you never await it?
2. Why did `gather` take 1 s for two 1 s sleeps, and why would `time.sleep` not?
3. Why can't the lookup node restart the MCP server?
4. After the first Ctrl-C, why did a blocking `input()` keep waiting under `asyncio.run`?
5. Why is `CancelledError` not caught by `except Exception`, and what should you do after catching it?
6. What is an `ExceptionGroup` and how do you handle a nested one?

<details><summary>Answers</summary>

1. A coroutine object; the body never runs, and Python warns "never awaited". 2. Both sleeps wait on the loop at the same time; `time.sleep` blocks the one thread so the loop can't switch. 3. LangGraph runs each node in its own task; anyio requires the task that entered the connection (the chat task) to exit it. The node sets `broken`; the chat loop reconnects. 4. asyncio's handler only cancelled the main task and returned; the interrupted read was retried (PEP 475), so `input()` stayed blocked. 5. It derives from `BaseException` so cleanup/cancel logic isn't swallowed by accident; clean up and re-raise. 6. One exception that wraps several (from concurrent tasks); use `except*` per type, or loop through `.exceptions` to the first real error.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | exercises 1-8 with explanations | 45 min |
| B. Another AI tutor | quizzing, extra examples | 30 min |
| C. Primary docs | exact semantics, cancellation | 2 h |
| D. Video | the event-loop mental model | 1-2 h |

**Start here:** D (Corey Schafer) then C (the conceptual HOWTO).

**A.** Paste in a main session: "Read learning/notes/2026-10-03-python-async-await.md. Walk me through exercises 1-7, one at a time, running each and explaining the output. Then show me in faq_client.py and graph.py where each concept (AsyncExitStack, asyncio.timeout, read_line, ensure_connected) appears."

**B.** NotebookLM (add the C links) or ChatGPT/Gemini. Prompt: "Using only https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html, https://docs.python.org/3/library/asyncio-task.html, https://docs.python.org/3/library/asyncio-runner.html and https://anyio.readthedocs.io/en/stable/tasks.html, explain coroutines vs tasks, the event loop, cancellation, and task groups with small examples. Then ask me 6 questions, one at a time, and correct me."

**C.** All opened 2026-10-03.
- Conceptual overview of asyncio (HOWTO): https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html (event loop, coroutines, tasks, `await`; part 2 is internals, optional)
- Coroutines and Tasks: https://docs.python.org/3/library/asyncio-task.html (`run`, `create_task`, `TaskGroup`, `timeout`, `to_thread`, cancellation)
- Runners (read "Handling Keyboard Interruption"): https://docs.python.org/3/library/asyncio-runner.html
- anyio, Tasks: https://anyio.readthedocs.io/en/stable/tasks.html (task groups, exception groups); Cancellation and timeouts: https://anyio.readthedocs.io/en/stable/cancellation.html (cancel scopes, LIFO exit, "Avoiding cancel scope stack corruption"). The docs I fetched don't state the same-task rule in so many words; I confirmed it by running exercise 7.
- PEP 492 (async/await): https://peps.python.org/pep-0492/ ; PEP 654 (`ExceptionGroup`, `except*`): https://peps.python.org/pep-0654/ ; PEP 475 (retry interrupted system calls): https://peps.python.org/pep-0475/
- Real Python, "Async IO in Python: A Complete Walkthrough" (Leodanis Pozo Ramos, ~39 min read): https://realpython.com/async-io-python/ . Title and author confirmed in a search result; the page returned 403 to my fetch, so I haven't read it.

**D.**
- "Python Tutorial: AsyncIO - Complete Guide to Asynchronous Programming with Animations", Corey Schafer: https://www.youtube.com/watch?v=oAkLSJNr5zY . Title, channel and link confirmed in a search result (video posted Sept 2025; I did not watch it). Covers coroutines, tasks, the event loop, and when to pick asyncio vs threads vs multiprocessing.
- "Python Concurrency From the Ground Up: LIVE!", David Beazley, PyCon US 2015: https://www.youtube.com/watch?v=MCs5OvhV9S4 (link from the pyvideo.org page, https://pyvideo.org/pycon-us-2015/python-concurrency-from-the-ground-up-live.html ). Live-codes an event loop from scratch; old (pre-`async def` style) but the best look at how a loop works. Advanced.
