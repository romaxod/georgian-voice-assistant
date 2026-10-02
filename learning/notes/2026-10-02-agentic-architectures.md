# Agentic architectures: patterns beyond the single loop

Why it matters: "agentic architectures", LangGraph and MCP are what this project is built to learn, and knowing the architecture of agentic systems is the point. This note is the map; the single loop is in [agent loops](2026-10-02-agent-loops.md). Checked against Anthropic, OpenAI and LangGraph docs on 2026-10-02.

## 1. What you're learning, and why it matters

**Problem:** "use an LLM" has many shapes, from one prompt to a team of autonomous agents. More autonomy means more flexibility, but also more cost, latency, and ways to fail. You need names for the shapes so you can pick the smallest one that works.

**Workflows vs. agents** (Anthropic's split, repeated in the LangGraph docs):

- **Workflow:** the *code* decides the path. LLM calls are steps in a fixed structure. Predictable, testable.
- **Agent:** the *model* decides the next step and which tools to use, in a loop, until it's done. Flexible, harder to bound.
- "Agentic system" covers both. Most useful products are mostly workflow with a little agent in it.

**The patterns** (names from Anthropic's "Building effective agents"; LangGraph's docs use the same five):

| Pattern | One line | Use when |
|---|---|---|
| **Prompt chaining** | step 1's output feeds step 2, with optional code checks between | a task splits cleanly into fixed steps (draft, then translate) |
| **Routing** | classify the input, send it down a specialised path | different request types need different handling (FAQ, complaint, hand-off) |
| **Parallelization** | run independent calls at once (split the task, or vote on one task) | speed, or several independent checks |
| **Orchestrator-workers** | a model splits the task at run time and delegates to workers | you can't know the subtasks in advance (editing many files) |
| **Evaluator-optimizer** | one call generates, another critiques, repeat until good | clear quality criteria and revision helps |
| **Autonomous agent loop** | model + tools in a loop with stop conditions | open-ended problems with unpredictable steps |

```
chain:       in -> [LLM] -> check -> [LLM] -> out
routing:     in -> [classify] -+-> [FAQ path] ----+
                               +-> [clarify path] +-> out
                               +-> [human] -------+
eval-opt:    in -> [generate] -> [evaluate] --good--> out
                      ^------feedback--+--bad
agent loop:  in -> [model] <-> [tools]  ... -> out
```

**Also worth knowing:**

- **Plan-and-execute:** a model writes a multi-step plan, then steps run (by a cheaper model or code), re-planning if a step fails. Good for long tasks; overkill for one FAQ lookup.
- **Reflection:** generate, critique, revise (the evaluator-optimizer shape with one model); strongest with an external check such as a test.
- **Multi-agent:** several model-driven roles. Two shapes in OpenAI's guide: a **manager** that calls specialist agents as tools, and **decentralized** peers that hand off to each other. Costs more and is harder to debug; OpenAI's guide advises maximising a single agent first.
- **Human-in-the-loop / hand-off:** the system pauses for approval, or passes the conversation to a person. For a real customer service, a *feature*, not a failure.
- **RAG / tool-augmented assistant:** the model answers from retrieved or tool-fetched facts. Our `lookup_faq` is a tiny version. "Agentic RAG" (LangGraph tutorial) lets the model decide whether to retrieve, grades results, and rewrites the query.

**How LangGraph expresses these** (concept names checked in the current docs):

- **State:** the shared data (messages, retrieved facts); typically a `TypedDict` or Pydantic model. **Reducers** say how updates merge (e.g. append to the message list).
- **Nodes:** functions that take state and return updates; an LLM call or plain code.
- **Edges:** which node runs next; fixed, or **conditional** (`add_conditional_edges`, a routing function returns the next node). `START` and `END` are the entry and exit. A node can also return a `Command` (state update plus `goto`).
- **Cycles:** an edge back to an earlier node makes the loop; `recursion_limit` stops runaway cycles (`GraphRecursionError`).
- **Checkpoints and threads:** a checkpointer saves state after each step, per `thread_id`. This gives conversation memory and resumability.
- **Interrupts:** `interrupt()` pauses a node and waits for outside input (a human); `Command(resume=...)` continues. It requires a checkpointer.
- `Send` fans work out to parallel nodes (the orchestrator-worker shape).

**Where MCP fits:** MCP is "a standardized way to connect AI applications to external systems" (its docs compare it to USB-C). It standardises the **tools layer** (how tools are described, listed and called), not the architecture. Any pattern above can get its tools through MCP. It is orthogonal to the choice of graph shape.

## 2. In this repo

BUILD_PLAN says which pattern we're building:

- **2.1:** nodes understand -> look up -> answer, with edges: a **routing + RAG-style** workflow.
- **2.2:** adds routes (clarify, hand off to a human, tool error) and a step limit: **routing** plus a bounded **tool loop** plus a **hand-off node**. That is mostly a workflow with a small agent loop inside, not a free-roaming agent.
- **2.3-2.4:** the lookup node calls the tool via MCP; the shape stays the same.
- **3.1-3.2:** the eval cases test each route (ordinary, ambiguous, tool failure, false-action claim).

Planned graph, to compare with your sketch (exercise 2):

```
START -> [understand/route] --ambiguous--> [clarify] --------------> END
                |--unsure/unsafe-------> [handoff to human] -------> END
                |--FAQ question--> [model] <--> [lookup_faq tool]   (step limit)
                                      |--tool error--> [honest error reply] --> END
                                      +--answer--> [validate reply] --> END
```

**Production reality.** A real customer assistant needs systematic evaluation and a clear answer to how the quality, correctness and safety of its answers are checked. A production assistant would add: a **guardrail/validator** node on inputs and outputs (no unsupported claims, no data leaks), **human hand-off** with context passed along, **audit logs** of every tool call, permissions on tools (read-only first), and approval gates (interrupt) before any money-moving action. Keep **autonomy low**: the cost of a wrong action is high, regulators want traceability, and a fixed path is easier to test than a free agent. This matches OWASP's "excessive agency" (functionality, permissions, autonomy) and why BUILD_PLAN 2.2 includes "block my card isn't falsely confirmed". This project stays fictional and read-only.

**How to choose:** start with the simplest thing that works (one prompt with retrieval). Add a pattern only when you can name the failure it fixes, with an eval case that shows it. Order of escalation: single call -> chain/route -> tool loop -> evaluator-optimizer -> orchestrator -> multi-agent. Anthropic and OpenAI both say this.

## 3. How the pieces fit together

Architecture (workflow/agent shape) decides *who chooses the next step*; the loop and its guards ([agent loops](2026-10-02-agent-loops.md)) decide *how one step cycle runs safely*; LangGraph is the runtime that draws it; MCP is where the tools come from; evals ([BUILD_PLAN](../../BUILD_PLAN.md) phase 3) tell you whether it works. Claude Code's own subagents are the same ideas applied to coding: see [subagents](2026-10-01-claude-code-subagents.md) and [hooks](2026-10-02-hooks-and-headless-claude.md).

## 4. Related tools

- Other frameworks (OpenAI Agents SDK, CrewAI, AutoGen, plain Python): this project is about learning LangGraph, so we use it. Anthropic advises starting with direct API calls, since frameworks add layers that hide prompts and responses.
- LangChain "Deep Agents" and prebuilt agents (mentioned on the LangGraph overview page): higher-level; skip until you can draw the graph yourself.

## 5. Hands-on exercises

1. **Classify** each system by pattern: (a) a bot that translates an email, then proofreads it; (b) a bot that labels a message "billing / tech / other" and sends it to a different prompt; (c) a coding assistant that edits an unknown set of files; (d) a writer model plus a critic model that loops until the critic approves; (e) a support bot with a search tool that decides when to search and when to answer. Check: chain, routing, orchestrator-workers, evaluator-optimizer, autonomous loop.
2. **Sketch this project's graph** as boxes and arrows from BUILD_PLAN 2.1-2.2 on paper, then compare with section 2. Mark which nodes are code and which call the model.
3. **Add three nodes** a production assistant would need (guardrail, human approval, audit log) to your sketch. Say what each checks and which BUILD_PLAN eval case would test it.
4. **Argue** whether a multi-agent design (supervisor plus FAQ agent, handoff agent, safety agent) would help this project. Give one reason for and two against. Check: against, since one tool, one data source, small scope, and every agent adds cost, latency and failure modes.
5. *(Needs network; optional)* Open the LangGraph "Workflows and agents" page and find where each of the five workflow patterns appears as code. Which uses `Send`?

## 6. Self-check: can you answer these without looking?

1. Workflow vs. agent: who decides the next step in each?
2. Name the five workflow patterns and one use for each.
3. What do state, nodes, conditional edges and a checkpointer each do in LangGraph?
4. What does MCP standardise, and what doesn't it decide?
5. Which pattern is our graph and why isn't it a fully autonomous agent?
6. Why keep autonomy low in a customer-facing assistant that handles accounts?

<details><summary>Answers</summary>

1. Workflow: your code. Agent: the model.
2. Chaining (fixed steps), routing (classify and branch), parallelization (speed or voting), orchestrator-workers (dynamic subtasks), evaluator-optimizer (generate and critique).
3. State: shared data. Nodes: steps. Conditional edges: choose the next node from state. Checkpointer: saves state per thread for memory, resume and interrupts.
4. The tools interface (discovery, schemas, calls). Not the control flow or the architecture.
5. Routing plus a bounded tool loop plus hand-off. Paths and limits are set by code; the model only chooses within them (answer, call the one tool).
6. Wrong actions are costly and must be auditable; fixed paths are testable; prompt injection and hallucinated actions become dangerous with broad tools.
</details>

## 7. Ways to learn it (choose later)

**Start here:** Anthropic, "Building effective agents". It names every workflow pattern in this note, says when *not* to use agents, and is the source the LangGraph docs follow; the others are narrower, longer or vendor-specific.

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Exercises 1-4 with critique of your sketch | About 45 min |
| B. Another AI tutor | A different explanation and a quiz | About 45 min |
| C. Primary docs | The accurate vocabulary | 1.5 hr |
| D. Video or course | Seeing graphs built in code | 1.5 to 6 hr |

**A. Prompt for a main session in this repo:**
> Walk me through learning/notes/2026-10-02-agentic-architectures.md. Give me exercise 1 first and wait for my answers, then have me sketch the project graph (exercise 2) before showing yours, then argue the multi-agent question with me. Quiz me on section 6.

**B. Tool:** NotebookLM with the C links. Prompt:
> Using only these sources, explain the difference between workflows and agents, the five workflow patterns, and how LangGraph expresses them (state, nodes, edges, checkpoints, interrupts). Then quiz me with 6 questions and answers. Sources: https://www.anthropic.com/engineering/building-effective-agents, https://docs.langchain.com/oss/python/langgraph/workflows-agents, https://docs.langchain.com/oss/python/langgraph/graph-api, https://docs.langchain.com/oss/python/langgraph/interrupts, https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph, https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf

**C. Reading list** (opened 2026-10-02 unless noted):
- Anthropic, "Building Effective AI Agents" (Erik S. and Barry Zhang, 2024-12-19): <https://www.anthropic.com/engineering/building-effective-agents>. Read "Building blocks, workflows, and agents" for the five patterns. *(opened)*
- LangGraph docs, "Workflows and agents": <https://docs.langchain.com/oss/python/langgraph/workflows-agents>. The same patterns in code. *(opened)*
- LangGraph docs, "Thinking in LangGraph": <https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph>. A five-step method for turning a process (a support-email agent) into a graph, with error handling by type. Best match for BUILD_PLAN 2.1. *(opened)*
- LangGraph docs, "Graph API overview": <https://docs.langchain.com/oss/python/langgraph/graph-api>. State, nodes, edges, reducers, `Command`, `Send`, recursion limit. *(opened)*
- LangGraph docs, "Interrupts": <https://docs.langchain.com/oss/python/langgraph/interrupts>. `interrupt()` and `Command(resume=...)`, for the human hand-off. *(opened)*
- LangGraph docs, "Persistence": <https://docs.langchain.com/oss/python/langgraph/persistence>. Threads, checkpoints, checkpointers. *(opened)*
- LangGraph docs, "Custom RAG agent" (agentic RAG): <https://docs.langchain.com/oss/python/langgraph/agentic-rag>. Conditional edges and a retrieval loop. *(opened)*
- LangGraph docs, "Overview": <https://docs.langchain.com/oss/python/langgraph/overview>. Mixing deterministic and agentic steps. *(opened)*
- OpenAI, "A practical guide to building agents" (PDF, 34 pages): <https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf>. Orchestration (manager vs. decentralized), guardrails, "Plan for human intervention". *(opened and text-extracted)*
- MCP, "What is the Model Context Protocol?": <https://modelcontextprotocol.io/docs/getting-started/intro>. *(opened)*
- OWASP, "LLM06:2025 Excessive Agency": <https://genai.owasp.org/llmrisk/llm062025-excessive-agency/>. The case for low autonomy. *(confirmed in search results; not opened)*
- Andrew Ng's The Batch letters, "Agentic Design Patterns" series, March 2024: Part 1 <https://www.deeplearning.ai/the-batch/how-agents-can-improve-llm-performance/> (opened), Part 2 Reflection <https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-2-reflection> (opened), Part 3 Tool Use <https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-3-tool-use/>, Part 4 Planning <https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-4-planning/>, Part 5 Multi-Agent Collaboration <https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-5-multi-agent-collaboration/> (Parts 3-5 as listed on the Part 2 page; not opened). His four patterns (reflection, tool use, planning, multi-agent) are a different cut from Anthropic's.
- Yao et al., "ReAct" <https://arxiv.org/abs/2210.03629> and Shinn et al., "Reflexion" <https://arxiv.org/abs/2303.11366>: the papers behind the reasoning-plus-acting and reflection patterns. *(both opened)*

**D. Video and courses**
- DeepLearning.AI, "AI Agents in LangGraph" (Harrison Chase, Rotem Weiss; free in the platform beta; about 1.5 h): <https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/>. Lessons "LangGraph Components", "Persistence and Streaming", "Human in the Loop". Best fit for 2.1-2.2. *(opened)*
- LangChain Academy, "Foundation: Introduction to LangGraph - Python" (free; 55 lessons, about 6 h of video): <https://academy.langchain.com/courses/intro-to-langgraph>. Modules on state, routers, agents, human-in-the-loop, parallelization, sub-graphs. Use as a reference, not in full. *(opened)*
- "What's next for AI agentic workflows ft. Andrew Ng of AI Fund" (Sequoia Capital, 2024, about 13 min): <https://www.youtube.com/watch?v=sal78ACtGTc>. Four patterns in one talk. *(title and ID confirmed via search results and a fetch)*

Whatever you choose, finish with exercises 1-2 and the self-check.
