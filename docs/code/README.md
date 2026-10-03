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
| [`data/faq.json`](data/faq.json.md) | The FAQ knowledge base for the fictional Georgian operator "ჯიხვი" (Jikhvi): 20 question/answer entries about plans, roaming, SIM cards, payments and branches, stored as JSON. |
| [`faq.py`](faq.py.md) | Stores the ჯიხვი FAQ in a SQLite database built from `data/faq.json`, and provides `lookup_faq(topic)`, which finds the best-matching entries by simple word and stem scoring. |
| [`first_call.py`](first_call.py.md) | A one-shot script that sends one Georgian question to OpenAI's Responses API with `gpt-5.4-mini`, prints the answer, and prints the token counts and the cost of the call. |
| [`graph.py`](graph.py.md) | A LangGraph version of the ჯიხვი customer-service assistant: one node classifies the message, one looks up the FAQ, one writes the Georgian reply, with a terminal chat loop around the graph. |
| [`speech_smoke.py`](speech_smoke.py.md) | A command-line smoke test for Azure Speech in Georgian that records from the microphone, transcribes a WAV file (STT), synthesizes a reply to a WAV file (TTS) and plays WAV files, all from WSL. |
