# Build plan

The ordered list of steps for building this project. Any main session reads this file, finds the **first unchecked step**, and implements it. So when Roman types **"next"** (or "continue"), work picks up from here.

Status: `[ ]` not started · `[~]` in progress · `[x]` done (with date)

Every step follows the loop in PROJECT_CONTEXT.md: short why → Claude implements the whole step and runs its "Done when" check and a break test → code docs, decisions and tutor notes are written automatically → Roman reads them and runs the git commit himself. "Learn" lines below are what the docs and tutor notes for that step should cover.

---

## Phase 0: Setup

- [x] 2026-10-02 **0.1 Accounts and keys** *(Roman, no code)*
  - Do: buy $5 of API credit at the chosen LLM provider and **set a monthly spend limit**; create the Azure Speech F0 resource ([SETUP.md](SETUP.md) §1–2); put the keys in `.env`.
  - Learn: API keys vs. subscriptions, why secrets never go in git.
  - Done when: `.env` has both keys, and `git status` doesn't list `.env`.

- [x] 2026-10-02 **0.2 Python project environment**
  - Do: create `.venv` on Python 3.14, install the provider SDK and `python-dotenv`, write `requirements.txt`, and load the key from `.env` in a tiny script.
  - Learn: venv, `python -m pip`, `requirements.txt`, environment variables ([SETUP.md](SETUP.md) §3).
  - Done when: `python check_env.py` prints "key loaded" without printing the key itself.

## Phase 1: Text assistant (day 1)

- [x] 2026-10-03 **1.1 First LLM call**
  - Do: send one Georgian question to the model from Python and print the answer, the token usage, and the estimated cost.
  - Learn: the messages format, system prompts, response objects, SDK exceptions (wrong key, no credit, network error).
  - Done when: it answers in Georgian, and a wrong key gives a clear error message, not a raw traceback.

- [x] 2026-10-03 **1.2 Terminal chat with memory** *(`chat.py`; fictional service: ჯიხვი, a mobile operator)*
  - Do: build a loop where you type, it answers, and the conversation history is kept between turns. Give it a system prompt for the fictional service.
  - Learn: why the model is stateless and *you* resend history; lists of dicts; the system prompt.
  - Done when: a follow-up question ("და რამდენი ღირს?") is answered using the earlier turn.

- [x] 2026-10-03 **1.3 The fictional service and its data**
  - Do: (service already chosen in 1.2: ჯიხვი, a fictional mobile operator) write ~15–25 FAQ entries, starting from the facts in `chat.py`'s system prompt, load them into SQLite, and write `lookup_faq(topic)` in plain Python.
  - Learn: SQLite from Python, parameterized queries (why not f-strings → SQL injection), returning JSON-friendly data.
  - Done when: `lookup_faq("ბარათი")` returns matching entries, and a query with a quote character doesn't break it.

- [x] 2026-10-03 **1.4 Tool calling**
  - Do: give the model `lookup_faq` as a tool. Validate its arguments, run the function, return the result, and have the model answer from it.
  - Learn: tool schemas, the tool-call loop, why *your code* runs the tool, and what to do with bad arguments or empty results.
  - Done when: an FAQ question is answered from the database (you see the tool call printed), and an off-topic question doesn't call the tool.

- [x] 2026-10-03 **1.5 Georgian speech smoke test** *(the riskiest part, so it comes early)*
  - Do: transcribe a recorded Georgian `.wav` with Azure STT, synthesize a Georgian reply to a file with TTS, and play it.
  - Learn: audio formats (sample rate, wav), Azure Speech SDK basics, WSL audio.
  - Done when: you hear Eka or Giorgi speak a reply, and the transcript of your own recording is mostly right. Also record **3 code-switched sentences** (Georgian with English tech words, e.g. "API-ს key როგორ შევცვალო?"), and have TTS read one reply that contains an English word. Note what happens in SETUP.md §2 (code-switching).

## Phase 2: Agentic architecture and voice (day 2)

- [x] 2026-10-03 **2.1 Rebuild the flow in LangGraph** *(`graph.py`)*
  - Do: state (messages, retrieved facts), nodes (understand → look up → answer), and edges.
  - Learn: state, nodes, edges, conditional routing, and how LangGraph runs a graph step by step.
  - Done when: the same questions as 1.4 work, and you can trace one request through every node out loud.
  - Result: all 1.4 questions pass. The TV-packages question (skipped by the model in 1.4) now always goes through lookup, because the graph routes every ჯიხვი question there. Two things left for 2.2/3.1: that lookup returned unrelated entries (matched "პაკეტ"), and the answer said "no information" without offering a human operator.

- [x] 2026-10-03 **2.2 Clarify, hand off, and fail safely**
  - Do: add routes to ask a clarifying question when a request is ambiguous, to hand off to a human when unsure, and to handle tool errors. Add a step limit.
  - Learn: why a graph beats one prompt here, failure modes, and refusing to claim actions it can't take.
  - Done when: an ambiguous request triggers a clarifying question; a simulated tool error gets an honest reply; "block my card" isn't falsely confirmed.
  - Result: new nodes `clarify`, `check`, `handoff`; `lookup` retries once (a cycle). "რამდენი ღირს?" gets a clarifying question, and a second unclear reply hands off. `--simulate-tool-error always` gives the fixed "technical problem" reply, and `once` recovers on the retry. "ბარათი დამიბლოკეთ" → "I can't do it myself" plus the app steps. With a prompt forced to lie, `check` blocked "დავბლოკე". The 2.1 TV-packages case now hands off (`answered=false`) instead of guessing. Found: LangGraph's `recursion_limit` needs N+1 for an N-node path, and can trigger after the reply was already sent.

- [x] 2026-10-03 **2.3 MCP server** *(`mcp_server.py`)*
  - Do: move `lookup_faq` into a small MCP server (stdio) and test it with the MCP Inspector.
  - Learn: MCP client vs. server, tool discovery, schemas, transports.
  - Done when: the Inspector lists the tool and a call returns FAQ data.
  - Result: `mcp` 2.3.0 (v2 SDK: `FastMCP` is now `MCPServer`). The search stays in `faq.py`, and the server wraps it. The Inspector CLI (`--method tools/list`, `tools/call`) shows the input schema (with `minLength`/`maxLength`), an output schema from Pydantic models, and read-only annotations. `ბარათი` returns 3 entries as `structuredContent` plus JSON text. Break tests: empty, too long, missing, or non-string `topic`, and an unknown tool name, each return `isError: true` without reaching our code. A broken DB path gives "the FAQ database failed (OperationalError)", and a quote character gives `[]`. A stray `print()` to stdout didn't crash this SDK's client (it logged "Failed to parse JSONRPC message" and skipped the line), but it breaks the protocol, so logs go to stderr.

- [x] 2026-10-03 **2.4 Connect the graph to MCP** *(`faq_client.py`)*
  - Do: the graph's lookup node calls the tool through an MCP client instead of the Python function.
  - Learn: async/await (MCP clients are async), connection lifecycle, error handling across process boundaries.
  - Done when: 2.1–2.2 behavior is unchanged, and killing the server gives a graceful error.
  - Result: `faq_client.py` keeps one stdio connection to `mcp_server.py` for the whole chat (startup 3–4 s, a call ~0–0.6 s) and turns every failure into `FaqToolError(retryable=...)`. The graph now runs async (`ainvoke`, `astream`, `asyncio.run`). The same 9 questions take the same routes and get the same FAQ entries as the 2.2 code; `--simulate-tool-error once/always` behave as before. Break tests: `kill -9` on the server → that turn says "Connection closed" → `tool_error` hand-off, and the next turn restarts the server (3.4 s) and answers. `SIGSTOP` (hung server) → 5 s timeout → hand-off, and the next turn restarts it. A missing server file → hand-off on every FAQ question, no crash. Found: anyio task groups must be closed by the task that opened them, and LangGraph runs nodes in their own tasks, so the chat loop restarts the server, not the lookup node. `asyncio.run` makes Ctrl-C cancel the main task instead of raising, which a blocking `input()` ignores until Enter, so Python's handler is restored while waiting for input.

- [x] 2026-10-03 **2.5 Push-to-talk voice loop** *(`voice.py`, `speech.py`, `speech_text.py`)*
  - Do: press Enter to record, then STT → graph → TTS → playback. Show the transcript, tool call, and time per stage in the terminal. Add a small **speech-text** step before TTS that makes the answer speakable, e.g. turning English terms into Georgian-script spellings (QR → ქიუარ) or SSML `<sub>`. Required: 1.5 showed Giorgi reads English words as Georgian letters ("ქრ" for QR). Keep the on-screen text unchanged.
  - Learn: microphone capture, a pipeline with timing, where the latency goes.
  - Done when: you ask a question out loud and hear a correct answer, and the terminal shows each stage's time.
  - Roman's spoken check (2026-10-03): "რა ტარიფები გაქვთ?" was transcribed exactly and answered correctly out loud (STT 2.0 s + graph 3.9 s + TTS 1.2 s = 7.1 s on the first, cold turn; 4.5–5.1 s after). Both code-switched questions broke in STT: "eSIM როგორ გავააქტიურო?" → "ეს წინ როგორ გავააქტიურო?" → the plan-change answer (wrong topic, answered=true); "QR კოდი…" → "ქიუ არკადი რაღა დავასკანერო?" → intent=other, "not about ჯიხვი" (wrong). Not fixed on purpose: they're eval cases for 3.1 (spoken/code-switched, and "misheard question classified as other") and the baseline for 2.6a's Scribe v2 and 3.4.
  - Result (Claude's part, 2026-10-03): `speech.py` now holds the Azure/PulseAudio functions (raising `SpeechError`; `speech_smoke.py` is its CLI), plus a `Recorder` thread for push-to-talk. `speech_text.py` rewrites a reply for the voice (₾ → ლარი, 0.50 ₾ → 50 თეთრი, 10:00-დან → 10 საათიდან, 24/7, GB, SIM/eSIM, QR → ქიუარ, other acronyms letter by letter, Georgian suffixes glued on). TTS → STT round trips: prices, times and plan names now come back exactly (before: ₾ silent, "10 0 0 დან", "S" gone). `graph.py`'s turn became `run_turn()`, shared by text and voice. With Roman's 1.5 recordings (`--wav`): 3.6–5.1 s from end of question to start of reply (STT 1.2–1.4 s, graph 1.4–2.7 s, TTS 1.0–1.2 s). STT errors flow through: "რომ მინი" (q1) got a clarifying question about a "mini package". Break tests: wrong Azure key → readable 401 line, loop goes on; silence → "ვერ გავიგე" without touching the graph; no PulseAudio → "couldn't open the microphone", loop goes on; quiet mic → "almost silent". Found: on WSLg the first mic read arrives ~0.5 s after opening, so `Recorder.start()` waits for audio before showing "● recording". Startup takes ~15 s because importing `openai` reads thousands of small files over `/mnt/c` (only startup; not per turn).

- [x] 2026-10-06 **2.6a (Optional) ElevenLabs ready-made voice** *(`providers.py`, `elevenlabs_api.py`, `compare_speech.py`)*
  - Do: set up ElevenLabs ([SETUP.md](SETUP.md) §4, stage 2). Put TTS behind one small interface, so Azure ↔ ElevenLabs is a config switch with Azure as the automatic fallback. Use a model that lists Georgian (`eleven_v4`, `eleven_v3`, or the low-latency `eleven_v4_turbo`), and check the current docs before choosing.
  - Learn: swappable components (an interface plus a fallback), latency to first audio, and comparing providers fairly.
  - Done when: a config switch changes the voice; ElevenLabs failing falls back to Azure; and a blind rating of 10 Georgian sentences (pronunciation and naturalness, 1–5) plus time to first audio is recorded, Azure vs. ElevenLabs ready-made.
  - Also (1.5 confirmed Azure STT fails on every English word, see SETUP.md §2): try ElevenLabs **Scribe v2** with **keyterms** ("API", "LangGraph", "MCP", ...) on the same code-switched recordings. STT goes behind the same kind of swappable interface.
  - Result (code, 2026-10-03): `providers.py` puts TTS and STT behind one interface each (`synthesize(text, timing)` → WAV bytes, `transcribe(path)` → text). `TTS_PROVIDER` / `STT_PROVIDER` in `.env` (or `--tts` / `--stt` on `voice.py`) pick Azure or ElevenLabs, and `WithFallback` sends a failed call to Azure. `SpeechError` gained `retryable`: a missing or rejected key turns ElevenLabs off for the session, while a network error falls back for that turn only. `elevenlabs_api.py` calls the HTTP API directly with httpx (`/v1/text-to-speech/{voice}/stream` as `pcm_24000`, `/v1/speech-to-text` with `scribe_v2`, `language_code=kat` and keyterms). `voice.py` prints the provider and the time to first audio. Keyterms (18) come from the FAQ's Latin terms plus a few domain words; "API" and "key" are left out on purpose, so c1/c2 test Scribe without help. Azure baseline (`compare_speech.py stt`, Roman's q1, c1–c4): **WER 83%, English terms 2/10**. Azure Giorgi's first audio comes 0.6–1.05 s after the request, and all of it 1.4–1.6 s after. Break tests: no key → both STT and TTS fall back to Azure, the turn completes, and ElevenLabs stays off for the session; a fake key → real `HTTP 401: invalid_api_key` from ElevenLabs, shown as one line → Azure; connection refused → Azure for that turn, ElevenLabs tried again on the next turn.
  - Scribe run (2026-10-06, `compare_speech.py stt`, Roman's q1, c1–c4; one change per column): mean WER **Azure 83% → Scribe v2 73% → Scribe v2 + keyterms 46%**, English terms 2/10 → 2/10 → 4/10, 1.3 / 1.8 / 1.5 s per 5 s file. Keyterms fixed c4 ("SIM-ის QR კოდი email-ზე მომივა?", WER 14%; only the e of eSIM lost) and c3 (exact). Plain Scribe got "API-ს" right in c1 without help, but with keyterms it became "BPI-ს": the bias pulls toward Latin spellings, sometimes the wrong one. q1 got worse ("1000 ევრო პაში" / "სომხი" for "როუმინგი", vs Azure's "რომ მინი"). c2 failed everywhere. Free plan: library voices give HTTP 402, premade voices work; ElevenLabs TTS first audio 0.85–1.0 s, done 3–5 s for an 80-character sentence (Azure 1.4–1.6 s).
  - Blind TTS rating (2026-10-06, `compare_speech.py tts` + `rate`; 10 FAQ answers after speech-text, 934 characters each; Roman rated 20 clips in random order). ElevenLabs used the premade voice Brian, Roman's pick by ear from 4 premade male voices:

    | Provider | Pronunciation (1–5) | Naturalness (1–5) | First audio (median) | Whole reply (median) |
    |---|---|---|---|---|
    | Azure `ka-GE-GiorgiNeural` | 2.3 | 1.6 | 0.74 s | 1.23 s |
    | ElevenLabs `eleven_v4_turbo`, Brian | **4.8** | **3.9** | 0.62 s | 3.78 s |

    ElevenLabs won on all 10 sentences (pronunciation 4–5 vs 1–4). Caveats: one rater, and the two voices sound different, so "blind" only hides which provider is which, not that two voices take turns. Trade-off: the voice loop plays a reply only once all of it has arrived, so ElevenLabs adds ~2.5 s of silence per turn; playing the stream as it arrives would remove that (possible follow-up, not done).
  - End-to-end check (2026-10-06, `voice.py --wav audio/c4.wav --stt elevenlabs --tts elevenlabs`): Scribe heard "SMS QR კოდი email-ზე მომივა?" (the compare run had "SIM-ის": Scribe isn't deterministic run to run). The graph honestly handed off ("not in the FAQ"). But ElevenLabs TTS took **15.1 s** for a 140-character reply (first audio 2.2 s), so 22.8 s passed before the reply started. In the comparison, generation ran at roughly the speed of speech (7.5 s of audio took 7.7–9.9 s on some sentences), so streaming playback could stutter too. Conclusion for now: Scribe + keyterms for STT (more accurate, same speed); for TTS, ElevenLabs sounds far better, but with play-after-download it's too slow for a live turn.

- [ ] **2.6b (Optional stretch) The assistant speaks in Roman's voice** *(limit 2.6a + 2.6b to ~2–3 h in total; never at the expense of Phase 3)*
  - Do: record about 2 min of clean Georgian and create an Instant Voice Clone ([SETUP.md](SETUP.md) §4, stage 3). Swap the voice ID; the code doesn't change.
  - Learn: instant vs. professional cloning, consent requirements, and voice-clone security risks.
  - Done when: the loop speaks in your voice, and the same 10-sentence blind rating now has three columns (Azure / ready-made / your clone), recorded in the README.
  - Rules: say in any demo that it's a consented clone of your own voice. Never commit or share the voice ID or API key.

## Phase 3: Evaluation (day 3)

- [ ] **3.1 Test set**
  - Do: write 20–25 text cases as data (JSON or YAML): ordinary questions, ambiguous ones, missing information, multi-turn, tool failures, false-action claims, and **code-switched** questions (Georgian with English words). Each case has its expected behavior.
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
  - Do: record 5 spoken versions of test cases (at least 2 code-switched), run them end to end **one at a time** (Azure F0 allows 1 concurrent STT request), and compare the transcripts and answers with the text results. If you tried Scribe v2 in 2.6a, compare both STT providers on the same recordings.
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
- 2026-10-02: Added code-switching (Georgian + English words) checks to 1.5, 2.5, 2.6a, 3.1, and 3.4 after finding that Azure STT can't switch languages mid-sentence and has no phrase lists for ka-GE.
- 2026-10-03: Switched from Roman typing the code to Claude implementing each whole step. Roman learns from auto-generated code docs (`docs/code/`), DECISIONS.md and tutor notes instead, and still runs git himself. Reason: typing a few lines per turn and answering quiz questions was too slow for a 3–4 day build.
- 2026-10-03: The fictional service is chosen in 1.2 instead of 1.3, because 1.2's system prompt and its "და რამდენი ღირს?" check need a service with prices. 1.3 moves those facts into SQLite.
- 2026-10-03: 2.5's speech-text step and 2.6a's Scribe v2 test changed from "if needed" to required/confirmed. Step 1.5 found Azure TTS reads English words letter by letter in Georgian, and Azure STT failed on every English word in Roman's recordings.
