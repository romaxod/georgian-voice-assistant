# georgian-voice-assistant

Roman is building this side project to learn LangGraph, MCP, STT/TTS and LLM evaluation. Read `PROJECT_CONTEXT.md` (why, plan, learning rules, decision log) and `SETUP.md` (accounts, keys, environments) before substantial work. The scope guardrails in PROJECT_CONTEXT.md apply to every session.

## Tutor handoff (main sessions)

Roman wants to understand everything done in this repo, including the tooling around it. The `tutor` agent writes short learning notes in `learning/notes/`, each describing what to learn, how, and from which sources. Notes are listed in `learning/INDEX.md`.

**After any turn that introduced something new to him,** ask him with the **AskUserQuestion** tool (a popup, `multiSelect: true`) which items to hand to the tutor. "New" includes a library, API, concept, command, file or config format, git/gh operation, or Claude Code feature.

- First check `learning/INDEX.md` and the relevant notes. **Leave out anything already explained.**
- If something is **partly** explained, offer it as an addition to that note, e.g. "Add to *subagents* note: resuming a finished subagent".
- Give each option a one-line description of what the note would cover. Ask at most 4 options per question; group related items together.
- If nothing new came up, don't ask.

**When he picks items, hand them off immediately and automatically.** He shouldn't have to do anything else.

1. **Spawn the tutor in the background:** the `tutor` agent type if it's listed, otherwise a general-purpose agent with `model: sonnet` told to read and follow `.claude/agents/tutor.md`. Keep doing your own work while it runs.
2. **Put everything in the first prompt.** Use a numbered list of items, and give each one the facts it needs: what was done, the exact commands, files and output, and the sources you verified. Say for each item whether it's a new note or an addition to an existing note and section. A message sent to a running subagent may arrive after it has finished and be missed, so **don't send corrections mid-run**.
3. **One tutor at a time.** If a tutor is still running when new items come up, wait for it to finish, then resume it with SendMessage and the new items. Resuming keeps its context. This also stops two tutors from editing the same note or `INDEX.md` at once.
4. **Check its work.** The tutor returns a checklist with each numbered item and where it was covered. Read the note. If anything is missing, wrong, or lacks sources for each learning option, resume the same tutor with the exact gaps and check again.
5. **Both finish.** Don't end the task or say "done" while a tutor is still running. Wait for its completion notification, check it as in step 4, then relay the explanation to Roman (he can't see subagent output directly) and link the note.

If you are the tutor, ignore this section.

## Other rules

- Never ask for or accept API keys in chat. They go only in `.env` (gitignored).
- `gh` on this machine has more than one account; `private/CONTEXT.md` says which one this repo uses. Confirm it's active (`gh auth status`) before any push. This repo's git identity is set locally, never globally.
- No real company's code, data, prompts or branding; the service and its data are fictional. Personal details stay in `private/`.
- Record real decisions in the decision log in PROJECT_CONTEXT.md.
