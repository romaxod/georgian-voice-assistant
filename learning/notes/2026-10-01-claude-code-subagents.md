# Claude Code sessions, subagents and the tutor setup

Date: 2026-10-01. Facts checked against code.claude.com docs on this date. This is the first tutor handoff, so it doubles as a worked example of the system it describes.

## 1. What you're learning, and why it matters

**Problem 1: one conversation gets crowded.** Everything the model has seen (chat, files it read, search results) lives in its **context window**, a limited amount of text. Big searches and doc lookups would fill the main session's window and cost money on the expensive model.

- A **session** is one running `claude` process with its own context window.
- A **subagent** is a second Claude instance that the main session launches with its **Agent tool**. It has its own context window, works alone with its own tools, and sends **one final report to the main session**, not to you. The main session relays what matters.
- It can run in the **background** (the main session keeps talking to you), in parallel, and on a cheaper/faster model.

**Problem 2: you want a reusable explainer role.** A subagent can't chat with you; it only reports to the main session. So the role is stored in a definition file:

- **Custom agent file:** `.claude/agents/<name>.md` (this project) or `~/.claude/agents/` (all projects). YAML frontmatter between `---` lines: required `name` and `description` (tells the main agent when to delegate); optional `tools` (allow-list), `model`, `permissionMode`, `skills`, `memory`, `maxTurns`, `mcpServers`, `hooks`, `background`, `effort`. The text below the frontmatter is the agent's **system prompt**.
- A main session spawns the tutor, which works alone: it can't ask you anything.

**The tutor is non-interactive and an explainer only.** It doesn't build project code or chat. It writes a short note in `learning/notes/` (what to learn, how, sources), updates `learning/INDEX.md` (one line per note, with topics covered) and returns the note text. *(Updated 2026-10-01: the earlier interactive `claude --agent tutor` mode, `learning/QUEUE.md` and `learning/LOG.md` were removed; INDEX.md replaces the queue.)*

**Handoff rule (CLAUDE.md)** *(updated 2026-10-02)*. After a turn that introduced something new, the main session checks INDEX.md, skips what's already explained, and asks you in a popup (the **AskUserQuestion** tool, multi-select) which items to hand off; partly covered topics are offered as "add to existing note". After you pick, the handoff runs automatically:
- The tutor runs in the **background** while the main session keeps working.
- Everything goes in the **first prompt** as a numbered item list. No mid-run corrections, because of the late-message race (see resume below).
- **One tutor at a time.** If one is running, the main session waits, then resumes it with the new items (this also avoids two tutors editing INDEX.md at once).
- The tutor returns a **coverage checklist** (each item and where it's covered). The main session reads the note and resumes the tutor for any gaps.
- The main session doesn't say "done" until the tutor has finished and been checked; then it relays the result.

**Resuming a subagent (SendMessage)** *(added 2026-10-01)*. The main session has a **SendMessage** tool that addresses a subagent by name or ID.
- To a **running** subagent: the message is queued and delivered at its **next tool round** (between tool calls). If it finishes first, it never sees it. That race happened here: "restructure to the 7-section format" arrived after the tutor had finished, so the old format was delivered.
- To a **finished** subagent: it is **resumed** from its transcript with everything from its earlier run (files read, text written). A **new** Agent call starts blank, so you'd re-send every fact. This is how the note got restructured.
- **Fork vs resume:** a fork starts with a copy of the *parent's* conversation; resuming continues the *subagent's own* one.
- **Trade-off:** resuming saves tokens and re-explaining; start fresh when the old context is wrong or bloated.
- Docs check (2026-10-01): the sub-agents page covers resuming via `SendMessage` (agent ID or name; no agent teams needed; the full history is kept; built-in Explore and Plan are one-shot and can't be resumed) and forks. It does **not** state the "queued until the next tool round" timing; that comes from the tool definition.

**Model choice:** `model: sonnet` in `tutor.md` resolves to Sonnet 5.5 on Anthropic's API (older Sonnets on Bedrock/Vertex). Elsewhere: `claude --model sonnet`, `/model` in a session, `"model"` in settings.json, or `ANTHROPIC_MODEL`. The main agent can override a subagent's model per call.

## 2. In this repo

What you saw in the terminal:

| Terminal text | Meaning |
|---|---|
| `claude-code-guide(Check ...)` | Main session launched a built-in subagent type that answers Claude Code questions from the docs. Other built-ins: general-purpose, Explore (read-only search), Plan. |
| `Backgrounded agent (↓ to manage · ctrl+o to expand)` / `Waiting for 1 background agent` | It runs in the background; `↓` manages background tasks, `ctrl+o` expands output. |
| `Message from @claude-code-guide` | The subagent's final report arriving at the main session. |
| `Agent ... finished · 1m 38s` | Subagent done. |
| `Write(.claude/agents/tutor.md)` + `Allowed by auto mode classifier` | In auto mode a classifier auto-approves actions it judges safe (a file write in the project) instead of prompting; risky ones still prompt or get blocked. |
| `Baked for 2m 25s` | Elapsed time of that turn. |
| `recap: ...` | Auto summary after a turn; disable in `/config`. |

Then:
- **`.claude/agents/tutor.md`** was written (model sonnet; tools Read, Grep, Glob, Bash, Edit, Write, WebFetch, WebSearch). It's a definition; it runs nothing by itself.
- **`CLAUDE.md`** got the handoff rule (see section 1). It's auto-loaded into every session in this project, so all sessions follow it. It's an instruction, not a guarantee. A **hook** (shell command in settings.json) is the enforced mechanism, but can't judge "was this new to Roman?".
- **`learning/notes/`** and **`learning/INDEX.md`** were created.
- **Why this note was written by a general-purpose agent:** agent definitions are read at session start, so the already-running session didn't know the new `tutor` type. It spawned a general-purpose agent with `model: sonnet` and told it to follow `tutor.md`. After a restart, `tutor` is a real type.
- Optional `/output-style learning` changes how the *main* session talks (leaves `TODO(human)` bits for you, adds "Insight" blocks). It can't set the model.

## 3. How the pieces fit together

The two sessions can't see each other's chats; the repo files are their shared memory (`PROJECT_CONTEXT.md`, `SETUP.md`, `CLAUDE.md`, `learning/`, git history).

```
 FLOW A: handoff (produced this note)

  Roman <---chat---> MAIN SESSION (Opus 5.5, builds the project)
                        |   ^
        Agent tool:     |   | one final report
        prompt + facts  v   | (Roman never sees it directly)
                      SUBAGENT (Sonnet 5.5, own context)
                        +--> writes learning/notes/2026-10-01-....md
                        +--> updates learning/INDEX.md
  MAIN SESSION relays the explanation to Roman

  Files (INDEX.md, notes/, CLAUDE.md) are what later sessions share.

 RESUME *(added 2026-10-01)*

  MAIN --Agent--> SUBAGENT (finishes, delivers old-format note)
  MAIN --SendMessage(to: name/ID)--> same SUBAGENT resumes with its
       full earlier context and restructures the note
```

Misconceptions to drop: a subagent is not a smaller chat window you can talk to; it doesn't know the conversation unless its prompt or files tell it (or it's forked); `tutor.md` isn't a running program; Sonnet is used for cost and speed, and it keeps the main session's context clean.

## 4. Related tools

- **Built-in agent types** (general-purpose, Explore, Plan, claude-code-guide): ready-made workers; custom agents are for a repeatable role with its own prompt.
- **Skills** and **slash commands**: reusable instructions loaded into the *same* context, not a separate worker.
- **Hooks:** deterministic shell commands on events; use when a rule must be enforced.
- **Output styles:** change tone/format of the main session only.
- **`claude --agent <name>`** (or `"agent"` in settings.json): makes the whole session run as that agent. We don't use it; the tutor is spawned by main sessions only.
- **Forks** (`subagent_type: "fork"`): a subagent that inherits the full conversation instead of starting blank; always runs on the parent's model. Different from resuming (section 1).

## 5. Hands-on exercises (each has a check you can observe)

1. `cat .claude/agents/tutor.md`. Check: identify the frontmatter (between the `---` lines) vs the system prompt (everything after); name the line that sets the model and the one that tells the main agent when to delegate.
2. Open `learning/INDEX.md` and `CLAUDE.md`. Check: you can say how a main session decides which topics to offer you and what "add to existing note" means.
3. Ask a main session "which topics does the INDEX say are already explained?". Check: it lists this note's topics.
4. Quit and restart the main session, then run `/agents`. Check: `tutor` is now listed as a project agent. Explain why it wasn't before the restart.
5. In the main session, ask for a small background task (e.g. "use an Explore agent to find where INDEX.md is mentioned"). Press `↓` while it runs and `ctrl+o` after. Check: you see the status lines and the report relayed.
6. Open `CLAUDE.md` and predict what the main session does after a turn that introduces something new. Then test it.
7. Ask a main session to spawn a background agent, then after it finishes ask it to send that agent a follow-up. Check: the agent answers using what it learned before, without re-reading the files *(added 2026-10-01)*.

## 6. Self-check: can you answer these without looking?

1. Where does a subagent's final report go, and how does Roman hear it?
2. Why couldn't the main session spawn the `tutor` type right after writing `tutor.md`?
3. How does the tutor decide whether to write a new note or extend one?
4. Why does the handoff rule live in CLAUDE.md, and what would you use if it had to be guaranteed?
5. How do the main and tutor sessions share information without seeing each other's chats?
6. Why is the tutor forbidden from writing project code?
7. A message to a subagent arrives after it finished. What happens, and how does that differ from a new Agent call or a fork? *(added 2026-10-01)*
8. Why doesn't the main session send corrections to a running tutor, and what does it do instead? *(added 2026-10-02)*

<details>
<summary>Answers</summary>

1. To the main session that spawned it; the main session relays what matters.
2. Agent definitions load at session start; the running session predated the file. Restart, or use a general-purpose agent told to read the file.
3. It reads INDEX.md and related notes: not covered means a new note; partly covered means add to the existing note, marked `*(added date)*`; then it updates INDEX.md.
4. CLAUDE.md is auto-loaded into every session in the project. For enforcement, a hook in settings.json (but it can't make judgment calls).
5. Through repo files: INDEX.md, notes, PROJECT_CONTEXT.md, SETUP.md, CLAUDE.md, git history.
6. You learn by building with the main session; the tutor's only job is explaining, so you understand each piece you wrote.
7. It resumes from its transcript with its full earlier context. A new Agent call starts blank (re-send the facts); a fork copies the parent's conversation, not the subagent's.
8. The message may arrive after the tutor finished and be missed. So everything goes in the first prompt; later items are sent by resuming the finished tutor, one tutor at a time.

</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Ask a main session to walk you through** | Learning by doing on this very setup | About 30 min |
| B. Another AI tutor | A different explanation, with the exercises as its script | About 30 min |
| C. Read primary docs | The most accurate source | About 45 min |
| D. Video or course | Seeing the workflow before trying | 30 min to 2 hr, then do the exercises anyway |

**A. Prompt for a main session:**
> Walk me through `learning/notes/2026-10-01-claude-code-subagents.md`. Do exercises 1-7 one at a time (run, show output, ask me to explain), then quiz me on the self-check questions.

**B. Tool:** NotebookLM with the C links as sources (or ChatGPT/Gemini). Prompt:
> Using only these sources, explain Claude Code subagents: own context window, custom agent files, forks vs resuming with SendMessage, and CLAUDE.md. Then quiz me with 5 questions. Sources: https://code.claude.com/docs/en/sub-agents, https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/model-config, https://code.claude.com/docs/en/hooks-guide

**C. Primary docs** (opened 2026-10-01, all 200):
- <https://code.claude.com/docs/en/sub-agents>: start here; defining agents, resuming, forks.
- <https://code.claude.com/docs/en/memory>: how CLAUDE.md is loaded.
- <https://code.claude.com/docs/en/output-styles>: the `learning` style, main session only.
- <https://code.claude.com/docs/en/model-config>: model aliases like `sonnet`.
- <https://code.claude.com/docs/en/permission-modes>: what auto mode approves.
- <https://code.claude.com/docs/en/hooks-guide>: when a rule must be enforced.
- <https://code.claude.com/docs/en/cli-reference>: `--agent`, `--model`.

**D. Courses** (found by search 2026-10-02, all from Anthropic):
- "Introduction to subagents", Anthropic Courses (free, Skilljar account, 4 modules; matches this note best): <https://anthropic.skilljar.com/introduction-to-subagents>
- "Claude Code: A Highly Agentic Coding Assistant", DeepLearning.AI with Anthropic, Elie Schoppik; about 2 h, 10 lessons, covers subagents and CLAUDE.md; free during beta when I opened it: <https://www.deeplearning.ai/courses/claude-code-a-highly-agentic-coding-assistant>
- Not checked: no YouTube video verified.
