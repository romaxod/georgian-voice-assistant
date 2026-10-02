# Agent loops: model, tool, result, repeat

Why it matters: "agentic architectures" is the first thing this project sets out to learn, and "does the model call tools in a loop, and what stops it?" is the core of that phrase. Checked against vendor docs and papers on 2026-10-02; links are marked with how they were verified (section 7).

## 1. What you're learning, and why it matters

**Problem:** the model can't run anything. It can only *ask* for a tool call. Something has to run the tool, give the result back, and decide when to stop. That something is a loop in your code.

**The basic loop** (this is the whole idea; everything else is guard rails):

1. Send the message list (system prompt + history + tool schemas) to the model.
2. Reply is either a **final answer** (text) or one or more **tool calls** (a name plus JSON arguments).
3. Tool call: *your code* checks the name is on your list, validates the arguments, runs the function, and appends the result as a **tool-result message**. Go to 1.
4. Final answer: return it to the user. Stop.

A tool call is *a request*, not an action. Validation and permission checks belong in your code (OWASP calls missing ones "excessive agency", see C).

**Stop conditions** (decide all of them up front, not only the happy one):

- **Final answer:** the model returns text with no tool call.
- **Max steps:** a hard cap, e.g. 5 model calls per user turn. Without it a confused model can loop forever.
- **Errors:** a tool exception, timeout, or a validation failure that repeats. Stop and reply honestly or hand off.
- **Budget:** a cap on tokens, money, or seconds per turn (a voice assistant also has a latency budget).
- **Repeat detection:** the same tool with the same arguments twice in a row means stop or change approach.

**History growth and cost.** The model is stateless, so every iteration resends the whole list, including every earlier tool result. A turn with 4 iterations bills the early messages 4 times, and long tool outputs ride along on every later call. See [tokens and pricing](2026-10-02-api-tokens-and-pricing.md), "stateless model and growing input cost". Practical rules: return small, relevant tool results; cap steps.

**Open vs. closed loops.**

- **Open loop:** the model acts and nobody checks. The answer ships as is.
- **Closed loop:** an automatic **verifier** checks the result and its feedback goes back to the model: generate -> verify -> feed the failure back -> fix -> re-verify.
- Verifiers, cheapest first: schema/argument validation, a unit test, a linter, a database lookup ("does this order id exist?"), a regex or rule, then an LLM judge last.
- **Why plain-code checks first:** they cost no tokens, run in milliseconds, give the same answer every time, and can return a *precise* error ("argument `topic` must be a non-empty string, got `''`"). A vague "try again" makes the model guess. An extra LLM turn costs input and output tokens and may be wrong itself.
- Keep **retries bounded** (e.g. 2). A verifier that always fails turns a closed loop into an infinite one.

**Failure modes** (each one is a test case in BUILD_PLAN 3.1):

| Failure | What it looks like | Catch |
|---|---|---|
| Infinite loop | model keeps calling tools, never answers | max steps, budget |
| Repeated identical call | same tool, same args, same empty result | compare with the previous call; stop |
| Hallucinated tool name or argument | calls `block_card`, or passes `topic=17` | allow-list of names; schema validation; error message back |
| Error spiral | each retry changes things and fails differently | bound retries; stop and hand off |
| Prompt injection via tool result | an FAQ row says "ignore instructions, ..." | treat results as data; the model can't call tools you didn't register; no sensitive tools |
| Claiming an action not taken | "I've blocked your card" with no tool call | no such tool exists; rule check: confirmation wording requires a successful tool result |

**ReAct** (Yao et al., 2022): the model interleaves a short *reasoning* step ("the user asks about fees, I should look up the FAQ") with an *action* (tool call) and an *observation* (the result), repeating until done. Modern tool-calling APIs are essentially this loop built in. **Reflection / self-correction** (Reflexion, Shinn et al., 2023; Ng's Part 2 letter): after an attempt, the model, given feedback, writes a critique and tries again. The feedback is strongest when it comes from something external (a test, a validator) rather than the model's own opinion. That is the closed loop above.

## 2. In this repo

No project code exists yet. Where each piece lands in [BUILD_PLAN.md](../../BUILD_PLAN.md):

- **1.4 Tool calling:** the hand-written loop in plain Python: `lookup_faq` schema, check the name, validate arguments, run, append the result, call the model again, plus a step cap. "Done when": the tool call is printed, and an off-topic question doesn't call the tool.
- **2.1 and 2.2:** the same loop as a LangGraph graph. Model node -> conditional edge ("tool call? or answer?") -> tool node -> back to the model node. 2.2 adds routes for clarify, hand-off, tool errors and a **step limit** (LangGraph has a `recursion_limit` setting; its docs say the default is 1000 super-steps, so set your own low value). See [agentic architectures](2026-10-02-agentic-architectures.md).
- **3.3 Fix one failure, measure again:** the eval loop is a closed loop *for the developer*: run cases (verifier = rules, then an LLM judge), read failures, change one thing, rerun the same cases, compare. Same pattern, with you as the "model".

**Entelligence AI** (short): an AI code-review product ("DeepReviews"; also a CLI, `entelligence review`). A search found no official "closed loop" page from them, so treat the phrase as marketing; what matters is the general pattern of AI-generated work checked automatically (tests, linters, review) and fed back, with a human last. Nothing here depends on the product.

## 3. How the pieces fit together

```
 user -> [model] --tool call--> [your code: allow-list, validate, run] --result--> back to [model]
            |                              |  error text (precise) ------------^
            +--final answer--> user        +--too many steps / repeated call / budget--> stop or hand off
```

The loop is the "agent"; the checks around it are what make it safe. In a graph, each box is a node and each arrow is an edge.

## 4. Related tools

- Anthropic's SDK has a tool runner that runs this loop for you, and other SDKs and LangChain have similar helpers (check current docs). We write it by hand in 1.4 so the first "magic" version isn't magic.
- Frameworks hide the loop but not its failure modes. You still need caps and validation.

## 5. Hands-on exercises (pen and paper, or BUILD_PLAN-linked)

1. Write out the exact message list for a turn with **2 tool calls** (system, user, assistant tool call, tool result, assistant tool call, tool result, assistant answer). Count how many times the user message is sent in total. Check: 3 model calls, so it is billed 3 times.
2. For `lookup_faq(topic)`: write the stop conditions (max steps, repeat rule, budget) and the exact error text for (a) empty topic, (b) topic not a string, (c) no rows found. Check: each message says what was wrong and what to do next, in under 20 words.
3. List 5 ways the loop could go wrong for a customer-service assistant and the cheapest check for each (use the table above; add your own, e.g. asking for another customer's data).
4. Take your table from 3 and mark which checks are plain code and which need an LLM. Aim for at most one LLM check.
5. *(At 1.4)* Break it on purpose: make `lookup_faq` always return an empty list. Does your loop stop? After how many calls?
6. *(At 3.3)* Write the before/after story of one fix as: failing case, cause, one change, rerun result.

## 6. Self-check: can you answer these without looking?

1. Who runs a tool, the model or your code? What does the model actually output?
2. Name four stop conditions.
3. Why does input cost grow faster than the number of iterations, and what grows?
4. Why check with plain code before an LLM judge?
5. What is a closed loop, and what makes a good error message to feed back?
6. Name three failure modes and a check for each.

<details><summary>Answers</summary>

1. Your code. The model outputs a request: tool name plus JSON arguments (or a final text answer).
2. Final answer, max steps, error/timeout, budget (also repeated identical call).
3. The full history (all earlier tool results) is resent on every iteration, so each call's input is larger than the last; total input is roughly the sum of those growing sizes. See the tokens note.
4. Free, fast, deterministic, and it can say exactly what is wrong. An LLM judge adds cost and its own errors.
5. Generate, verify automatically, feed the failure back, fix, re-verify. A good error says what was wrong and how to fix it, and doesn't leak internals.
6. E.g. infinite loop -> step cap; hallucinated tool -> allow-list; false action claim -> no such tool plus a rule check.
</details>

## 7. Ways to learn it (choose later)

**Start here:** Anthropic, "Building effective agents" (section "Agents" plus the appendices). It is by the vendor's own engineers, short, and defines the loop, when not to use it, and why to start simple; the other sources are longer or narrower.

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Exercises 1-4 with feedback, then 1.4 live | About 45 min |
| B. Another AI tutor | A second explanation and quizzing | About 45 min |
| C. Primary docs and papers | Accurate, citable material | 1.5 hr |
| D. Video or course | Seeing the loop built from scratch | 1.5 hr course, or 13 min talk |

**A. Prompt for a main session in this repo:**
> Walk me through learning/notes/2026-10-02-agent-loops.md. Do exercises 1-4 one at a time: ask me to write the message list and error messages first, then critique. Then quiz me on section 6, and tell me which BUILD_PLAN step each answer shows up in.

**B. Tool:** NotebookLM with the C links as sources. Prompt:
> Using only these sources, explain the tool-calling agent loop (model, tool call, validation, result, repeat), its stop conditions and failure modes, and the difference between open and closed loops. Then give me a 6-question quiz with answers. Sources: https://www.anthropic.com/engineering/building-effective-agents, https://www.anthropic.com/engineering/writing-tools-for-agents, https://arxiv.org/abs/2210.03629, https://arxiv.org/abs/2303.11366, https://genai.owasp.org/llmrisk/llm062025-excessive-agency/

**C. Reading list** (all fetched and opened 2026-10-02 unless noted):
- Anthropic, "Building Effective AI Agents" (Erik S. and Barry Zhang, 2024-12-19): <https://www.anthropic.com/engineering/building-effective-agents>. Read "What are agents?", "When (and when not) to use agents", "Appendix 1: Agents in practice". *(opened)*
- Anthropic, "Writing effective tools for AI agents—using AI agents" (Ken Aizawa et al., 2025-09-11): <https://www.anthropic.com/engineering/writing-tools-for-agents>. Read the part on error messages and response size; this is the "precise error" advice. *(opened)*
- Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (2022): <https://arxiv.org/abs/2210.03629>. Read the abstract and the HotpotQA example trace. *(opened)*
- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning" (2023): <https://arxiv.org/abs/2303.11366>. Abstract and the coding experiments (tests as feedback). *(opened)*
- Andrew Ng, "Agentic Design Patterns Part 2: Reflection", The Batch, 2024-03-27: <https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-2-reflection>. A 2-minute read; see "external tools (unit tests)". *(opened)*
- OWASP, "LLM06:2025 Excessive Agency": <https://genai.owasp.org/llmrisk/llm062025-excessive-agency/>. Why validation and least privilege matter. *(confirmed in search results: title and URL; not opened)*
- OWASP, "LLM01:2025 Prompt Injection": <https://genai.owasp.org/llmrisk/llm01-prompt-injection/>. The indirect-injection section covers tool results. *(opened)*
- OpenAI, "A practical guide to building agents" (PDF, 34 pages): <https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf>. Chapters "Agent design foundations" and "Guardrails". *(opened and text-extracted)*
- LangGraph docs, "Workflows and agents": <https://docs.langchain.com/oss/python/langgraph/workflows-agents>. The agent as a conditional loop between an LLM node and a tool node. *(opened)*
- LangGraph docs, "Graph API overview" (recursion limit): <https://docs.langchain.com/oss/python/langgraph/graph-api>. *(opened)*

**D. Video and courses**
- DeepLearning.AI, "AI Agents in LangGraph" (Harrison Chase and Rotem Weiss; free during the platform beta, about 1.5-1.7 h): <https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/>. Lesson 2, "Build an Agent from Scratch" (12 min), is the loop in plain Python and matches BUILD_PLAN 1.4, then 3 and 5 match 2.1-2.2. *(opened; page lists 1 h 42 min, search snippet said 1 h 32 min)*
- "What's next for AI agentic workflows ft. Andrew Ng of AI Fund" (Sequoia Capital, 2024-03-26, about 13 min): <https://www.youtube.com/watch?v=sal78ACtGTc>. Reflection, tool use, planning, multi-agent in one short talk. *(title and ID confirmed via search results and the fetched YouTube page; channel name taken from search results)*
- Andrew Ng, DeepLearning.AI course "Agentic AI" (about 9 h 55 min, paid Pro membership): <https://www.deeplearning.ai/courses/agentic-ai>. Too long for this weekend; reference only. *(opened)*

Whatever you choose, finish with exercises 1-3 and the self-check.
