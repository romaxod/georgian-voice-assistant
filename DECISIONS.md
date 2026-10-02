# Decisions

Every decision in this project, from provider choices down to small code details: what was chosen, why, what else was considered, and how to explain it.

**How it's written:** a Stop hook runs the `decision-logger` agent after every main-session turn and appends new entries here automatically (`.claude/hooks/log-decisions.sh`). Entries are append-only and newest last. If an entry is wrong, fix it by hand or add a `reversal` entry. To pause logging, run `touch .claude/decision-logger/disabled`.

Tags: `provider` · `architecture` · `tooling` · `code` · `process` · `scope` · `reversal`

---

### 2026-10-01 · Build a staged voice pipeline instead of a realtime speech-to-speech model `[architecture]`
- **Decision:** STT → LLM workflow (LangGraph) → MCP tool → TTS, as separate stages.
- **Why:** each stage can be inspected, timed and tested on its own, which is what systematic evaluation needs.
- **Alternatives:** an end-to-end realtime speech-to-speech API. Harder to debug and evaluate stage by stage.
- **How:** PROJECT_CONTEXT.md "What this is"; BUILD_PLAN phases 1–2.
- **How to explain it:** "I kept the stages separate so I could measure where errors and latency come from."
- **Decided by:** together

### 2026-10-01 · Fictional Georgian-language customer service as the domain `[scope]`
- **Decision:** the assistant serves a fictional service, in Georgian.
- **Why:** a Georgian customer assistant is a realistic, testable use case, and a fictional service avoids any real company's branding or data.
- **Alternatives:** English; a real company. The first is less relevant, the second risks impersonation and data issues.
- **How:** PROJECT_CONTEXT.md scope guardrails; the concrete service is chosen in BUILD_PLAN 1.3.
- **How to explain it:** "I picked a realistic use case but kept everything fictional and safe to publish."
- **Decided by:** together

### 2026-10-01 · Separate repo, private on GitHub until it's ready `[tooling]`
- **Decision:** a standalone repo `romaxod/georgian-voice-assistant`, private for now, made public before submitting.
- **Why:** a clean, showable project; nothing half-finished is public.
- **Alternatives:** working inside the general `ABSTR ASSN` folder.
- **How:** `git init`, `gh repo create ... --private --source=. --push`.
- **How to explain it:** "The repo history shows how the project grew step by step."
- **Decided by:** together

### 2026-10-02 · Repo-local git identity with the GitHub noreply email `[tooling]`
- **Decision:** set `user.name`/`user.email` locally (`236373192+romaxod@users.noreply.github.com`), not globally.
- **Why:** this laptop also commits work for another account, so a global setting would mix the two identities. The noreply address also keeps the real email out of a public history.
- **Alternatives:** global config; the real email.
- **How:** `git config user.email ...` plus `git commit --amend --reset-author` before the first push.
- **How to explain it:** "I separated work and personal identities on one machine."
- **Decided by:** together

### 2026-10-01 · Python 3.14 with a project venv `[tooling]`
- **Decision:** use the already-installed Python 3.14 via pyenv, with a `.venv` per project.
- **Why:** every planned package ships a pure-Python wheel requiring Python 3.10+ (checked on PyPI 2026-10-01).
- **Alternatives:** installing 3.12 via pyenv. Kept as an optional learning exercise only.
- **How:** SETUP.md §3.
- **How to explain it:** "I checked compatibility on PyPI before deciding instead of assuming."
- **Decided by:** Claude, confirmed by Roman

### 2026-10-02 · Paid LLM API ($5–10) instead of the Gemini free tier, OpenAI recommended `[reversal]`
- **Decision:** buy $5–10 of API credit; OpenAI recommended, Anthropic equally viable. This replaces the 2026-10-01 plan to start on the Gemini free tier.
- **Why:** Roman preferred a paid provider and has the budget. The estimated total cost is ~$1.50–2 on a cheap model. OpenAI also sells STT/TTS, a possible fallback if Azure's Georgian is weak.
- **Alternatives:** Gemini free tier (low rate limits, prompts may be used for training); Anthropic.
- **How:** SETUP.md §1; key in `.env` as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- **How to explain it:** "I estimated the cost before choosing: about 500 calls × 2.3K tokens comes to roughly $2."
- **Decided by:** Roman (provider), Claude (recommendation)

### 2026-10-01 · Azure Speech for STT and TTS `[provider]`
- **Decision:** Azure Speech, free F0 tier, via Azure for Students.
- **Why:** documented Georgian (`ka-GE`) STT plus two Georgian neural voices; a free tier and $100 student credit with no card; one key for both directions; Speech Studio for no-code testing.
- **Alternatives:** Google (Georgian STT, no Georgian TTS found), AWS (Georgian STT, no Polly voice), OpenAI (Georgian TTS not listed), ElevenLabs (planned as a comparison).
- **How:** SETUP.md §2; `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` in `.env`. Full comparison in learning/notes/2026-10-02-azure-basics.md §2.
- **How to explain it:** "Azure was the lowest-friction provider with documented Georgian in both directions. Then I measured where it's weak."
- **Decided by:** Claude, confirmed by Roman

### 2026-10-02 · Microsoft's first-party "Speech" resource, not a marketplace product `[provider]`
- **Decision:** create the "Speech" card by Microsoft (Azure Service, **Create**).
- **Why:** one resource covers STT and TTS on the F0 tier. The third-party cards ("Text-to-Speech API", BitFractal…) are separate paid subscriptions.
- **Alternatives:** separate third-party STT/TTS marketplace products.
- **How:** Portal → Create a resource → Speech.
- **How to explain it:** "I picked the first-party service so billing and SDK support stay in one place."
- **Decided by:** Claude, confirmed by Roman

### 2026-10-02 · Azure region `italynorth` `[provider]`
- **Decision:** deploy the Speech resource in Italy North.
- **Why:** the Azure for Students policy (`RequestDisallowedByAzure`) only allows `denmarkeast`, `switzerlandnorth`, `polandcentral`, `austriaeast` and `italynorth`. Of those, only Italy North and Switzerland North support Speech, and Italy North also lists fast transcription.
- **Alternatives:** Germany West Central and West Europe (blocked by policy); Switzerland North.
- **How:** read the policy with `az policy assignment list ...` in Cloud Shell; `AZURE_SPEECH_REGION=italynorth`.
- **How to explain it:** "I hit a policy error, read the allowed regions from the policy, and cross-checked them against the service's region table."
- **Decided by:** together

### 2026-10-02 · Measure code-switching (Georgian with English words) instead of assuming `[process]`
- **Decision:** add code-switched test cases to BUILD_PLAN 1.5, 2.5, 2.6a, 3.1 and 3.4.
- **Why:** Azure language ID can't switch mid-sentence, and phrase lists aren't shown for `ka-GE`. Georgian developers mix in English constantly.
- **Alternatives:** ignore it; switch STT provider up front without evidence.
- **How:** an eval category plus a "speech-text" rewrite step before TTS if needed.
- **How to explain it:** "Real Georgian users code-switch, so I made it its own eval category."
- **Decided by:** Roman raised it, Claude designed it

### 2026-10-02 · Optional voice clone, staged: Azure → ElevenLabs ready-made → Roman's clone `[scope]`
- **Decision:** BUILD_PLAN 2.6a/2.6b, with TTS behind a swappable interface and Azure as fallback.
- **Why:** changing one thing per stage shows whether a quality change comes from the provider or the recording. Azure Personal Voice is gated to approved business customers.
- **Alternatives:** clone directly; Azure Personal Voice; ElevenLabs Professional clone ($22+, 30+ min of audio).
- **How:** SETUP.md §4; `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`.
- **How to explain it:** "I compared three voices blind on the same 10 sentences."
- **Decided by:** Roman (idea), Claude (staging)

### 2026-10-02 · BUILD_PLAN.md and a "next" workflow instead of Wayfinder `[process]`
- **Decision:** a numbered step list in `BUILD_PLAN.md`; every session reads it and resumes at the first unchecked step when Roman types "next".
- **Why:** the plan and big decisions already existed and the build fits in a weekend. Wayfinder plans multi-session efforts as GitHub-issue decision maps, which would cost a day.
- **Alternatives:** `/wayfinder`; ad-hoc prompting.
- **How:** BUILD_PLAN.md plus the CLAUDE.md "next / continue" section.
- **How to explain it:** "I made the plan the shared memory between AI sessions, so any session can pick up where the last stopped."
- **Decided by:** Claude, confirmed by Roman

### 2026-10-02 · Tutor agent that writes notes only, handed off by popup `[tooling]`
- **Decision:** a Sonnet `tutor` subagent writes SETUP-§3-style notes in `learning/notes/`. Main sessions ask via a popup what to hand off; the tutor runs in the background, one at a time, returns a coverage checklist, and the main session verifies it.
- **Why:** Roman wants to understand everything without slowing the build. Subagents can't chat with the user, so notes fit. Late mid-run messages can be missed, so everything goes in the first prompt.
- **Alternatives:** an interactive tutor session (`claude --agent tutor`), dropped by Roman; the Learning output style.
- **How:** `.claude/agents/tutor.md`, CLAUDE.md "Tutor handoff", `learning/INDEX.md`.
- **How to explain it:** "I split building and learning across agents and made their handoff lossless."
- **Decided by:** Roman (requirements), Claude (design)

### 2026-10-02 · Automatic decision log via a Stop hook and a headless Sonnet logger `[tooling]`
- **Decision:** an async Stop hook runs `.claude/hooks/log-decisions.sh` after every main-session turn. It extracts that turn from the transcript and asks headless `claude -p --model sonnet` (no tools, hooks disabled) to return decision entries, which the script appends here under a file lock.
- **Why:** Roman wants every decision recorded, so he can explain it later, without remembering to ask. A hook runs every time, while a CLAUDE.md instruction can be forgotten.
- **Alternatives:** a CLAUDE.md rule making the main session spawn a logger each turn (less reliable, uses main context); `--bare` (skips subscription login); giving the logger tools (unnecessary risk).
- **How:** `.claude/settings.json` (Stop, `async: true`), `.claude/hooks/decision_logger.py`, `.claude/agents/decision-logger.md`. Recursion guard: `DECISION_LOGGER_CHILD=1` plus `disableAllHooks`. Off switch: `.claude/decision-logger/disabled`.
- **How to explain it:** "I used deterministic hooks for things that must always happen, and LLM judgment only for extraction."
- **Decided by:** Roman (requirement), Claude (design)

### 2026-10-02 · One decision log: DECISIONS.md replaces the PROJECT_CONTEXT.md table `[reversal]`
- **Decision:** `DECISIONS.md` is now the only decision log. The decision-log table in `PROJECT_CONTEXT.md` was replaced with a pointer to it.
- **Why:** the assistant said it wanted "one decision log instead of two". Other reasons were not stated.
- **Alternatives:** keep the manual table in `PROJECT_CONTEXT.md` alongside the automatic log. Why this was rejected was not stated beyond avoiding two logs.
- **How:** `PROJECT_CONTEXT.md` "Decision log" section rewritten as a pointer, and step 5 of its workflow now points to `DECISIONS.md`. `CLAUDE.md` and `BUILD_PLAN.md` were repointed. `CLAUDE.md` now tells Claude to state the reason for a choice in its reply so the logger can capture it, and tells the headless logger to ignore that file.
- **How to explain it:** "I replaced the hand-written decision table with an automatic log so decisions get recorded as they happen and there's one source of truth."
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Recursion guard via the `DECISION_LOGGER_CHILD` env var `[code]`
- **Decision:** `.claude/hooks/log-decisions.sh` exits immediately if `DECISION_LOGGER_CHILD=1`. This stops the headless logger session from triggering another logger run through its own Stop hook.
- **Why:** the headless logger is itself a Claude session, so without a guard its Stop hook would fire another logger. The subagent's docs summary had no documented `stop_hook_active` mechanism and only gave a vague, unofficial "in-hook" env var workaround.
- **Alternatives:** `--bare` was rejected because it skips the subscription login. `--settings '{"disableAllHooks": true}'` is used **as well** (belt and braces): the env var stops the script, and the setting stops the child firing hooks at all.
- **How:** first line of `.claude/hooks/log-decisions.sh`. `decision_logger.py` launches the child with `env={..., "DECISION_LOGGER_CHILD": "1"}` and `--settings '{"disableAllHooks": true}'` from a temp directory. *(corrected by hand 2026-10-02)*
- **How to explain it:** "A hook that launches Claude can trigger itself, so I added an explicit env-var guard to prevent infinite recursion."
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Giorgi as the default Azure voice `[provider]`
- **Decision:** use `ka-GE-GiorgiNeural` as the default TTS voice.
- **Why:** in Roman's Speech Studio test he rated Giorgi 3.5–4/5 and Eka 3/5. Neither mispronounced anything, but Giorgi sounded more natural.
- **Alternatives:** `ka-GE-EkaNeural`; an ElevenLabs voice (planned comparison in BUILD_PLAN 2.6a).
- **How:** SETUP.md §2 test results; this becomes the voice name in the TTS config.
- **How to explain it:** "I picked the voice from a listening test, and planned a blind comparison against alternatives."
- **Decided by:** Roman (ratings), Claude (default)

### 2026-10-02 · Real-time recognition, and send eval audio one clip at a time `[process]`
- **Decision:** use real-time STT, not fast or batch transcription, and run voice evals sequentially.
- **Why:** on the Azure F0 tier, fast/batch transcription show "Not applicable", and real-time STT allows only 1 concurrent request (verified in Azure quota docs 2026-10-02).
- **Alternatives:** fast transcription (Georgian supports it, but not on F0); a paid S0 tier.
- **How:** SETUP.md §2 F0 limits; BUILD_PLAN 3.4 "one at a time".
- **How to explain it:** "I designed the eval runner around the free tier's concurrency limit instead of hitting 429s."
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Two depths of tutor notes: full and short `[process]`
- **Decision:** the tutor writes **full** notes (7 sections, ways to learn including videos and courses) for anything important to Roman's growth, even outside this project's scope, and **short** explanation-only notes for small or peripheral things. The handoff popup labels each option, and Roman can override it.
- **Why:** Roman said he won't watch videos for small things, but wants the full treatment for important topics.
- **Alternatives:** always full; never suggest videos.
- **How:** `.claude/agents/tutor.md` "Two depths"; CLAUDE.md handoff rule.
- **How to explain it:** n/a (personal learning workflow)
- **Decided by:** Roman

### 2026-10-02 · Async hook fixes: drop the useless timeout, log skipped runs `[code]`
- **Decision:** removed `"timeout": 300` from the Stop hook in `.claude/settings.json`, and `decision_logger.py` now writes `skip: disabled` to `runs.log` when the off switch is on.
- **Why:** the tutor found in the hooks docs that async hooks ignore `timeout` (the real limit is the 280 s `subprocess.run` timeout), and that a disabled run previously left no trace, so you couldn't tell it was off.
- **Alternatives:** keep the timeout as documentation (misleading); keep silent skips.
- **How:** `.claude/settings.json`; `log_run("skip: disabled")` in `main()`. Tested: `runs.log` showed `skip: disabled`.
- **How to explain it:** "A reviewer, here an AI tutor reading the docs, caught a config that looked protective but did nothing."
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Planned agent design: routing + bounded tool loop + human handoff `[architecture]`
- **Decision:** the LangGraph graph will route each turn (answer, look up, clarify, hand off), run a tool loop with a step limit, and end in a handoff node when the assistant is unsure or the user asks for an action it can't take.
- **Why:** this is the simplest pattern that covers the plan (BUILD_PLAN 2.1–2.2), Anthropic's "Building effective agents" recommends starting with simple workflows, and a customer-service assistant should keep autonomy low (OWASP excessive agency). Multi-agent adds cost and failure modes with no benefit at this size.
- **Alternatives:** a fully autonomous agent loop; multi-agent supervisor; plan-and-execute.
- **How:** learning/notes/2026-10-02-agentic-architectures.md §2 (diagram); built in BUILD_PLAN 2.1–2.2.
- **How to explain it:** "I chose the least autonomous design that solves the task, and added guardrails where a customer-service assistant needs them."
- **Decided by:** Claude (unconfirmed). Confirm or change it at step 2.1.

### 2026-10-02 · Keep the repo on `/mnt/c` for now, move to `~` only if problems repeat `[tooling]`
- **Decision:** The repo stays at `/mnt/c/prog/ABSTR ASSN/georgian-voice-assistant`, on the Windows drive. Moving it into the Linux filesystem (`~`) is optional and only worth doing if the same problems come back.
- **Why:** The `python -m venv .venv` failure was most likely a stale working directory. Windows-side deletion or renaming is the probable cause, but the tutor note says that is unverified. The `.venv` was created fine after `cd` back into the folder. Microsoft's guidance is to keep projects for Linux tools in `~`, but the note treats a move as optional. No other reason was stated.
- **Alternatives:** Move the repo to `~` (Microsoft's recommended setup for Linux tools). It was not chosen now because the failure had a cheaper fix, `cd` again. The `/mnt/c` quirks are documented in `learning/notes/2026-10-02-wsl-filesystems.md`, which includes a short how-to for moving.
- **How:** No change was made. The venv sits at `/mnt/c/prog/ABSTR ASSN/georgian-voice-assistant/.venv` (Python 3.14.0 from pyenv). Roman should quote the path in commands because it contains a space.
- **How to explain it:** "I kept the project on the Windows-mounted drive because the failure was a stale shell directory and not a filesystem problem, and I know the exit route, which is moving it into WSL's native filesystem, if the quirks come back."
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Bigger chunks per step: whole step in one message, one break test `[process]`
- **Decision:** Each build step is delivered as one numbered message with all commands and code, short whys, and one request for all output at the end. This replaces 3-4 commands per turn with a wait after each.
- **Why:** Roman said "we need to get our speeds up a little" after several small-batch turns and a tutor detour with no code written yet. The time budget is a 3-4 day weekend build.
- **Alternatives:** Keep drip-feeding with guesses before each chunk. Not kept because it was too slow.
- **How:** Memory file `pace-bigger-chunks.md`, indexed in `MEMORY.md`. The step 0.2 reply follows it (why, steps, break test, commit).
- **How to explain it:** "I noticed the step-by-step pacing was too slow for a weekend build, so I changed the workflow to batch each step while still typing the code and breaking it myself."
- **Decided by:** together

### 2026-10-02 · `requirements.txt` generated with `pip freeze` `[tooling]`
- **Decision:** Pin dependencies by running `python -m pip freeze > requirements.txt` after installing `openai` and `python-dotenv`, instead of hand-writing the list.
- **Why:** It records the exact installed versions, including transitive dependencies, so anyone can recreate the identical environment with `pip install -r requirements.txt`.
- **Alternatives:** Hand-written requirements list. Not chosen because it doesn't capture exact versions or dependencies.
- **How:** `requirements.txt` in the repo root, committed with `check_env.py`.
- **How to explain it:** "I froze the environment so the install is reproducible down to the transitive dependencies."
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Use `python -m pip` inside the activated venv `[tooling]`
- **Decision:** Install packages with `python -m pip install ...` after `source .venv/bin/activate`, and check `which python` before and after activation.
- **Why:** `python -m pip` runs pip as part of that exact Python, so packages can't land in the wrong interpreter. A plain `pip` could belong to a different Python.
- **Alternatives:** Plain `pip install`. Not used because of the wrong-interpreter risk.
- **How:** The commands in step 0.2. The `which python` check should show `.venv/bin/python`.
- **How to explain it:** "I call pip through the interpreter so I know which environment I'm installing into."
- **Decided by:** together

### 2026-10-02 · `check_env.py` prints key lengths, never values `[code]`
- **Decision:** `check_env.py` loads `.env` with `load_dotenv()` and checks `OPENAI_API_KEY`, `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`. It prints "key loaded (N chars)" or "MISSING", never the value itself.
- **Why:** The output can be pasted into the chat safely without leaking secrets, and it still confirms each variable is set.
- **Alternatives:** none discussed
- **How:** `check_env.py` in the repo root, using `python-dotenv` and `os.getenv`. A deliberate break test runs it after `deactivate`.
- **How to explain it:** "I wrote the env check so it never prints secrets, which makes it safe to share logs while debugging."
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · OpenAI Responses API with `gpt-5.4-mini` for the first LLM call `[provider]`
- **Decision:** Use OpenAI's Responses API (`client.responses.create`) with model `gpt-5.4-mini` ($0.75 in / $4.50 out per 1M tokens) in `first_call.py`.
- **Why:** Responses is OpenAI's recommended API for new projects, and the installed SDK (openai 3.23.0) was checked to have it. The model's price was verified in the pricing note. Why this model over others: not stated.
- **Alternatives:** Chat Completions API (older, so not chosen). No other models discussed.
- **How:** `first_call.py` with `MODEL = "gpt-5.4-mini"`, `PRICE_IN = 0.75`, `PRICE_OUT = 4.50`, `instructions=` as system prompt, `response.output_text` for the answer.
- **How to explain it:** I used OpenAI's recommended Responses API, confirmed the SDK supported it, and priced the cheap `gpt-5.4-mini` model from the official pricing page.
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Catch specific OpenAI SDK errors and exit with a one-line message `[code]`
- **Decision:** Wrap the call in `try/except` for `AuthenticationError`, `RateLimitError` and `APIConnectionError`, each calling `sys.exit("Error: ...")` with a readable message. Other errors, such as a bad model name, are left as raw tracebacks on purpose, as a break-test exercise.
- **Why:** A customer-facing assistant should fail with a clear message, not a raw traceback.
- **Alternatives:** A bare traceback, or a catch-all `except`. The catch-all was not discussed. Roman is asked how to catch the bad-model error too.
- **How:** `first_call.py`, the `except` blocks around `client.responses.create`.
- **How to explain it:** I catch the specific SDK exceptions and turn them into one clear line, so the user never sees a raw stack trace.
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Pricing constants and cost printed per call `[code]`
- **Decision:** Hardcode `PRICE_IN` and `PRICE_OUT` and print token counts and USD cost after each response, computed from `response.usage`.
- **Why:** Not stated beyond showing "the answer, the token count and the cost". It fits the paid-API budget decision.
- **Alternatives:** none discussed.
- **How:** `first_call.py`, the `cost = usage.input_tokens / 1_000_000 * PRICE_IN + ...` line, with a comment noting the prices were checked on 2026-10-02.
- **How to explain it:** I track the cost of every call from the usage object, so spend is visible from the first request.
- **Decided by:** Claude (unconfirmed)

### 2026-10-02 · Tutor notes for dotenv, dependencies, gh accounts and Responses API, with depth chosen per topic `[process]`
- **Decision:** Batch 2 of tutor notes covers environment variables and dotenv (short), dependencies and pinning (short), `gh` with two accounts (short), and the OpenAI Responses API (full). They are written in the background by the tutor agent.
- **Why:** Roman picked these topics from the options offered. Reasons for the depth levels: not stated.
- **Alternatives:** Other offered topics were not selected. The options were not fully visible in the excerpt.
- **How:** `AskUserQuestion`, then `SendMessage` to the tutor agent. Notes go into `learning/notes/` and `learning/INDEX.md`.
- **How to explain it:** I choose which new concepts get written up, and how deeply, so the notes match what I actually need to learn.
- **Decided by:** Roman
