# Failure handling and guardrails in a conversational assistant

Date: 2026-10-03. Built from step 2.2 (`graph.py`). Checked by reading `graph.py`, running the regex on sample sentences, reading the installed `langgraph/types.py`, and opening the OWASP LLM06, Microsoft Copilot Studio fallback and LangGraph docs pages listed in section 7. Related notes (not repeated here): hand-off wording and "no false action claims" in the prompt are in [system prompts and memory](2026-10-03-system-prompts-and-memory.md); guardrails and human-in-the-loop as architecture are in [agentic architectures](2026-10-02-agentic-architectures.md); verifiers and false action claims in [agent loops](2026-10-02-agent-loops.md); the LangGraph API side of 2.2 (cycles, `update_state`) is in [LangGraph in practice](2026-10-03-langgraph-in-practice.md).

## 1. What you're learning, and why it matters

**Problem:** the happy path of a chatbot is easy. A real customer service cares about the other paths: the customer says something vague, the search finds nothing useful, the database is locked, the model says "I blocked your SIM" when it can't. Each needs a decided, tested response. Otherwise the system guesses, and a guess in customer service is a wrong answer or a false promise.

**The failure modes and what 2.2 does about each**

| Failure | Control in `graph.py` | Kind |
|---|---|---|
| Ambiguous message ("რამდენი ღირს?") | `understand` returns intent `ambiguous`, `clarify` asks one question | LLM classifies, code routes |
| Still unclear after asking | `clarify_turns >= MAX_CLARIFY_TURNS` (1) -> hand off `still_unclear` | counter in state |
| No or irrelevant retrieval | `lookup` finds nothing -> `no_facts`; `answer` sets `answered=false` -> `check` blocks -> `not_answered` | code + model verdict |
| Tool error (DB locked) | retry once (cycle), then `tool_error` hand-off | code |
| False action claim | regex in `check` -> `false_action_claim` | code backstop |
| Runaway loop | `recursion_limit` = 10 | framework limit |
| Model output doesn't parse | `parsed is None`: `understand` falls back to a plain search; `answer` returns an empty draft that `check` blocks | code |
| Customer asks for a human | intent `human` -> `asked_for_human` | LLM classifies, code routes |

**Clarify, guess or hand off?** Clarify when two or more quite different readings exist and the earlier turns don't pick one. Guess (pick the likely reading) when one is clearly most likely: "და რამდენი ღირს?" after a roaming question stays `faq`. Hand off when asking again won't help. Cap clarification loops, because a bot that keeps asking is worse than one that gives up. Microsoft's guidance says at most two fallback questions per session; we use one clarification (`MAX_CLARIFY_TURNS = 1`) because voice turns are slow.

**Hand-off design.** A good hand-off passes a *reason* and *context* to the human (here `handoff_reason` and `handoff_note`, printed by the `handoff` node; a real system would create a ticket with the transcript, so the customer doesn't repeat themselves). The customer-facing wording must be honest: our assistant can't transfer a call, so `asked_for_human` says exactly that and points to the app chat and branches. A fake "transferring you now" is a false action claim of its own.

**Fixed templates vs generated text.** `handoff` makes no LLM call: one fixed Georgian string per reason. Why: failure replies must work when the model is the thing failing (outage, bad output, injection), they are reviewable by compliance, and they cost nothing. The price is that they can sound stiff; that is acceptable for failure paths. For `false_action_claim` it appends the top FAQ answer, which is vetted text.

**Model self-verdict gating.** `Draft(reply, answered: bool)` makes the model say whether the FAQ entries contained the answer; plain-Python `check` acts on it. This fixed 2.1's TV-packages case (retrieval returned unrelated "პაკეტ" entries, the model guessed). **Limit:** it is self-reported. The same model that missed the mismatch can claim `answered=true`. Phase 3 should measure it with labeled cases and, later, a groundedness check by a separate LLM judge or an entailment model (the DeepLearning.AI guardrails course covers one).

**Deterministic output check (the regex).** `FALSE_ACTION_CLAIM` looks for first-person action stems (`დავბლოკ`, `შეგიცვ`...). Georgian is agglutinative, so we match the stem plus `\w*` for the ending. `(?<!ვერ )(?<!არ )` skips negated forms: I ran it, "თქვენი SIM დავბლოკე." matches, "ვერ დაგიბლოკავთ" and "მე არ დაგიბლოკავ" don't. Offline test result from the session: 10 of 10 right (6 claims caught, 4 honest sentences allowed).
- A **false positive** (blocks an honest sentence) costs a needless hand-off. A **false negative** (misses a claim) lets a false promise through. For customer service the second is worse, so the stem list is broad.
- It misses paraphrases and other negation ("never"), so it is **defense in depth**: the main control is the prompt (`ANSWER_PROMPT` plus `CONTEXT_ACTION`) and, most importantly, the system has no tool that could perform the action. OWASP LLM06 Excessive Agency lists excessive functionality, permissions and autonomy as the root causes; the best fix is removing the capability, not detecting words.

## 2. In this repo

- **Break test for `check`.** A scratch script replaced `graph.ANSWER_PROMPT` with one that told the model to confirm actions. With `CONTEXT_ACTION` still present, the model still refused ("მე თავად ვერ დაგიბლოკავთ..."). After blanking `CONTEXT_ACTION` too, the draft said "თქვენი SIM დავბლოკე." and the trace showed `[check] blocked: false_action_claim (draft claimed 'დავბლოკე' ...)`, then the hand-off reply. Two layers of prompt had to be removed before the model misbehaved; the third layer (regex) then caught it. Module globals can be patched because `answer` reads `ANSWER_PROMPT` at call time.
- **Real conversations:** "რამდენი ღირს?" -> ambiguous -> question; "როუმინგის პაკეტი" -> `faq`, answered. "პაკეტი მინდა" -> question; "არ ვიცი, რაღაც" -> `still_unclear` hand-off. "ბარათი დამიბლოკეთ..." -> `action` -> "I can't do that myself, to block the SIM...". "ოპერატორთან დამაკავშირე" -> `asked_for_human`. Cost per turn about $0.0006-0.0015.
- **Tool errors:** `python graph.py --simulate-tool-error once` shows "try 1: database is locked (simulated) -> retry", "try 2: 2 entries", correct answer. `always` ends in `tool_error` and "ბოდიში, ტექნიკური შეფერხების გამო...".

## 3. How the pieces fit together

Each node that detects a problem only *writes* `handoff_reason`; routers only *read* it; one `handoff` node turns the reason into text. Adding a failure mode means one reason, one template, and one check.

```
understand --problem/human/2nd ambiguous--> handoff
    |--ambiguous--> clarify -> END
    |--faq/action--> lookup (retry once) --nothing/error--> handoff
    |                  v
    |               answer -> check --draft blocked--> handoff
    |--other-----------^        |--ok--> END
```

**Why a graph beats one prompt here.** One big prompt ("if unsure, hand off; never claim actions; ask once") is advice the model may ignore, can't count turns, can't retry a DB call, and can't be unit tested per route. The evil-prompt break test is the evidence: the prompt was sabotaged and the model's output was still stopped by code. In a graph, the rules that must hold are code in routers and checks; the model only does language work (classify, draft).

## 4. Related tools

- **Guardrails AI** and **NVIDIA NeMo Guardrails**: libraries for input/output rails (topic control, PII, jailbreak, groundedness, self-check by a second LLM call). We hand-wrote two checks to understand them, and they add dependencies and latency; for production you would evaluate them. Moderation endpoints (OpenAI) cover harmful content, not "claimed an action".
- **LangGraph `interrupt()`**: pauses the graph and waits for a human, resumed with `Command(resume=...)`. That is for a human *inside* the flow (approvals). Our `handoff` ends the bot's turn instead, because the live agent system is outside this project.
- **LLM-as-judge groundedness** (Phase 3): a second model checks whether the reply is supported by the facts. More flexible than a regex, but it costs a call and can be wrong too.

## 5. Hands-on exercises

1. Run `.venv/bin/python graph.py`. Send "რამდენი ღირს?", then "არ ვიცი". Check: `clarify`, then `[understand] ... hand off: still_unclear`. Then `/reset` and send "რამდენი ღირს?", "როუმინგი ევროპაში". Check: answered normally.
2. `.venv/bin/python graph.py --simulate-tool-error once`, ask a roaming question. Check: `try 1 ... retry`, `try 2: ... entries`. Repeat with `always`: two tries, then `reason=tool_error`.
3. In a scratch script (not in the repo): `from graph import false_action_claim`. Try 10 sentences you write: 5 claims, 5 honest ones incl. "ვერ"/"არ" forms and a paraphrase ("თქვენი ბარათი უკვე დაცულია"). Check: which paraphrases slip through (false negatives)?
4. Break test: in a scratch script set `graph.ANSWER_PROMPT` to a prompt telling the model to confirm actions and `graph.CONTEXT_ACTION = ""`, build a graph, ask "ბარათი დამიბლოკეთ". Check: `[check] blocked: false_action_claim` or the model still refuses. Say which layer held.
5. Write down one eval case per route (clarify, still_unclear, human, no_facts, tool_error, false claim, honest action refusal) with expected `handoff_reason`. Check: each is decidable from graph state without reading the reply, which is how Phase 3 can score routes automatically (route accuracy, hand-off rate, false-claim rate, answered-but-wrong rate).

## 6. Self-check: can you answer these without looking?

1. Why does `handoff` not call the model? 2. When do we clarify, guess, and hand off? 3. What is the limit of `answered`? 4. Why are false negatives worse than false positives in the claim regex? 5. Why is the regex not the main defense against false claims? 6. Why is a graph better than one long prompt for these rules?

<details><summary>Answers</summary>

1. Failure replies must work when the model is the failure, and they should be fixed, reviewable text. 2. Clarify with two plausible different readings; guess when one is clearly likely or history settles it; hand off after the clarify cap, no facts, errors, or a human request. 3. It's the model grading itself; it can be confidently wrong, so Phase 3 measures it and may add an independent judge. 4. A missed claim is a false promise to a customer; a false positive only sends them to a human. 5. It misses paraphrases; the real controls are the prompt and the absence of action tools (OWASP LLM06). 6. Code enforces counters, retries, routing and checks and can be tested per route; a prompt is only a request.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-5 on this repo | 45 min |
| B. Another AI tutor | Failure-mode quiz, eval-case brainstorming | 45 min |
| C. Primary docs | OWASP risk, hand-off design, interrupts | 2 h |
| D. Video/course | Seeing guardrails built | 1.5-3 h |

**A.** Paste: "Read learning/notes/2026-10-03-failure-handling-and-guardrails.md and graph.py. Walk me through exercises 1-5, run each command, and explain each result as a failure mode, its control, and how Phase 3 would measure it."

**B.** NotebookLM loaded with the C links, or ChatGPT/Gemini. Prompt: "Using only these sources (https://genai.owasp.org/llmrisk/llm062025-excessive-agency/, https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/cux-fallbacks, https://docs.langchain.com/oss/python/langgraph/interrupts, https://www.anthropic.com/engineering/building-effective-agents), explain how a customer-service bot should handle ambiguity, tool errors, hand-off and false action claims. Then quiz me with 6 questions and ask me to design 5 eval cases."

**C.**
- OWASP, "LLM06:2025 Excessive Agency": <https://genai.owasp.org/llmrisk/llm062025-excessive-agency/>. Definition, root causes (functionality, permissions, autonomy), mitigations. *(opened via search result summary)*
- Microsoft, "Design graceful fallbacks and handoffs": <https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/cux-fallbacks>. Conversation-design view: seek understanding, disambiguate, be transparent, at most two fallback questions, smooth hand-off. *(opened)*
- LangGraph, "Interrupts": <https://docs.langchain.com/oss/python/langgraph/interrupts>. `interrupt()` and `Command(resume=...)`, approval and review patterns. *(opened)*
- Anthropic, "Building effective agents": <https://www.anthropic.com/engineering/building-effective-agents>. Stopping conditions and human checkpoints. *(cited in the agent-loops note; my fetch failed today, so not re-opened)*
- NVIDIA NeMo Guardrails, output rails: <https://docs.nvidia.com/nemo/guardrails/getting_started/5_output_rails/README.html>. What an output rail is. *(seen in search results, not opened)*

**D.**
- DeepLearning.AI, "Safe and Reliable AI via Guardrails" (Shreya Rajpal, Guardrails AI; short course, 1 h 32 min, free): <https://www.deeplearning.ai/short-courses/safe-and-reliable-ai-via-guardrails> . Lessons on failure modes in RAG apps, hallucination checks with NLI, keeping a bot on topic, PII. Details confirmed in search results.
- LangChain's YouTube walkthrough of `interrupt` for human-in-the-loop agents: <https://youtu.be/6t7YJcEFUIY>, linked from the LangChain blog post "Making it easier to build human-in-the-loop agents with interrupt" (The LangChain Team, 2024-12-14; blog opened). I could not confirm the video's own title or watch it.
- For repair and fallback in conversation design I found only articles, no video I could verify; search terms: "conversation design fallback and handoff", "chatbot repair strategies".
