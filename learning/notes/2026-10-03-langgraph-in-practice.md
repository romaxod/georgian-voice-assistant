# LangGraph in practice: StateGraph, reducers, checkpoints, streaming

Date: 2026-10-03. Checked against the LangGraph docs (Checkpointers, Streaming, Use the graph API, v1 migration, LangSmith tracing pages; all opened), the installed packages (langgraph 1.2.12, langgraph-checkpoint 4.2.0, Python 3.14), and by running throwaway graphs and `python graph.py --draw`. The line-by-line walk-through of the code is `docs/code/graph.py.md`. The concepts (state, reducers, cycles, interrupts, `Send`, workflows vs agents) are already in [agentic architectures](2026-10-02-agentic-architectures.md); memory and checkpointers in [system prompts and memory](2026-10-03-system-prompts-and-memory.md). This note is the API in use.

## 1. What you're learning, and why it matters

**Problem:** `chat.py` was one hand-written `while` loop where the model decided everything. For the next steps (clarify, hand off to a human, call MCP tools, enforce step limits) you need the flow to be *explicit*, inspectable and resumable. LangGraph is a runtime where you declare the flow as a graph and it runs, saves and traces it.

- **`StateGraph(State)`**: a builder. You add **nodes** (Python functions), connect them with **edges**, then `compile()` it into a runnable graph.
- **State** is a `TypedDict`. Each key is a **channel**. A node reads the whole state and returns a **partial update** (a dict with only the keys it changes). LangGraph merges it in.
- **Reducer**: a function `(old, new) -> merged` attached with `Annotated[type, reducer]`. No reducer: the new value overwrites. `operator.add` on a float sums (our `cost`). `add_messages` on a list appends new messages, **replaces** one with the same `id`, and **deletes** one when you send `RemoveMessage(id=...)`. Verified: appending a `HumanMessage` and an `AIMessage` gives ids to both, and `RemoveMessage` of the first leaves one message.
- **Edges**: `add_edge(a, b)` always goes a to b. `add_conditional_edges(a, fn)`: `fn(state)` returns the next node's name. The `Literal["lookup","answer"]` return annotation is how LangGraph learns the possible targets without a path map; the drawing needs it.
- **`START` / `END`**: special nodes for entry and exit.
- **Checkpointer** (`compile(checkpointer=InMemorySaver())`): saves the state after every **super-step** (one "tick" where all ready nodes run; our graph is sequential, so one node per tick). Calls with the same `thread_id` continue from the saved state. A **thread** = one conversation's checkpoint chain.
- **Closures**: our nodes are inner functions of `build_graph(llm=None, checkpointer=None)`, so they share `llm` without globals and tests can inject a fake.

## 2. In this repo

`graph.py`: `START -> understand -(faq)-> lookup -> answer -> END` and `understand -(other)-> answer`. Only `understand` and `answer` call a model.

**Tracing one request.** `graph.get_state_history(config)` after one question printed one checkpoint per super-step: step -1 `next=('__start__',)`, step 0 `next=('understand',)`, step 1 `next=('lookup',)`, step 2 `next=('answer',)`, step 3 `next=()`. `next` says what runs after that checkpoint; `()` means finished. On a toy graph I ran, step numbers **keep counting across turns of one thread** (second turn started at step 3), and the history lists newest first. Each entry is a `StateSnapshot` with `.values`, `.next`, `.metadata["step"]`.

**invoke vs stream.** `graph.invoke(input, config)` runs to the end and returns the final state. `graph.stream(input, config, stream_mode=...)` yields while it runs. Modes (Streaming docs): `values` (full state after each step), `updates` (`{node: what it returned}`; we use this for the trace lines and timings), `messages` (LLM tokens with metadata, for typing-effect output; useful for TTS in 2.5), `custom` (anything you emit with `get_stream_writer()`), plus `checkpoints`, `tasks`, `debug`. In `stream_mode="values"` the first item is the input merged into the state.

**State access.** `get_state(config).values` reads the saved state (we read the last message and `cost`). `update_state(config, {...})` writes a **new checkpoint** and runs the values through the reducers, which is why `{"messages": [RemoveMessage(id=...)]}` deletes. We use it to drop the question when the API failed mid-turn (tested: 1 message before, 0 after, error `OpenAIModelNotFoundError` HTTP 404). Because the checkpoint was already saved, without that cleanup the next turn would see an unanswered question.

**Why `understand` resets `facts` and `lookup_error`:** keys without reducers persist in the checkpoint between turns, so last turn's facts would leak into this one.

**Drawing.** `python graph.py --draw` prints Mermaid text (dotted `-.->` = conditional edges); paste it into mermaid.live. It needs `OPENAI_API_KEY` set to *something*, because `ChatOpenAI(...)` is created in `build_graph`; I tested with a dummy value.

**Break test:** patching `graph.lookup_faq` to raise `sqlite3.OperationalError` gave `lookup_error` in state, and `answer` told the customer honestly and offered an operator. Errors as data in state, as in the [1.4 function-calling note](2026-10-03-function-calling-responses-api.md).

**Recursion limit.** A graph with a cycle stops after N super-steps with `GraphRecursionError`; set per call with `config={"recursion_limit": N}`. The docs I opened cover it under "Create and control loops". The installed source says `DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))`, much higher than older tutorials (25), so set a low limit yourself. Our graph has had a cycle since step 2.2 (`lookup -> lookup`), so the limit is set to 10; see the next section.

### What step 2.2 added *(added 2026-10-03)*

Checked against the installed langgraph 1.2.12 (`types.py`, `pregel/main.py`), the "Use the graph API" docs page (opened), and scratch graphs.

- **A cycle with an attempt counter.** `route_after_lookup` can return `"lookup"`, so the node runs again. A cycle needs an exit, so the counter lives in state (`lookup_attempts`, reset by `understand` each turn); `MAX_LOOKUP_ATTEMPTS = 2` means one retry. On the last failure `lookup` sets `handoff_reason="tool_error"` and the router goes to `handoff`. Each retry is its own super-step, so it appears in the `stream` trace (`try 1 ... retry`, `try 2: 2 entries`).
- **Cycle vs `RetryPolicy`.** `builder.add_node("lookup", fn, retry_policy=RetryPolicy(...))` (`from langgraph.types import RetryPolicy`) retries a node that *raises*. Fields in the installed source: `initial_interval=0.5` s, `backoff_factor=2.0`, `max_interval=128.0`, `max_attempts=3` (includes the first try), `jitter=True`, `retry_on` (exception class(es) or a function; the default retries connection errors, HTTP 5xx and many built-in errors such as `ValueError`, `OSError`). Its advantages are backoff and jitter without extra nodes. We used a cycle because the retries show in the trace and, more importantly, after the last attempt `RetryPolicy` re-raises, while our version turns the failure into state (`handoff_reason`) that the graph can route to a friendly reply. (I did not test `RetryPolicy` in this repo; that comparison is from the source and docs.)
- **One shared problem flag.** Any node that finds a problem writes `handoff_reason` (and `handoff_note`); routers only check `state.get("handoff_reason")`. New failure mode: one reason string, one template, no router rewrite.
- **A router can end the graph.** `route_after_check` is annotated `-> Literal["handoff", "__end__"]` and returns `"__end__"`, the string value of `END`, so no extra node is needed.
- **`recursion_limit` is N+1.** Scratch test: a 3-node chain `a -> b -> c` raised `GraphRecursionError` at `recursion_limit=3` and passed at 4 (the limit also counts one step after the last node). The longest normal path here is 6 nodes, so `MAX_STEPS = 10`. `python graph.py --max-steps 3` makes it trigger.
- **The double-reply bug.** With `--max-steps 3`, "გამარჯობა" ran `understand`, `answer`, `check` (the reply was already saved), and then raised. The first handler appended a step-limit apology too, leaving 5 messages instead of 4. Fix: catch `GraphRecursionError` and add `STEP_LIMIT_REPLY` only if `graph.get_state(config).values["messages"][-1].id` is still the user's message id. That is why the user message gets our own `uuid` id.
- **`update_state(config, values, as_node="handoff")`.** `update_state` writes a new checkpoint "as if" the values came from node `as_node`. LangGraph then treats that node as having just run and computes what comes next from it; `handoff` has an edge to END, so the unfinished steps are dropped and the next turn starts clean. Without `as_node` it picks the last node that updated the state if that isn't ambiguous (docstring in `pregel/main.py`), which here would be wrong.
- **`lookup_fn` dependency injection.** `build_graph(lookup_fn=lookup_faq)` takes the search function as a parameter. `failing_lookup("once"|"always")` returns a stand-in that raises `sqlite3.OperationalError`, so the error paths can be tested without breaking a real database. Compare the monkeypatching in the [Python CLI note](2026-10-03-python-cli-basics.md): injection needs no patching and the dependency is visible in the signature.
- **Exercise:** `python graph.py --max-steps 3`, send "გამარჯობა". Check: `[step limit]` line and exactly one reply. Then `--max-steps 4` and check it passes.

Failure-handling design (why each route exists) is in [failure handling and guardrails](2026-10-03-failure-handling-and-guardrails.md).

## 3. How the pieces fit together

```
input -> [reducers merge it into State] -> node runs -> returns partial update -> reducers merge
      -> checkpointer saves (per thread_id) -> conditional edge reads State, names next node -> ... -> END
          ^ stream() lets you watch each step; get_state / update_state read and edit the saved copy
```

Sets up **2.2**: a `clarify` node and a `handoff` node are just new nodes and new targets in `route_after_understand`; a loop plus `recursion_limit` gives the step limit; `interrupt()` pauses for a human. **2.4**: MCP tools replace the body of `lookup`; the graph around it stays.

## 4. Related tools

- **Router workflow (ours) vs ReAct agent.** An agent is a model-driven loop: the model picks tools until it answers. LangGraph's prebuilt version was `create_react_agent` in `langgraph.prebuilt` with a `ToolNode`; per the v1 migration page it is **deprecated** in favor of `from langchain.agents import create_agent` (which runs on LangGraph). `langchain` itself isn't installed here. We chose the router because every ჯიხვი question needs the FAQ, so letting the model decide is a chance to skip it (the TV-packages miss in 1.4). The cost is one more LLM call (turns took 1.4-3.2 s). Conditions that would flip it: many tools, open-ended tasks. See [agentic architectures](2026-10-02-agentic-architectures.md).
- **Honest weakness of the router:** with `lookup` always running, "გაქვთ სატელევიზიო პაკეტები?" returned unrelated entries (matched "პაკეტ"), and the answer said it had no info but did not offer an operator. That is a retrieval-precision problem, a Phase 3 eval case.
- **LangSmith** (installed as a dependency): a hosted tracing UI. Enable with env vars `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY=...` (docs page above). It sends prompts and data to a third party, so not for real customer data; we defer it to Phase 3 (evals).
- **Other:** plain Python (what `chat.py` was), OpenAI Agents SDK, CrewAI. LangGraph is what this project set out to learn.

## 5. Hands-on exercises

1. `OPENAI_API_KEY=dummy .venv/bin/python graph.py --draw`. Paste the output into mermaid.live. Check: three nodes, two dotted edges from `understand`.
2. Run `.venv/bin/python graph.py`, ask "რა ღირს როუმინგი ევროპაში?" then "და რამდენ ხანს მოქმედებს?". Check: the second `topic` mentions roaming and Europe (rewritten from history).
3. In a scratch script copy the toy graph idea: two nodes, `log: Annotated[list[str], operator.add]`, `InMemorySaver`, two `invoke` calls with the same `thread_id`. Check: `log` accumulates across calls; with a new `thread_id` it starts empty.
4. Print `get_state_history(config)` as `(s.metadata["step"], s.next)`. Check: newest first; `next=()` at the top.
5. Remove the `Annotated` from `cost` in a copy of `State`. Check: `cost` now holds only the last node's value, not the sum.
6. Make `route_after_understand` return `"nowhere"`. Check: an error naming the unknown node (read the traceback bottom-up).

## 6. Self-check

1. What does a node return, and who merges it? 2. Difference between a key with and without a reducer? 3. What is a super-step and how many checkpoints did one turn create? 4. Why does `update_state` with `RemoveMessage` delete a message? 5. Router workflow vs ReAct agent: which decides whether to call the tool here, and what did we trade? 6. Why does `understand` reset `facts`?

<details><summary>Answers</summary>

1. A partial dict of changed keys; the reducers (or overwrite) of each channel. 2. With: old and new are combined by the function (add, append, replace by id); without: overwritten. 3. One tick where ready nodes run; a checkpoint after the input and after each node (steps -1 to 3 for one turn, 5 checkpoints). 4. `update_state` passes values through reducers; `add_messages` treats `RemoveMessage` as a delete by id. 5. The graph's edge decides (router); we gained a guaranteed lookup and a drawable flow, lost one LLM call of latency and the model's flexibility. 6. The checkpoint keeps non-reducer keys, so old facts would be shown for a new question.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-6 on this repo | 45 min |
| B. Another AI tutor | Quiz, extra toy graphs | 45 min |
| C. Primary docs | Exact API behavior | 2 h |
| D. Video/course | Seeing graphs built live | 3-6 h |

**A.** Paste: "Read learning/notes/2026-10-03-langgraph-in-practice.md and graph.py. Walk me through exercises 1-6, running each command, and explain each result in terms of super-steps and reducers."

**B.** NotebookLM with the C links. Prompt: "Using only these sources (https://docs.langchain.com/oss/python/langgraph/use-graph-api, https://docs.langchain.com/oss/python/langgraph/checkpointers, https://docs.langchain.com/oss/python/langgraph/streaming), explain state, reducers, super-steps, checkpoints and stream modes with a 3-node example, then quiz me with 6 questions."

**C.**
- Use the graph API: <https://docs.langchain.com/oss/python/langgraph/use-graph-api>. Sections "Process state updates with reducers", "MessagesState", "Conditional branching", "Create and control loops", "Visualize your graph". *(opened)*
- Checkpointers: <https://docs.langchain.com/oss/python/langgraph/checkpointers>. Threads, super-steps, `get_state`, `get_state_history`, `update_state`. *(opened)*
- Streaming: <https://docs.langchain.com/oss/python/langgraph/streaming>. The stream modes table. *(opened)*
- Thinking in LangGraph: <https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph>. Designing the nodes for a process; closest to 2.1. *(opened earlier, see agentic note)*
- LangGraph v1 migration: <https://docs.langchain.com/oss/python/migrate/langgraph-v1>. The `create_react_agent` deprecation. *(opened)*
- LangSmith tracing with LangGraph: <https://docs.langchain.com/langsmith/trace-with-langgraph>. The env vars. *(opened)*

**D.**
- LangChain Academy, "Introduction to LangGraph - Python" (free, 55 lessons, about 6 h): <https://academy.langchain.com/courses/intro-to-langgraph>. Take Module 1 (simple graphs, chains, routers, agents) and Module 2 (state schema, reducers, message management); Module 3 covers streaming and state editing. *(opened)*
- "Learn LangGraph and Build Conversational AI with Python", Vaibhav Mehra, freeCodeCamp (about 3 h): <https://youtu.be/jGg_1h0qzaM>. Title, instructor, link and length confirmed on the freeCodeCamp article page; I did not watch it. It starts with type annotations, which helps with the typing section of [Python CLI basics](2026-10-03-python-cli-basics.md).
- DeepLearning.AI, "AI Agents in LangGraph" (about 1.5 h): <https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/> (opened earlier; see the agentic note). Persistence and streaming lesson.
