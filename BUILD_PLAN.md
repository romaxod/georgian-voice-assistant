# Build plan

The ordered list of steps for building this project. Any main session reads this file, finds the **first unchecked step**, and teaches it. So when Roman types **"next"** (or "continue"), work picks up from here. Each step should take about 30–90 minutes.

Status: `[ ]` not started · `[~]` in progress · `[x]` done (with date)

Every step follows the learning loop in PROJECT_CONTEXT.md: why first → Roman types the code → trace it → break it → log decisions → commit.

---

## Phase 0: Setup

- [ ] **0.1 Accounts and keys** *(Roman, no code)*
  - Do: buy $5 of API credit at the chosen LLM provider and **set a monthly spend limit**; create the Azure Speech F0 resource ([SETUP.md](SETUP.md) §1–2); put the keys in `.env`.
  - Learn: API keys vs. subscriptions, why secrets never go in git.
  - Done when: `.env` has both keys, and `git status` doesn't list `.env`.

- [ ] **0.2 Python project environment**
  - Do: create `.venv` on Python 3.14, install the provider SDK and `python-dotenv`, write `requirements.txt`, and load the key from `.env` in a tiny script.
  - Learn: venv, `python -m pip`, `requirements.txt`, environment variables ([SETUP.md](SETUP.md) §3).
  - Done when: `python check_env.py` prints "key loaded" without printing the key itself.

## Phase 1: Text assistant (day 1)

- [ ] **1.1 First LLM call**
  - Do: send one Georgian question to the model from Python and print the answer, the token usage, and the estimated cost.
  - Learn: the messages format, system prompts, response objects, SDK exceptions (wrong key, no credit, network error).
  - Done when: it answers in Georgian, and a wrong key gives a clear error message, not a raw traceback.

- [ ] **1.2 Terminal chat with memory**
  - Do: build a loop where you type, it answers, and the conversation history is kept between turns. Give it a system prompt for the fictional service.
  - Learn: why the model is stateless and *you* resend history; lists of dicts; the system prompt.
  - Done when: a follow-up question ("და რამდენი ღირს?") is answered using the earlier turn.

- [ ] **1.3 The fictional service and its data**
  - Do: decide on the fictional service (log it in the decision log), write ~15–25 FAQ entries, load them into SQLite, and write `lookup_faq(topic)` in plain Python.
  - Learn: SQLite from Python, parameterized queries (why not f-strings → SQL injection), returning JSON-friendly data.
  - Done when: `lookup_faq("ბარათი")` returns matching entries, and a query with a quote character doesn't break it.

- [ ] **1.4 Tool calling**
  - Do: give the model `lookup_faq` as a tool. Validate its arguments, run the function, return the result, and have the model answer from it.
  - Learn: tool schemas, the tool-call loop, why *your code* runs the tool, and what to do with bad arguments or empty results.
  - Done when: an FAQ question is answered from the database (you see the tool call printed), and an off-topic question doesn't call the tool.

- [ ] **1.5 Georgian speech smoke test** *(the riskiest part, so it comes early)*
  - Do: transcribe a recorded Georgian `.wav` with Azure STT, synthesize a Georgian reply to a file with TTS, and play it.
  - Learn: audio formats (sample rate, wav), Azure Speech SDK basics, WSL audio.
  - Done when: you hear Eka or Giorgi speak a reply, and the transcript of your own recording is mostly right. Note the quality in SETUP.md §2.

## Phase 2: Agentic architecture and voice (day 2)

- [ ] **2.1 Rebuild the flow in LangGraph**
  - Do: state (messages, retrieved facts), nodes (understand → look up → answer), and edges.
  - Learn: state, nodes, edges, conditional routing, and how LangGraph runs a graph step by step.
  - Done when: the same questions as 1.4 work, and you can trace one request through every node out loud.

- [ ] **2.2 Clarify, hand off, and fail safely**
  - Do: add routes to ask a clarifying question when a request is ambiguous, to hand off to a human when unsure, and to handle tool errors. Add a step limit.
  - Learn: why a graph beats one prompt here, failure modes, and refusing to claim actions it can't take.
  - Done when: an ambiguous request triggers a clarifying question; a simulated tool error gets an honest reply; "block my card" isn't falsely confirmed.

- [ ] **2.3 MCP server**
  - Do: move `lookup_faq` into a small MCP server (stdio) and test it with the MCP Inspector.
  - Learn: MCP client vs. server, tool discovery, schemas, transports.
  - Done when: the Inspector lists the tool and a call returns FAQ data.

- [ ] **2.4 Connect the graph to MCP**
  - Do: the graph's lookup node calls the tool through an MCP client instead of the Python function.
  - Learn: async/await (MCP clients are async), connection lifecycle, error handling across process boundaries.
  - Done when: 2.1–2.2 behavior is unchanged, and killing the server gives a graceful error.

- [ ] **2.5 Push-to-talk voice loop**
  - Do: press Enter to record, then STT → graph → TTS → playback. Show the transcript, tool call, and time per stage in the terminal.
  - Learn: microphone capture, a pipeline with timing, where the latency goes.
  - Done when: you ask a question out loud and hear a correct answer, and the terminal shows each stage's time.

- [ ] **2.6a (Optional) ElevenLabs ready-made voice** *(only once 2.5 works)*
  - Do: set up ElevenLabs ([SETUP.md](SETUP.md) §4, stage 2). Put TTS behind one small interface, so Azure ↔ ElevenLabs is a config switch with Azure as the automatic fallback. Use a model that lists Georgian (`eleven_v4`, `eleven_v3`, or the low-latency `eleven_v4_turbo`), and check the current docs before choosing.
  - Learn: swappable components (an interface plus a fallback), latency to first audio, and comparing providers fairly.
  - Done when: a config switch changes the voice; ElevenLabs failing falls back to Azure; and a blind rating of 10 Georgian sentences (pronunciation and naturalness, 1–5) plus time to first audio is recorded, Azure vs. ElevenLabs ready-made.

- [ ] **2.6b (Optional stretch) The assistant speaks in Roman's voice** *(limit 2.6a + 2.6b to ~2–3 h in total; never at the expense of Phase 3)*
  - Do: record about 2 min of clean Georgian and create an Instant Voice Clone ([SETUP.md](SETUP.md) §4, stage 3). Swap the voice ID; the code doesn't change.
  - Learn: instant vs. professional cloning, consent requirements, and voice-clone security risks.
  - Done when: the loop speaks in your voice, and the same 10-sentence blind rating now has three columns (Azure / ready-made / your clone), recorded in the README.
  - Rules: say in any demo that it's a consented clone of your own voice. Never commit or share the voice ID or API key.

## Phase 3: Evaluation (day 3)

- [ ] **3.1 Test set**
  - Do: write 20–25 text cases as data (JSON or YAML): ordinary questions, ambiguous ones, missing information, multi-turn, tool failures, and false-action claims. Each case has its expected behavior.
  - Learn: what makes a good eval case, behavior vs. exact wording.
  - Done when: the file covers every category, with at least 3 cases each.

- [ ] **3.2 Eval runner**
  - Do: run every case through the graph and check the tool used, its arguments, and behavior (rules first; an LLM judge only where rules can't decide). Record latency. Save results to `runs/`.
  - Learn: automated checks vs. LLM-as-judge, judge bias, reproducibility.
  - Done when: one command prints a score per category and saves a results file.

- [ ] **3.3 Fix one failure, measure again**
  - Do: read the failures, pick one cause, change one thing (prompt, routing, or tool description), and rerun the same cases.
  - Learn: error analysis, changing one variable at a time.
  - Done when: a before/after table is in the README, and the story of the fix is written down. This becomes the story for the demo.

- [ ] **3.4 Voice check**
  - Do: record 5 spoken versions of test cases, run them end to end, and compare the transcripts and answers with the text results.
  - Learn: how STT errors propagate through the pipeline.
  - Done when: a small results table exists, with one observed STT failure explained (or a note that none occurred).

- [ ] **3.5 README, then make the repo public**
  - Do: write a README covering what it is, an architecture diagram, how to run it, the eval results, and what failed and what you learned. Then check for secrets and make the repo public.
  - Done when: a stranger could understand it in 2 minutes, and `git log -p | grep -i key` finds nothing secret.

## Phase 4: Demo (day 4)

- [ ] **4.1 Demo clip:** script one interaction (~40 s) plus one lesson (~20 s); rehearse and record it.
- [ ] **4.2–4.3 Personal steps** *(local only: `private/CONTEXT.md`)*

---

## Changes to the plan

If a step turns out wrong or too big, edit this file, split the step, and note why here.

- 2026-10-02: Added optional 2.6a/2.6b (ElevenLabs ready-made voice, then a clone of Roman's voice), so each stage changes one thing. Setup is in SETUP.md §4.
