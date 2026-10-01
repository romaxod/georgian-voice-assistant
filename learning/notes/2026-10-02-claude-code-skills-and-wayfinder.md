# Claude Code skills, plugins and Wayfinder

Date: 2026-10-02. Docs pages and the installed plugin files checked on this date. Plugin: `mattpocock-skills` v1.2.3.

## 1. What you're learning, and why it matters

**Problem: you keep re-typing the same detailed instructions** ("interview me about this plan", "research this from primary sources"), and CLAUDE.md is the wrong place because it loads on every turn.

- A **skill** is a folder with a `SKILL.md`: YAML frontmatter (`name`, `description`) plus markdown instructions. The body loads into the **current session's context** only when the skill is used. That is how it differs from CLAUDE.md (always loaded) and from a subagent (separate context; see the [subagents note](2026-10-01-claude-code-subagents.md), sections 1 and 4).
- **Two ways to invoke:** you type `/skill-name`, or the model calls its **Skill tool** because the `description` matches the task. Only the name and description sit in context until then.
- **Frontmatter switches:** `disable-model-invocation: true` means only you can run it; `user-invocable: false` means only the model can. `context: fork` runs a skill inside a subagent.
- **Where skills live:** `~/.claude/skills/` (all projects), `.claude/skills/` (this repo), or inside a plugin.
- A **plugin** is a directory bundling skills, agents, hooks, MCP servers as one installable unit, usually from a marketplace via `/plugin`. Its manifest is `.claude-plugin/plugin.json`. Plugin skills can be namespaced like `/my-plugin:review`.
- Cost: an enabled plugin's skill names and descriptions are in context on every turn, but a skill's full text loads only when used.

## 2. In this repo

Roman has the **`mattpocock-skills`** plugin (v1.2.3) at `~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/`. I read its README, `docs/engineering/wayfinder.md` and `skills/engineering/wayfinder/SKILL.md`.

**Wayfinder** plans a chunk of work **too big for one session**. The route is foggy, so it charts a **map** instead of building:
- The map is one issue labelled `wayfinder:map` on the issue tracker (GitHub, GitLab or local markdown). It holds the **Destination**, **Decisions so far** (an index), **Not yet specified** ("fog"), and **Out of scope**.
- Work is **decision tickets**: child issues, each a question sized for one agent session. Types: `grilling` (talk it through; the default), `prototype`, `research` (a subagent reads docs), `task` (manual work that unblocks a decision, like signing up for a service).
- Tickets are resolved **one at a time**; the **frontier** is the open tickets nothing blocks. It **plans, doesn't build**. When the map is clear you hand off: `/to-spec`, then `/to-tickets` and `/implement`.
- The author's own docs call it **the heaviest, densest flow**: for greenfield or multi-session work; a well-scoped feature should use `/grill-me` or `/grill-with-docs` instead. "Greenfield" is not required, though; it's session count that decides.
- **Needs setup first:** `/setup-matt-pocock-skills` configures the tracker.

**Correction to the earlier guess.** Wayfinder did not show in this session's skill list not because it is disabled, but because its SKILL.md sets `disable-model-invocation: true`: it is **user-only**. Same for `to-spec`, `to-tickets`, `implement`, `grill-me`, `grill-with-docs`, `setup-matt-pocock-skills`. You type it. (Not tested by running it; I did not run Wayfinder.)

**Why we use `BUILD_PLAN.md` instead:**
- The plan and big decisions already existed in `PROJECT_CONTEXT.md`, so there was no fog to chart.
- The project is weekend-sized: one session can hold the route, so Wayfinder's own docs would point to a grill flow.
- Roman's real need: any session knows the next step without him phrasing it. A checklist file plus the "next / continue" rule in CLAUDE.md does that with no tracker setup.

## 3. How the pieces fit together

```
plugin (installed unit)
  +-- skills/  --> /name or Skill tool --> text loads into THIS session's context
  +-- agents/  --> subagents, run in a SEPARATE context
  +-- hooks, MCP servers ...

big foggy effort:  /wayfinder -> map issue + decision tickets -> /to-spec -> /to-tickets -> /implement
one-session plan:  /grill-me  (or /grill-with-docs)
```

## 4. Related tools

- **`/grill-me`, `/grill-with-docs`, and the `grilling` skill** (the interview behind them): stress-test a plan by being asked one question at a time. Best fit for step-sized decisions here.
- **`/research`:** investigates a question against primary sources, saves a cited markdown file, runs as a background agent (like the tutor).
- **`/prototype`**, **`/tdd`**, **`/diagnosing-bugs`**, **`/code-review`:** useful when we build; `/tdd` fits the eval phase.
- **`/to-spec`, `/to-tickets`, `/implement`:** the hand-off chain after planning; user-only.
- **`/teach`**, **`/handoff`** (productivity group): exist in the plugin; I read only their listing, not their files.
- **Not used:** Wayfinder and tracker setup (reason in section 2).

## 5. Hands-on exercises

1. Run `ls ~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering`. Check: you see `wayfinder`, `to-spec`, `implement`, `research`.
2. `head -5 ~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/wayfinder/SKILL.md`. Check: you find the frontmatter lines `name`, `description` and `disable-model-invocation: true`. Say what the last one does.
3. Do the same for `skills/engineering/research/SKILL.md`. Check: it has no `disable-model-invocation` line. Predict whether the model can call it by itself.
4. In a main session run `/plugin`. Check: you see `mattpocock-skills` among installed plugins.
5. Read `docs/engineering/wayfinder.md`, the table "When to reach for it". Check: place our project in a row and justify.
6. Try `/grill-me` on your own question, e.g. "grill me on step 1.3's fictional service choice". Check: it asks questions one at a time and doesn't write code.

## 6. Self-check: can you answer these without looking?

1. What gets loaded into context when a skill runs, and when?
2. How does a skill differ from a subagent?
3. What does `disable-model-invocation: true` change, and how does it explain Wayfinder missing from the list?
4. What is a plugin, in one sentence?
5. What is a decision ticket, and why does Wayfinder not build anything?
6. Why didn't this project use Wayfinder?

<details>
<summary>Answers</summary>

1. The `SKILL.md` body, into the current session's context, only when you type `/name` or the model calls the Skill tool; before that only name and description.
2. Same context vs a separate one; instructions to follow vs a worker with its own tools and report.
3. Only you can invoke it, so the model's skill list omits it, though it is installed.
4. A directory of skills, agents, hooks and MCP servers installed together.
5. A child issue holding a question whose answer is a decision. Wayfinder's job is a clear route; building comes after, via `/to-spec` and `/implement`.
6. The plan already existed, the project fits one-session decisions, and the need was "know the next step", solved by `BUILD_PLAN.md`.

</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Seeing real SKILL.md files | About 30 min |
| B. Another AI tutor | Wayfinder concepts explained differently | About 30 min |
| C. Primary docs | Accurate skill and plugin rules | About 45 min |
| D. Video or course | Seeing the workflow | Variable |

**A. Prompt for a main session:**
> Walk me through `learning/notes/2026-10-02-claude-code-skills-and-wayfinder.md`. Do exercises 1-6 one at a time, ask me to explain each output, then quiz me on the self-check questions.

**B. Tool:** NotebookLM with the C links. Prompt:
> Using only these sources, explain Claude Code skills vs subagents vs plugins, and when to use Wayfinder vs a grilling session. Quiz me with 5 questions. Sources: https://code.claude.com/docs/en/skills, https://code.claude.com/docs/en/plugins, https://github.com/mattpocock/skills

**C. Primary docs** (opened 2026-10-02):
- <https://code.claude.com/docs/en/skills>: what skills are, invocation switches, locations, skills vs subagents.
- <https://code.claude.com/docs/en/plugins>: what plugins bundle, install scopes, context cost.
- <https://github.com/mattpocock/skills>: the plugin's repo; overview of the skills (the repo README and the `docs/engineering/wayfinder.md` file locally give the details).

**D. Video or course:** none verified. Search "Matt Pocock Claude Code skills" or "Claude Code skills tutorial" on YouTube; I did not search for or confirm a specific video.
