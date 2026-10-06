# Code docs

One doc per code file, explaining every part of it. Written automatically by the `code-documenter` agent (Stop hook `.claude/hooks/document-code.sh`) whenever a file's content changes. Don't edit by hand. Decisions are in [DECISIONS.md](../../DECISIONS.md); concepts and sources are in [learning/](../../learning/INDEX.md).

| File | What it is |
|---|---|
| [`.claude/hooks/code_docs.py`](_claude/hooks/code_docs.py.md) | Stop-hook worker that finds code files whose content changed and asks a headless Claude session to (re)write one Markdown doc per file under `docs/code/`, then rebuilds the docs index. |
| [`.claude/hooks/decision_logger.py`](_claude/hooks/decision_logger.py.md) | Worker script behind the Stop hook: it reads the last turn of a Claude Code session, asks a headless Sonnet to extract decisions, and appends them to `DECISIONS.md`. |
| [`.claude/hooks/document-code.sh`](_claude/hooks/document-code.sh.md) | A Stop-hook wrapper that skips itself inside child Claude sessions and otherwise runs `code_docs.py`, which rewrites the docs for code files that changed this turn. |
| [`.claude/hooks/log-decisions.sh`](_claude/hooks/log-decisions.sh.md) | A Stop hook wrapper that starts the headless decision logger (`decision_logger.py`) after each Claude turn, unless it is running inside the logger's own child session. |
| [`.claude/settings.json`](_claude/settings.json.md) | Project-level Claude Code settings that register two asynchronous Stop hooks, one that logs decisions and one that updates the code docs, each time Claude finishes a turn. |
| [`chat.py`](chat.py.md) | A terminal chat for the fictional Georgian operator ჯიხვი (Jikhvi) that keeps conversation history and lets the model call a `lookup_faq` tool in a bounded loop. It prints each turn's tool calls, answer and cost. |
| [`check_env.py`](check_env.py.md) | A small script that checks whether the three secrets the project needs (OpenAI key, Azure Speech key, Azure region) are present in `.env`, printing only their lengths, never their values. |
| [`compare_speech.py`](compare_speech.py.md) | Step 2.6a script that runs Roman's recordings through Azure and ElevenLabs Scribe STT and the same FAQ sentences through Azure and ElevenLabs TTS, then lets him rate the TTS clips blind. |
| [`data/faq.json`](data/faq.json.md) | The FAQ knowledge base for the fictional Georgian operator "ჯიხვი" (Jikhvi): 20 question/answer entries about plans, roaming, SIM cards, payments and branches, stored as JSON. |
| [`elevenlabs_api.py`](elevenlabs_api.py.md) | Calls the ElevenLabs HTTP API for Georgian text-to-speech and Scribe v2 speech-to-text, with the same interface as the Azure functions in `speech.py`, so `providers.py` can swap one for the other. |
| [`faq.py`](faq.py.md) | Stores the ჯიხვი FAQ in a SQLite database built from `data/faq.json`, and provides `lookup_faq(topic)`, which finds the best-matching entries by simple word and stem scoring. |
| [`faq_client.py`](faq_client.py.md) | The client side of the ჯიხვი FAQ MCP server: it starts `mcp_server.py` as a subprocess, keeps one connection open, calls `lookup_faq`, and turns every failure into a `FaqToolError`. |
| [`first_call.py`](first_call.py.md) | A one-shot script that sends one Georgian question to OpenAI's Responses API with `gpt-5.4-mini`, prints the answer, and prints the token counts and the cost of the call. |
| [`graph.py`](graph.py.md) | A terminal chat for the ჯიხვი assistant, built as an async LangGraph graph that classifies each message, asks a clarifying question when needed, looks up the FAQ through the MCP server, checks the drafted reply, and hands off to a human with a fixed honest reply when something goes wrong. Its `run_turn` function is shared with the voice loop. |
| [`mcp_server.py`](mcp_server.py.md) | Exposes the ჯიხვი FAQ search from `faq.py` as an MCP server over stdio, so any MCP client can discover and call the `lookup_faq` tool without importing our code. |
| [`providers.py`](providers.py.md) | Defines swappable TTS and STT provider classes (Azure, ElevenLabs) with an automatic Azure fallback, so `voice.py` can switch speech companies through config. |
| [`speech.py`](speech.py.md) | Shared Azure Speech (STT and TTS) and microphone/speaker helpers that go through WSLg's PulseAudio, used by `speech_smoke.py`, `voice.py` and the provider layer. |
| [`speech_smoke.py`](speech_smoke.py.md) | Command-line wrapper (`record`, `stt`, `tts`, `play`) around the speech functions in `speech.py`, used to smoke-test Azure Speech in Georgian from WSL. |
| [`speech_text.py`](speech_text.py.md) | Rewrites a reply into text the Azure Georgian voice can pronounce (prices, times, symbols, English terms), just before TTS, while the on-screen text stays unchanged. |
| [`voice.py`](voice.py.md) | Push-to-talk voice front end for the ჯიხვი assistant: it records or reads a question, transcribes it (Azure or ElevenLabs), runs it through the LangGraph + MCP pipeline, rewrites the reply for speech, synthesizes and plays it, and prints per-stage timings. |
