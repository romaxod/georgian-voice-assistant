# Claude Code hooks and headless `claude -p`

Date: 2026-10-02. Checked against code.claude.com docs (hooks reference as raw markdown, hooks guide, CLI reference, headless, permissions) and against the real files in this repo, using Claude Code 2.1.287. CLAUDE.md vs. hooks is already covered in the [subagents note](2026-10-01-claude-code-subagents.md) (sections 2 and 4); this note is about how a hook actually works.

## 1. What you're learning, and why it matters

**Problem: an instruction can be skipped.** You wanted every decision logged, so you can explain it later. "Remember to log decisions" in CLAUDE.md is a request the model may forget. A **hook** is a command that Claude Code itself runs at a fixed point in its lifecycle, so it happens every time, whatever the model decides.

- **Hook:** a handler (usually a shell command) attached to an **event**. Configured under `"hooks"` in a settings file, grouped by event name, optionally filtered by a `matcher` (e.g. tool name).
- **Main events** (full list in the reference): `SessionStart` (session begins or resumes), `UserPromptSubmit` (you send a prompt, before Claude sees it), `PreToolUse` (before a tool runs; can block it), `PostToolUse` (after it succeeds), `Stop` (Claude finishes responding, once per turn), `SubagentStop` (a subagent finishes), `PreCompact` (before context compaction), `SessionEnd`, `Notification`.
- **Five hook types:** `command` (shell), `http` (POST to a URL), `mcp_tool` (call an MCP tool), `prompt` (one LLM call returns `{"ok": true}` or `{"ok": false, "reason": ...}`), `agent` (a subagent with Read/Grep/Glob checks; marked experimental).
- **Which events take `prompt`/`agent`:** the sources you saw disagree, so I checked. The reference page lists `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`, `PermissionDenied`, `Stop`, `SubagentStop`, `UserPromptSubmit`, `UserPromptExpansion`, `TaskCreated`, `TaskCompleted`, `TeammateIdle` as supporting **all five** types. So `Stop` does support them, and the hooks guide has a `Stop` + `prompt` example. `PermissionRequest` takes `prompt` but not `agent`. `PreCompact`, `Notification`, `SubagentStart`, `SessionEnd` and others are command/http/mcp_tool only; `SessionStart` and `Setup` are command/mcp_tool only. The "only tool events" claim is out of date. (A summarizer I first used to fetch the reference got this wrong too; the raw page is authoritative. Lists change between versions, so re-check.)
- **Input:** a command hook gets one JSON object on **stdin**: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `permission_mode`, plus event-specific fields. `Stop` adds `stop_hook_active` (true when Claude is already continuing because of a stop hook) and `last_assistant_message`.
- **Output:** exit code `0` = success (stdout is JSON control output if it looks like JSON). Exit `2` = **block** on events that can block (`PreToolUse` blocks the call, `UserPromptSubmit` blocks the prompt, `Stop` makes Claude keep going); stderr becomes the reason. Any other code (including 1) is a non-blocking error, so use 2 to enforce. JSON on exit 0 can carry `decision: "block"` + `reason`, `continue: false`, `systemMessage` (a warning to you), and `additionalContext` (text for Claude).
- **`async`:** `"async": true` runs the hook in the background: the session doesn't wait, its output is discarded, and Claude Code does **not** enforce `timeout`. `"asyncRewake": true` also runs in the background but if the hook exits `2` it wakes Claude with the stderr as a reminder (timeout is enforced).
- **Where configured:** `~/.claude/settings.json` (all projects), `.claude/settings.json` (this project, committed), `.claude/settings.local.json` (this project, gitignored), managed policy, plugin `hooks.json`, and skill/subagent frontmatter. `/hooks` lists everything and where it came from.
- **Trust and security:** a hook is arbitrary code running with **your** permissions. Project hooks wait for the workspace-trust dialog in interactive sessions, but a `claude -p` run shows no dialog and **does run** a project's `.claude/settings.json` hooks even in a never-trusted folder (permissions page, "What runs before you trust a folder"). Rule: read `.claude/settings.json` and `.claude/hooks/` of any repo before running `claude` in it.

**Headless `claude -p`** runs one non-interactive turn and prints the answer, so a script can use Claude like any command.
- Input from stdin or argument; `--output-format text|json|stream-json` (json has `result`, `session_id`, `total_cost_usd`).
- `--tools ""` removes all built-in tools; `--settings '<json or file>'` overrides keys for this run; `--setting-sources user,project,local` picks which settings files load; `--no-session-persistence` writes no session to disk; `--model sonnet` picks the model.
- `--bare` skips hooks, skills, plugins, MCP, auto memory and CLAUDE.md for faster, reproducible starts, and the docs call it the recommended scripted mode. But "in bare mode, Claude Code never reads OAuth credentials or the system keychain", so it needs `ANTHROPIC_API_KEY`. You log in with a subscription, so we couldn't use it.

**Two more ideas.** *Recursion:* a hook that starts Claude creates a Claude session that has its own `Stop` event, which can start the hook again, forever. *Race condition:* two writers appending to one file at once can interleave or clobber lines; `fcntl.flock` makes one wait for the other.

## 2. In this repo

`.claude/settings.json` (whole file): one `Stop` hook, `type: command`, `async: true` (a `timeout: 300` was removed 2026-10-02 because async hooks ignore it), running `"$CLAUDE_PROJECT_DIR"/.claude/hooks/log-decisions.sh`. Note `timeout` is ignored for async hooks, so the real limit is `timeout=280` inside the Python `subprocess.run`.

One turn, end to end:
1. Claude finishes its reply, `Stop` fires, Claude Code starts `log-decisions.sh` in the background and pipes the hook JSON to it. You don't wait.
2. `log-decisions.sh`: if `DECISION_LOGGER_CHILD=1`, `exit 0`. Otherwise `exec python3 decision_logger.py` (stdin passes through).
3. `decision_logger.py` `main()`: exits quietly if `.claude/decision-logger/disabled` exists. Reads the hook JSON, takes `transcript_path`.
4. `last_turn()` parses the **transcript**: a JSONL file, one JSON object per line, with `type` values such as `user`, `assistant`, `system`, `attachment`. User/assistant entries have `message.content` (a string, or blocks of type `text`, `tool_use`, `tool_result`). The turn starts at the last entry where `is_human_prompt()` is true: `type == "user"`, not `isMeta`, not a sidechain (subagent) entry, and with text rather than `tool_result` blocks (tool results are also `user` entries, which is why that check exists). Tool calls are shortened by `summarize_tool_use`, and the excerpt is capped at 40,000 characters.
5. It builds a prompt: the body of `.claude/agents/decision-logger.md` (frontmatter stripped), today's date, the last 40 titles from `DECISIONS.md` (dedupe), and the excerpt.
6. It runs `claude -p --model sonnet --tools "" --settings '{"disableAllHooks": true}' --no-session-persistence` with the prompt on stdin, `cwd` = a temp dir (so the project's CLAUDE.md and settings aren't loaded), and `DECISION_LOGGER_CHILD=1` in the environment.
7. The output is `NONE` or entries starting at `### `. Entries are appended to `DECISIONS.md` under `fcntl.flock(LOCK_EX)`. Every outcome writes a line to `.claude/decision-logger/runs.log` (`ok: 2 entries`, `ok: NONE`, `skip: ...`, `error: ...`); a `try/except` makes sure logging can never break your session.

Results so far: a pipe test took about 14 s and added 2 entries (`runs.log`: `ok: 2 entries`). One entry needed a hand correction because a code excerpt was cut off by the length limits in step 4.

Three separate guards against recursion: the env var, `disableAllHooks` in the child, and the temp-dir `cwd`.

Two caveats seen here. (a) The hook was written mid-session. The docs say the file watcher "normally picks up hook changes automatically", and `/hooks` shows what is loaded; if a new session shows no log lines after a turn, open `/hooks` or restart. (b) A skipped run writes `skip: disabled` to `runs.log` when the off switch is on. *(Updated 2026-10-02: it used to leave no line.)* (c) This session was started in the parent `ABSTR ASSN` folder, so it loaded that folder's settings, not the repo's. The hook only runs in sessions started **inside** `georgian-voice-assistant/`.

## 3. How the pieces fit together

```
 Roman <-> MAIN SESSION --turn ends--> Stop event
                                          | (async: session doesn't wait)
                                          v
                            log-decisions.sh  --env CHILD=1? --> exit
                                          v
                            decision_logger.py  --disabled file? --> exit
                              reads transcript JSONL (path from stdin JSON)
                              flock + append <------------------+
                                          v                      |
                  claude -p --tools "" (HEADLESS CHILD, temp dir, hooks off)
                              returns "NONE" or "### ..." entries --> DECISIONS.md
```

Deterministic plumbing (the hook, parsing, locking) wraps one non-deterministic step (the model's judgment about what counts as a decision).

## 4. Related tools

- **Prompt/agent hooks:** could do the judging without our own `claude -p` call, but they return an allow/block verdict, not free-form text appended to a file; a command hook plus `claude -p` fits "write entries" better.
- **`SubagentStop`, `SessionEnd`** instead of `Stop`: one log per session would be cheaper but loses per-turn detail.
- **`asyncRewake`:** would let a failed logger tell Claude; we'd rather stay silent and use `runs.log`.
- **Agent SDK** (Python/TypeScript): the library version of `claude -p`; more control, more code. Next step up if the shell-out grows.
- **`--bare`:** best for scripts when you use an API key (see section 1).
- **Plugins** can bundle hooks to share them.

## 5. Hands-on exercises

1. Read `.claude/settings.json`, `log-decisions.sh` and `decision_logger.py`, and write the 7 steps of section 2 from memory. Check: you can point to the line for each step (e.g. the `DECISION_LOGGER_CHILD` test, the `flock` call).
2. Run the pipe test by hand (about 15 s, one Sonnet call). Pick any transcript from `~/.claude/projects/-mnt-c-prog-ABSTR-ASSN/*.jsonl`:
   `printf '{"transcript_path":"%s"}' <path> | CLAUDE_PROJECT_DIR=$PWD .claude/hooks/log-decisions.sh`
   Check: `tail -3 .claude/decision-logger/runs.log` shows `ok: N entries` or `ok: NONE`, and `tail -30 DECISIONS.md` shows new entries if N > 0. Fix or delete test entries by hand.
3. Toggle the off switch: `touch .claude/decision-logger/disabled`, repeat exercise 2, then `rm .claude/decision-logger/disabled`. Check: `runs.log` gets **no** new line and `DECISIONS.md` is unchanged (the check happens before logging). Why is a missing log line harder to notice than an error line?
4. Run `/hooks` in a session. Check: you see `Stop` with this command and its source (project settings). Find one event that isn't configured and read its description.
5. Look at a transcript: `head -c 600 <path>` and `python3 -c "import json,collections,sys; print(collections.Counter(json.loads(l).get('type') for l in open(sys.argv[1])))" <path>`. Check: you can name which entries `is_human_prompt` accepts and why `tool_result` entries (also `type: user`) are rejected.
6. Predict, without running: remove the `DECISION_LOGGER_CHILD` check. What happens? Reason through it: the child is a Claude session, so it has its own `Stop` event. Which other guards stop a loop (`disableAllHooks`, the temp `cwd`, and `--no-session-persistence`, which probably leaves no transcript file for the hook to read)? What would have to be missing for an endless chain of paid Sonnet calls? Don't test it; an unbounded loop costs real usage.

## 6. Self-check: can you answer these without looking?

1. Why is a hook more reliable than a CLAUDE.md instruction, and what can't it do?
2. What does exit code 2 do on `PreToolUse` and `Stop`, and why isn't exit 1 enough to block?
3. What does `async: true` change, and why did we remove `timeout: 300` from `settings.json`?
4. Why can a hook that launches `claude` call itself, and which three guards does this repo use?
5. Why does `is_human_prompt` exclude `tool_result` entries, and why was `--bare` rejected?
6. What goes wrong without `flock` when two turns finish together, and what does it cost to leave the hook on?
7. Why read a repo's `.claude/settings.json` before running `claude` in it?

<details>
<summary>Answers</summary>

1. Claude Code runs it at the event itself, so the model can't forget or skip it. It can't judge intent by itself (that's why we call a model inside it).
2. `PreToolUse`: the tool call is blocked, stderr goes to Claude as the reason. `Stop`: Claude is prevented from stopping and continues. Exit 1 is a non-blocking error: the action proceeds.
3. The hook runs in the background, its output is discarded, and Claude Code doesn't enforce `timeout`. The 280 s limit is the `subprocess.run` timeout in the Python.
4. The child is a full Claude session with its own `Stop` event. Guards: `DECISION_LOGGER_CHILD=1` early exit, `disableAllHooks` via `--settings`, and running from a temp dir so project settings aren't loaded.
5. Tool results are also `type: "user"` entries, so without the check the "last prompt" would be the last tool output, not what you typed. `--bare` never reads OAuth/keychain credentials, and you use a subscription login.
6. Two processes append at once and their text can interleave or overwrite; `flock` makes the second wait. Cost: one Sonnet call per turn (up to 40,000 characters of input) against your subscription usage; stop it with the `disabled` file.
7. Hooks are arbitrary shell commands run with your permissions, and `claude -p` runs project hooks without a trust dialog.

</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Doing the exercises on the real logger | About 40 min |
| B. Another AI tutor | A second explanation of events, exit codes, recursion | About 30 min |
| C. Read primary docs | The exact event/type tables and JSON formats | About 1 hr |
| D. Course | Seeing hooks and headless mode used in a workflow | About 1 hr, then do the exercises anyway |

**A. Prompt for a main session:**
> Walk me through `learning/notes/2026-10-02-hooks-and-headless-claude.md`. Do exercises 1-6 one at a time (run, show output, ask me to explain before moving on), then quiz me on the self-check questions. Don't skip exercise 6; ask me to predict before you explain.

**B. Tool:** NotebookLM with the C links as sources (or ChatGPT/Gemini). Prompt:
> Using only these sources, explain Claude Code hooks (events, hook types and which events support prompt/agent hooks, stdin JSON, exit codes, async) and headless `claude -p` (`--tools`, `--settings`, `--bare` and why it needs an API key). Then explain how a Stop hook that launches `claude -p` can recurse and how to prevent it, and quiz me with 5 questions. Sources: https://code.claude.com/docs/en/hooks-guide, https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/headless, https://code.claude.com/docs/en/cli-reference, https://code.claude.com/docs/en/permissions

**C. Primary docs** (opened 2026-10-02):
- <https://code.claude.com/docs/en/hooks-guide>: start here; first hook, exit codes, matchers, prompt and agent hooks, `/hooks`.
- <https://code.claude.com/docs/en/hooks>: reference; event table, the "which events support which hook types" lists, stdin fields, `Stop` fields (`stop_hook_active`), async, trust.
- <https://code.claude.com/docs/en/headless>: `claude -p`, piping, `--output-format`, and the `--bare` section with its auth rule.
- <https://code.claude.com/docs/en/cli-reference>: one-line meanings of `--tools`, `--settings`, `--setting-sources`, `--no-session-persistence`, `--bare`.
- <https://code.claude.com/docs/en/permissions>: "What runs before you trust a folder" (hooks under `-p`).
- Python's `fcntl` docs for `flock` (not opened for this note; read `man flock` locally).

**D. Course** (confirmed 2026-10-02):
- "Claude Code in Action", Anthropic Academy (free, Skilljar). I opened the page: its lessons include "Hooks" and "Routines and Headless". Matches this note best: <https://anthropic.skilljar.com/claude-code-in-action>
- Not verified: I found no YouTube video whose title, creator and URL I could confirm. A search surfaced a Real Python tutorial on Claude Code hooks (<https://realpython.com/claude-code-hooks/>), but the page returned 403 to my fetch, so I only know it exists from the search listing. One video post ("Making Claude Code more reliable", Julian Harris, Substack) is about hooks but gave no video link and is from the feature's launch. For video, search YouTube for "Claude Code hooks" and prefer recent uploads, since the event list has grown.
