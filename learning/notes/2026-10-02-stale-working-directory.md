# Stale working directory

*(short note)* Checked 2026-10-02 against the bash source (`builtins/cd.def`) and by reproducing the symptom on this machine.

## 1. What and why

**Problem:** the prompt shows `/mnt/c/prog/ABSTR ASSN/georgian-voice-assistant`, but `python -m venv .venv` fails with `[Errno 2] No such file or directory`, even though the folder is clearly there.

- Every process has a **current working directory (cwd)**. The kernel stores it as a reference to a *directory object* (an inode), not as text. `os.getcwd()` / `getcwd(3)` asks the kernel to rebuild the path from that object.
- Your shell's `$PWD` is only **text** it remembers (`echo $PWD`). Bash prints it for the prompt and for `pwd` without asking the OS.
- If the folder is deleted, renamed, or deleted and recreated *after* you `cd`'d in, the process still points at the old object. The text still looks right, and a new folder may even exist at that path, but the old one is gone. Any command that needs the real cwd gets `ENOENT`.
- Relative paths (`.venv`, `./x`) are resolved against the cwd, so the failure shows up in unrelated commands. In our case `os.path.abspath('.venv')` calls `os.getcwd()` (see [reading tracebacks](2026-10-02-reading-python-tracebacks.md)).
- Symptoms: `ENOENT` from commands that use relative paths; `shell-init: error retrieving current directory: getcwd: cannot access parent directories` printed by bash or by tools like `pyenv` shims; `pwd: error retrieving current directory`.

## 2. In this repo

- Roman's shell failed; a fresh shell in the same folder worked; after `cd "/mnt/c/prog/ABSTR ASSN/georgian-voice-assistant"` it worked for him too. Most likely the folder was deleted/recreated or renamed from the Windows side after he had `cd`'d in. **This was not verified**; it's the explanation that fits.
- Surprise we hit: bash's builtin `pwd -P` printed the path fine *before* the `cd`. Bash's source (`pwd_builtin`) uses its cached `$PWD` text; with `-P` it resolves symlinks in that text with `lstat`, and only falls back to `getcwd` if that fails. If a folder exists again *by name*, the text check passes while the real cwd is dead. So the builtin is not a reliable test.
- I reproduced it on Linux with `mkdir d && cd d && rm -r ../d && mkdir ../d`: builtin `pwd -P` printed the path, `/bin/pwd` failed with `couldn't find directory entry in '..' with matching i-node`, and `python -c "import os; print(os.getcwd())"` raised `FileNotFoundError`. (Note: on `/mnt/c` the Windows side does the deleting, but the symptom is the same one Roman saw.)

Reliable checks (both ask the OS): `/bin/pwd` and `python -c "import os; print(os.getcwd())"`.

## 3. How it fits together

```
shell process --cwd--> directory object (deleted/renamed)    <- kernel's truth
      |
      +-- $PWD = "/mnt/c/.../georgian-voice-assistant"       <- just text
child process (python) inherits the cwd object, calls getcwd -> ENOENT
```

**Fix:** `cd "/mnt/c/prog/ABSTR ASSN/georgian-voice-assistant"` (the full path again), or `cd .`/`cd "$PWD"` (re-enters by name; may print the same error once). `cd -P .` also works. Quote paths with spaces: unquoted, `ABSTR ASSN` is two arguments to `cd`.

Related: `pwd -L` (default) prints the logical path with symlinks as you typed them; `pwd -P` prints the physical path with symlinks resolved. Both are text-based in bash as shown above.

## 4. Related tools

- Moving the repo into the Linux filesystem makes this rarer, since Windows apps no longer touch the folder. See [WSL filesystems](2026-10-02-wsl-filesystems.md).
- `lsof -p $$ | grep cwd` (if installed) shows what the shell's cwd points to; a deleted one is marked `(deleted)` on native Linux filesystems.
- Sources: GNU Bash manual, `pwd` builtin: <https://www.gnu.org/software/bash/manual/html_node/Bourne-Shell-Builtins.html> (the page was rate-limited when I tried it, so the behaviour above comes from the bash source file `builtins/cd.def` at <https://cgit.git.savannah.gnu.org/cgit/bash.git/plain/builtins/cd.def>, which I opened).
