# WSL: /mnt/c (Windows drive) vs the Linux filesystem

*(short note)* Checked 2026-10-02 against learn.microsoft.com (Working across file systems, WSL FAQ, wsl.conf reference) and this machine's `mount`.

## 1. What and why

**Problem:** Windows and Linux both want to own your files. WSL2 runs a real Linux in a lightweight VM, and your project folder can live on either side.

- **Linux filesystem:** the distro's own disk (ext4 inside a virtual disk file). Your home is `~` = `/home/roma1218`. Native speed, normal Linux permissions and case sensitivity.
- **Windows drives:** WSL mounts them under `/mnt/<letter>`. Here: `mount | grep ' /mnt/c '` shows
  `C:\ on /mnt/c type 9p (rw,noatime,aname=drvfs;path=C:\;uid=1000;gid=1000;symlinkroot=/mnt/,...)`.
  - **9p** is a network-style file protocol between the Linux VM and Windows; **DrvFs** is the WSL plugin that maps a Windows drive into Linux. Every file operation crosses the VM boundary, and Windows (NTFS) is the real owner of the data.
- **Microsoft's guidance:** store files in the filesystem of the tools you use. Linux command line (Ubuntu, bash, Python on Linux) means `/home/<user>/Project`, not `/mnt/c/Users/<user>/Project`, "for the fastest performance". Mounted drives work, just slower.

## 2. In this repo

The repo is at `/mnt/c/prog/ABSTR ASSN/georgian-voice-assistant`, i.e. on `C:\`. It works. Quirks you can see or may meet:

- **Speed:** many small-file operations (`git status`, `pip install`, creating `.venv` with thousands of files) are slower than on `~`. Fine for this project's size.
- **Permissions:** every file shows as mode 777 (`stat -c %a SETUP.md` printed `777` here). By default DrvFs doesn't store Linux permissions (`metadata` is disabled, `fmask`/`dmask` default `000`), so `chmod` does little. Docs: wsl.conf "Automount options". Mostly harmless, but SSH keys and `.env` can't be made private there. Keep keys out of the repo anyway.
- **Windows apps touch the folder:** Explorer, OneDrive/antivirus, an IDE open on the Windows side can lock, rename or recreate folders. This is the likely cause of the [stale working directory](2026-10-02-stale-working-directory.md) problem.
- **Case sensitivity and filenames:** Windows treats `A.txt` and `a.txt` as the same by default and forbids some characters; Linux files on `~` follow Linux rules. Code that runs on a Linux server can hide case bugs when developed on `/mnt/c`.
- **Symlinks:** the FAQ says Linux-side symlinks work normally; on mounted drives they depend on Windows rules (this can affect tools that create symlinks, such as some venv or package layouts).
- **Import cost, measured *(added 2026-10-03, short note)*:** `/usr/bin/time -f "%e s wall" python -c "import graph"` took **14.4 s and 15.0 s wall**, while `time` showed only user 2.1 s + sys 0.7 s. The gap is waiting, not computing: Python reads thousands of small `.py`/`.pyc` files from `.venv`, and each read crosses the 9p mount. `python -X importtime -c "import graph" 2> t.txt` shows per-module times (stderr; columns are self µs, cumulative µs, module name; Python docs for `-X importtime`): `openai.types` 4.0 s cumulative, `openai` 4.2 s, `langchain_openai` 7.5 s, `graph` 12.6 s. Only **startup** is affected; a turn's latency (LLM, Azure) isn't.
  - **Options (not done; Roman's choice):** (1) keep the code here but put the venv on the Linux disk: `python -m venv ~/.venvs/gva`, activate that one, `python -m pip install -r requirements.txt` (the packages are most of the files; keep the repo's `.venv` out of use). (2) move the repo to `~/projects/` (see "Moving is optional" below).
  - **Verify with the same two commands** before and after. If wall time falls close to user+sys (about 3 s), the mount was the cause. A second run is sometimes faster from caches, so repeat each twice.
- **Spaces in the path** (`ABSTR ASSN`) work but need quoting everywhere.

## 3. How it fits together

```
Windows (NTFS, C:\)  <--9p/DrvFs-->  /mnt/c  (what Linux tools see)
WSL2 VM (ext4 virtual disk)           ~, /home/roma1218  (native)
```

Open the Linux side from Windows: `explorer.exe .` in a WSL shell opens the current folder in Explorer, and `\\wsl$` (or `\\wsl.localhost\Ubuntu`) in the address bar lists distros. In VS Code, run `code .` from a WSL shell (installs the VS Code server in WSL once) or use "WSL: Connect to WSL" / "WSL: Reopen Folder in WSL" from the Command Palette. VS Code works on both `/mnt/c` and `~`.

**Moving is optional.** Staying on `/mnt/c` is fine for now. If the stale-cwd error or slowness repeats, `git clone` (or copy) the repo into `~/projects/`, work there, and open it with `code .`. Keep the `.git` history by cloning instead of copying `.venv` (venvs aren't portable between paths anyway).

## 4. Related tools

- Run everything on Windows natively instead of WSL: possible, but Linux-first tooling (bash scripts, pyenv, hooks) is why we chose WSL.
- Docker/devcontainers have the same guidance: keep bind-mounted code on the Linux side.

Sources opened: <https://learn.microsoft.com/en-us/windows/wsl/filesystems> (performance advice, `explorer.exe .`, `\\wsl$`, case sensitivity), <https://learn.microsoft.com/en-us/windows/wsl/faq> (files on Linux root vs mounted drives, permissions behaviour), <https://learn.microsoft.com/en-us/windows/wsl/wsl-config> (DrvFs, `metadata`, `fmask`), <https://code.visualstudio.com/docs/remote/wsl> (`code .`, Reopen Folder in WSL). The general speed advice is Microsoft's guidance; the import timing above was measured here on 2026-10-03.
