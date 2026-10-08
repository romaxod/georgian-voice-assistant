# Making a repo public safely: secrets and privacy in git history

Checked 2026-10-08 against the GitHub docs, the gh manual, and the gitleaks, trufflehog and git-filter-repo READMEs. gh on this machine is 2.45.0.

## 1. What you're learning, and why it matters

**Problem:** you make a private repo public, and a stranger reads every old commit. If an API key was ever committed, even once, even if you deleted it the next day, it is now public.

- **History is part of the repo.** A commit is a permanent snapshot. Deleting a file in a new commit only changes the newest snapshot. `git log -p` still shows the old content. Making the repo public publishes all commits, all branches and all tags.
- **A leaked key is a spent key.** Bots scan new public repos within minutes. If a secret is found, rotate (revoke and reissue) it first. Cleaning history is second.
- **Three kinds of "don't publish":**
  - *Secrets* (API keys, tokens, voice IDs of a clone): must never be public.
  - *Personal information* (private email, names of people or organizations, private plans, internal data): your judgment call; once public it can't be taken back.
  - *Embarrassing but harmless* (failed experiments, rough notes): usually fine, and honest failures build trust.
- **Uncommitted changes are still editable.** If a file with a problem isn't committed yet, edit it and nothing reaches history. Only the commit step is permanent. Fixing something committed but not pushed is also easy (`git commit --amend`, rebase). Fixing something already public is the hard case.

**Making it public (you run this yourself):**

```bash
gh auth status                                   # romaxod must be active
gh repo view romaxod/georgian-voice-assistant --json visibility,isPrivate
gh repo edit romaxod/georgian-voice-assistant --visibility public
```

The gh manual says newer versions require `--accept-visibility-change-consequences` together with `--visibility`. I confirmed the flag is absent from `gh repo edit --help` on 2.45.0, so it isn't needed here; if a newer gh complains, add it. GitHub's own warning lists the consequences: code visible to everyone, anyone can fork, Actions history and logs become visible, stars and watchers are reset.

**Config in the environment (12-factor).** The 12-factor app says config (keys, URLs) belongs in environment variables, not in code. Its test: could the codebase be open-sourced at any moment without leaking credentials? That's why this repo uses `.env` (gitignored) and `os.environ`.

## 2. In this repo

The scan before going public came in three layers. Each is stronger than the last.

1. **The plan's literal check:** `git log -p | grep -i key` gave 1355 lines, all prose ("keyterms", "API key"). Too noisy to read by eye, so a human would stop looking.
2. **Pattern filter on those lines:** `KEY…` followed by `=` or `:` and 20+ token characters, plus `sk-…` and `sk_…`. 0 hits.
   - **Break test:** three planted fake keys (OpenAI-style `sk-proj-…`, ElevenLabs-style `sk_…` in an `xi-api-key` header, an Azure-style 40-char value) were all caught, and the prose line "the key goes in .env" was skipped.
   - **Lesson: a scan that finds nothing must be shown able to find something.** Otherwise "0 hits" may just mean a broken filter.
3. **The strongest check: search for the real values.** A small Python script read each value from `.env` (never printing it) and searched `git log --all -p` plus all tracked and untracked files. Five values (OpenAI key 164 chars, Azure key 84, ElevenLabs key 51, two ElevenLabs voice IDs 20) appeared nowhere. Patterns guess what a key looks like; this checks for the actual secret.
   - **Gotcha:** `.env` had leading spaces on some names, and a first bash loop could have missed a value with a trailing `\r` or space, giving a false "clean". The Python version strips them.

Other checks:
- `git log --format='%an <%ae>'` shows only `236373192+romaxod@users.noreply.github.com`: no personal email is published.
- Files ever committed include no `.env`, `audio/` or `runs/`. Confirm with `git check-ignore -v .env audio runs` (all three are in `.gitignore`).
- **`.env.example`** was created today: variable names and comments, no values. A stranger runs `cp .env.example .env` and fills it in. python-dotenv reads `KEY=   # comment` as an empty string and `KEY=abc  # comment` as `abc` (checked with `dotenv_values`), so inline comments are safe.
- Privacy beyond secrets: planning notes can name people, organizations or private plans. Decide per file whether that is acceptable, and edit it before the commit if not. Here, personal planning was moved to a gitignored `private/` folder. Old commits still contain the earlier versions, so the files' history has to be rewritten (or published as a fresh history) before going public; see section 4 on `git filter-repo`.

## 3. How the pieces fit together

```
.gitignore --> keeps secrets out of commits
.env.example --> tells strangers what to set
scan (patterns, then real values, then a proper tool) --> proves history is clean
if not clean: rotate key --> (optional) rewrite history --> force-push
```

**If a secret IS found:**
1. Revoke or rotate it at the provider. Treat it as leaked.
2. Optionally rewrite history with `git filter-repo` (or BFG) on a *fresh clone*, then force-push. GitHub's guide notes that PR diffs and cached views can still hold the data (contact GitHub Support to purge them), forks keep the commit, and every collaborator must re-clone.
3. Add prevention: push protection, a pre-commit hook.

## 4. Related tools

- **gitleaks** (open source): regex rules plus entropy; `gitleaks git` scans history, `gitleaks dir` scans files.
- **trufflehog**: can *verify* a finding by calling the provider's API to see if the key still works (`--results=verified`). Fewer false alarms. It clones local repos to a temp dir before scanning.
- **GitHub secret scanning and push protection:** free on public repositories by default. Push protection blocks a `git push` that contains a recognized secret.
- **git filter-repo / BFG:** history rewriting. filter-repo insists on a fresh clone so a mistake is just a deleted folder.
- **pre-commit hooks** (gitleaks has one) stop the commit before it exists.

## 5. Hands-on exercises

1. Run `git log --format='%an <%ae>' | sort -u` in the repo. Check: only the noreply address.
2. Install gitleaks (release binary from its GitHub page, `brew install gitleaks`, or Docker `zricethezav/gitleaks`), then in the repo run `gitleaks git -v` and `gitleaks dir -v .`. Check: findings or "no leaks found". Look at what it flags (likely false positives such as `.env.example` names) and why.
3. Same with trufflehog: `trufflehog git file://. --results=verified,unknown` (install via its install script or Docker). Check: you can explain why verified results matter.
4. In a throwaway folder in the scratchpad (never this repo):
   ```bash
   git init leaky && cd leaky
   echo 'OPENAI_API_KEY=sk-proj-FAKEFAKEFAKEFAKEFAKE1234' > .env && git add . && git commit -m "oops"
   git rm .env && git commit -m "remove"
   git log -p -S'sk-proj-FAKE'          # still found in history
   cd .. && git clone leaky leaky-before
   cd leaky && pip install git-filter-repo   # or your package manager
   git filter-repo --path .env --invert-paths --force
   git log -p -S'sk-proj-FAKE'          # gone here
   cd ../leaky-before && git log -p -S'sk-proj-FAKE'   # still there in the old clone
   ```
   Check: the key survives in the clone made earlier, which is why rotation comes first.
5. Run gitleaks on `leaky-before`. Check: it flags the fake key if its rules match the shape; if not, you've found a detection gap.

## 6. Self-check: can you answer these without looking?

- Why doesn't deleting a file in a new commit remove a leaked key?
- Why did `grep -i key` give 1355 hits, and why is searching for the real values stronger than patterns?
- A scan returns zero findings. What do you do before trusting it?
- A key was committed and pushed. Which step comes first, and why?
- Name two places a leaked commit can survive after you rewrite history and force-push.
- Which kinds of repo content are not secrets but still need a decision before going public?

<details><summary>Answers</summary>

- History keeps the old snapshot; `git log -p` and clones still show it.
- Prose mentions "key" everywhere. Real values test the actual secrets, not a guess at their shape.
- Plant a known fake and check it is found (a break test).
- Rotate/revoke, because the key may already be copied; cleaning history can't un-leak it.
- Forks, old clones, GitHub's cached views and PR references.
- Personal email, names of organizations, private plans, anything private about other people.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Running the scan and the throwaway-repo exercise with questions | About 45 min |
| B. Another AI tutor | A second explanation and a quiz | About 30 min |
| C. Primary docs | Accurate procedures and limits | About 1 hr |
| D. Video | Seeing the tools run | 15-30 min |

**A. Prompt to paste into a main session in this repo:**
> Walk me through learning/notes/2026-10-08-making-a-repo-public-safely.md. Do exercises 1, 4 and 2 one at a time (use the scratchpad for the throwaway repo), show each output, and ask me to explain it. Then quiz me on the self-check questions.

**B. Tool:** NotebookLM with the C links loaded, or any chat AI. Prompt:
> Using only these sources, explain why deleting a file doesn't remove a leaked secret from git history, what to do in what order if one leaks, and what gitleaks and trufflehog add. Then give me a 5-question quiz with answers. Sources: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository, https://github.com/gitleaks/gitleaks, https://github.com/trufflesecurity/trufflehog, https://github.com/newren/git-filter-repo, https://12factor.net/config, https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility

**C. Reading list:**
- GitHub, removing sensitive data: <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository>. Start here: rotate first, filter-repo, force-push limits, forks and cached views.
- GitHub, changing repository visibility: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility>. What changes when private becomes public.
- gh manual, `gh repo edit`: <https://cli.github.com/manual/gh_repo_edit>. The `--visibility` flags.
- gitleaks README: <https://github.com/gitleaks/gitleaks>. Install and the `git` and `dir` commands.
- trufflehog README: <https://github.com/trufflesecurity/trufflehog>. Verified results, local repo scanning.
- git-filter-repo: <https://github.com/newren/git-filter-repo>. `--invert-paths`, `--replace-text`, the fresh-clone rule.
- GitHub, security features: <https://docs.github.com/en/code-security/getting-started/github-security-features>. Secret scanning and push protection are available on public repos by default.
- The Twelve-Factor App, Config: <https://12factor.net/config>. Why config lives in the environment.

**D. Video:** I searched for a gitleaks or filter-repo video and couldn't confirm a specific title and creator, so none is listed. Search YouTube for "gitleaks tutorial" and "remove secret from git history git filter-repo", and prefer videos newer than 2024 (older ones use `git filter-branch` or the old `gitleaks detect` command).

## *(added 2026-10-08)* Keeping personal context out of a public repo *(short)*

Checked 2026-10-08 against the Claude Code memory docs (<https://code.claude.com/docs/en/memory>) and GitHub's removing-sensitive-data page (section 7C).

**1. The pattern used here: a gitignored `private/` folder.**
- Personal planning notes moved to `private/`, and `private/` was added to `.gitignore` (check: `git check-ignore -q private/CONTEXT.md` exits 0).
- The public `CLAUDE.md` says: if `private/CONTEXT.md` exists (gitignored, local only), read it and follow its rules. Local sessions still get the context; GitHub never does. The public file only says the private file exists, not what is in it.
- Alternatives:
  - A separate private repo for the notes. Clean separation, but two repos to keep in sync.
  - Claude Code's own mechanisms, which I verified in the memory docs: `CLAUDE.local.md` at the project root "loads alongside `CLAUDE.md`" for personal per-project preferences, and the docs say to add it to `.gitignore`. `@path/to/file` imports in CLAUDE.md load other files at launch; a file outside the project (e.g. `@~/.claude/my-project-instructions.md`) also works, triggers a one-time approval dialog, and keeps the content out of the repo entirely. Our choice (a plain file plus an instruction) is the same idea, and also lets other tools read it.

**2. Headless agents only know what is in their prompt.**
- The decision logger and code documenter run `claude -p --tools ""`, so they have no file access and cannot read `private/` themselves.
- `.claude/hooks/decision_logger.py` and `code_docs.py` got a `private_rules()` function: if `private/CONTEXT.md` exists, it extracts its "## Privacy section" with a regex and appends it to the prompt (945 characters, verified with a quick import). The public hook code contains only the mechanism, nothing private.
- Lesson: an agent with no tools only knows what the prompt contains. If a rule must bind it, put the rule in the prompt.

**3. Current files are not enough: history still has the old wording.**
- Every old commit keeps the earlier text, and `git log -p` shows it, so history must be rewritten before the repo goes public. This was NOT done this session: rewriting history needs Roman's explicit go-ahead, and he runs every git command himself.
- **(a) `git filter-repo` in a fresh clone,** keeping the per-step commits. `--replace-text` rewrites literal phrases in every file version; `--file-info-callback` lets a Python snippet rewrite or swap whole file versions per path. Afterwards verify with `git log --all -p | grep -i <phrase>` and `git log --all --format=%B | grep -i <phrase>` (commit messages need checking too; `--replace-message` covers them). Prove the check can find something first (planted-phrase break test, as in section 2).
- **(b) Fresh history:** one orphan commit (`git checkout --orphan clean`, commit today's tree). Simplest and certain, but loses the step-by-step history.
- **Where to push.** GitHub's page says that after a force-push the data can remain in cached views and pull request references, that commits in forks stay accessible, and that you must contact GitHub Support to remove cached views. Force-pushing to the existing repo therefore may leave old commits reachable by SHA. Safer: create a new repo with the cleaned history and keep the old one private (or delete it).
- Cheapest of all: never publish what you'd have to scrub. Do the scan and the rewrite while the repo is still private.
