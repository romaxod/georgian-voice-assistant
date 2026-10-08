# georgian-voice-assistant

Roman is building this side project to learn LangGraph, MCP, STT/TTS and LLM evaluation. Read `PROJECT_CONTEXT.md` (why, plan, learning rules) and `SETUP.md` (accounts, keys, environments) before substantial work. The scope guardrails in PROJECT_CONTEXT.md apply to every session.

**This repo is public.** If `private/CONTEXT.md` exists (gitignored, local only), read it too and follow its rules; it holds Roman's personal planning, which must never appear in tracked files, commit messages or the decision log.

## "next" / "continue": how every main session works

`BUILD_PLAN.md` is the source of truth for what to do next. Roman shouldn't have to know what to ask.

**Claude implements; Roman reads.** Claude writes the code, runs it, runs the break test, and finishes the step. Roman learns from the auto-generated code docs (`docs/code/`), the tutor notes (`learning/notes/`) and `DECISIONS.md`, not from typing code or answering quizzes. No quiz questions, no "what do you think this prints?", no drip-feeding a few lines and waiting. Ask only when a decision is genuinely his (e.g. paying for something, a scope change) and can't be defaulted sensibly; otherwise pick, state the reason, and move on.

- **When a session starts, or he says "next" or "continue"** (or gives no specific task): read BUILD_PLAN.md, find the first step that isn't `[x]`, run `git status` / `git log --oneline -5`, then **implement the whole step in that turn**.
- **Implementing a step:** write all the files, install anything needed (update `requirements.txt` with `python -m pip freeze`), then actually run the step's "Done when" check and one break test yourself, and show the real output. If a check needs Roman (his microphone, his ears, a dashboard), do everything else first and give him one short numbered list of what to do.
- **Report back briefly:** what was built (files), what each part does in a few lines, the check output, and where to read more (`docs/code/<file>.md`, the tutor note). State the reason for every choice so the decision logger captures it.
- **Finishing a step:** mark it `[x] YYYY-MM-DD` in BUILD_PLAN.md and give him the git commands to run with a suggested commit message (**he runs every git command himself**; never run `git add`/`commit`/`push`). Then propose the next step.
- **If a step is too big or wrong:** split or edit it in BUILD_PLAN.md and add a line under "Changes to the plan". Don't silently skip steps.
- If he asks for something off-plan, do it, then point him back to the current step.

## Where Roman learns from

| What | Written by | Covers |
|---|---|---|
| `docs/code/<path>.md` | Stop hook → `code-documenter` (automatic, when a code file changes) | Every part of each code file explained, block by block, in this repo's context |
| `DECISIONS.md` | Stop hook → `decision-logger` (automatic, every turn) | Every choice: why, alternatives, how to explain it |
| `learning/notes/` | `tutor` agent (spawned by the main session) | Concepts and tools in depth, with exercises and sources (docs, videos, courses) |

## Tutor handoff (main sessions)

Roman wants to understand everything done in this repo, including the tooling around it. The `tutor` agent writes learning notes in `learning/notes/`, each describing what to learn, how, and from which sources. Notes are listed in `learning/INDEX.md`. **Don't ask him which items to hand off; do it automatically.**

**After any turn that introduced something new,** spawn the tutor with every new item. "New" includes a library, API, concept, command, file or config format, git/gh operation, or Claude Code feature.

- First check `learning/INDEX.md` and the relevant notes. **Leave out anything already explained.** If something is **partly** explained, hand it off as an addition to that note.
- Pick the depth per item: **(full)** for anything important to Roman's growth (even outside this project's scope), with exercises and ways to learn including videos and courses; **(short)** for small or peripheral things, explanation only. Group related items into one note.
- Line-by-line explanation of this repo's code belongs in `docs/code/` (automatic), not in tutor notes. Tutor notes teach the concept behind it.
- If nothing new came up, don't spawn it.

How to hand off:

1. **Spawn the tutor in the background:** the `tutor` agent type if it's listed, otherwise a general-purpose agent with `model: sonnet` told to read and follow `.claude/agents/tutor.md`. Keep doing your own work while it runs.
2. **Put everything in the first prompt.** Use a numbered list of items, and give each one the facts it needs: what was done, the exact commands, files and output, and the sources you verified. Say for each item whether it's a new note or an addition to an existing note and section, and its depth. A message sent to a running subagent may arrive after it has finished and be missed, so **don't send corrections mid-run**.
3. **One tutor at a time.** If a tutor is still running when new items come up, wait for it to finish, then resume it with SendMessage and the new items. Resuming keeps its context. This also stops two tutors from editing the same note or `INDEX.md` at once.
4. **Check its work.** The tutor returns a checklist with each numbered item and where it was covered. Read the note. If anything is missing, wrong, or lacks sources for each learning option, resume the same tutor with the exact gaps and check again.
5. **Both finish.** Don't end the task while a tutor is still running. Wait for its completion notification, check it as in step 4, then tell Roman in 2–3 lines what the note covers and link it (he can't see subagent output directly).

If you are the tutor, ignore this section.

## Other rules

- Never ask for or accept API keys in chat. They go only in `.env` (gitignored).
- `gh` on this machine has more than one account; `private/CONTEXT.md` says which one this repo uses. Confirm it's active (`gh auth status`) before any push. This repo's git identity is set locally, never globally.
- No real company's code, data, prompts or branding; the service and its data are fictional. Personal details stay in `private/`.
- Decisions are logged automatically to `DECISIONS.md` by the Stop hook (`decision-logger` agent). State the reason for a choice explicitly in your reply, so the logger can capture it. If you see a wrong entry, fix it. If you are the headless decision logger or code documenter, ignore this file.
- Code docs in `docs/code/` are regenerated automatically by a second Stop hook (`.claude/hooks/document-code.sh`) whenever a code file's content changes. Don't edit them by hand; fix the code or `.claude/agents/code-documenter.md` instead. To refresh them right away (e.g. before telling Roman to read one): `python3 .claude/hooks/code_docs.py`.
