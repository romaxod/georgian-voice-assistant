# `gh` with two GitHub accounts, and git identity vs credentials

*(short note)* Checked 2026-10-02 against cli.github.com manual pages, git-scm.com docs, and read-only `git config` / `gh auth status` on this machine (tokens hidden).

## 1. What and why

**Problem:** this machine has a work account and a personal one (`romaxod`). A push must go to the personal repo with the personal account, and never mix the two.

There are **two separate things**, and people confuse them:

| | Who you *claim* to be | Who GitHub *lets in* |
|---|---|---|
| What | **Commit author**: `user.name` / `user.email` in git config, written into each commit | **Credentials**: the token used when you `git push` over HTTPS |
| Set by | `git config user.name ...` (local = this repo only; `--global` = all repos) | `gh auth login` / `gh auth switch` |
| Checked by | Nobody; it's a label (GitHub links commits to an account by the email) | GitHub, on every push |

So you can push with the work token while the commits say the personal email, or the reverse. Neither error is visible until later.

## 2. In this repo

- `gh auth status` lists both accounts on github.com, both with `https` as the git protocol and scopes `gist, read:org, repo, workflow`. Exactly one is **Active account: true**. Roman found the work account active, ran `gh auth switch` (with exactly two accounts it just flips to the other; `gh auth switch --user romaxod` is explicit and what you use with three or more) and got "Switched active account for github.com to romaxod". Then `git push` to `https://github.com/romaxod/georgian-voice-assistant.git` worked.
- **How git got the token:** `git config --show-scope --get-regexp credential` shows, in the *global* config, `credential.https://github.com.helper` (and one for `gist.github.com`) = `!/usr/bin/gh auth git-credential`, preceded by an empty `helper =` line that clears other helpers. A credential helper is a program git asks for a username/password; a leading `!` means "run this shell command" ([gitcredentials](https://git-scm.com/docs/gitcredentials)). That is what `gh auth setup-git` writes ([manual](https://cli.github.com/manual/gh_auth_setup-git)). It follows that git takes whichever account is *active* in `gh`, which is consistent with the switch fixing the push (I did not find a manual page that states this, so treat it as inferred).
- **Identity:** `git config --show-scope user.name` shows a *local* identity for this repo (Roman Kvitsaridze with a `users.noreply.github.com` email linked to `romaxod`) and a *different global* identity. Local overrides global ([scopes](https://git-scm.com/docs/git-config)), so commits here use the local one. A new repo without a local setting would use the global one. CLAUDE.md's rule is: set identity locally, never `--global`.

## 3. Safe habits

- Before any push: `gh auth status` (look for `Active account: true` under `romaxod`), and `git config user.email` inside the repo.
- Useful flags: `gh auth status --active` (only the active account), `--hostname github.com`. `--show-token` prints the secret; don't use it in a shared terminal or chat.
- Adding an account: `gh auth login` again (web flow). Not needed here.
- Mention only: git's `includeIf "gitdir:~/work/"` in `~/.gitconfig` can apply a different identity automatically by directory ([git-config](https://git-scm.com/docs/git-config)). With HTTPS and `gh`, credentials still follow `gh`'s active account, so identity and token can still disagree.
- SSH keys with per-host aliases are the other common way to separate accounts. We use HTTPS + `gh`.

Sources opened: <https://cli.github.com/manual/gh_auth_switch>, <https://cli.github.com/manual/gh_auth_status>, <https://cli.github.com/manual/gh_auth_login>, <https://cli.github.com/manual/gh_auth_setup-git>, <https://git-scm.com/docs/gitcredentials>, <https://git-scm.com/docs/git-config>.
