# Dependencies and pinning

*(short note)* Checked 2026-10-02 against pip's docs, packaging.python.org specs, and `pip show` in this repo's `.venv`. Venv basics are in [SETUP.md section 3](../../SETUP.md).

## 1. What and why

**Problem:** you `pip install openai` today; a teammate (or you in three months) installs it and gets different versions of its helpers, and something breaks. How do you rebuild the *same* environment?

- **Direct dependency:** a package you chose (`openai`, `python-dotenv`). **Transitive dependency:** a package those need. `pip install openai python-dotenv` installed 15 packages, but we asked for 2.
- Each package declares what it needs with **version specifiers** ([PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)): `>=4.10.0` (at least), `<5` (below), `!=2.0.*` (exclude a range), `==2.13.1` (exactly), `~=1.4.5` (compatible: 1.4.5 up to but not including 1.5). Commas mean AND. That is what you saw in pip's output: `anyio<5,>=4.10.0 (from openai)`; `httpcore2==2.13.1 (from httpx2...)` is an exact pin between two packages.
- pip's **resolver** picks one version of each package that satisfies everyone's specifiers. Different times or platforms can resolve differently, hence pinning.
- **Wheels** are prebuilt packages named `name-version-{python tag}-{abi tag}-{platform tag}.whl` ([spec](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)). `py3-none-any` = pure Python, works anywhere. `cp314-cp314-manylinux_2_17_x86_64` = compiled for CPython 3.14 on Linux x86-64 (glibc 2.17+). `jiter` and `pydantic_core` are compiled (Rust); the rest here are pure Python. If no wheel fits your Python/OS, pip builds from source, which is slower and may need a compiler. A new Python like 3.14 is where this bites.
- **"Using cached":** pip keeps downloaded files and built wheels in `~/.cache/pip` (`python -m pip cache dir`), so reinstalling doesn't re-download ([caching docs](https://pip.pypa.io/en/stable/topics/caching/)).

## 2. In this repo

- Direct vs transitive, verified with `python -m pip show openai` (`Requires: anyio, httpx2, jiter, pydantic, sniffio, typing-extensions`). `Required-by:` shows who needs a package: `anyio` is required by `httpx2` and `openai`. `pip install pipdeptree` then `pipdeptree` draws the whole tree (optional, not installed here).
- **`python -m pip freeze > requirements.txt`** writes every installed package as `name==exact.version` (15 lines). It leaves out `pip` itself (Python 3.12+ omits only pip) ([docs](https://pip.pypa.io/en/stable/cli/pip_freeze/)), which is why upgrading pip 25.2 to 26.2.1 doesn't show. To recreate: new venv, then `python -m pip install -r requirements.txt` ([format](https://pip.pypa.io/en/stable/reference/requirements-file-format/)).
- **Decision:** freeze, not a hand-written list, so the environment is exactly reproducible. Trade-off: the file doesn't say which 2 packages you chose, and upgrading one means editing exact pins. Pip's own docs note freeze "reports what is installed; it does not compute a lockfile".

## 3. Choices for tracking dependencies

| Approach | Good | Weak |
|---|---|---|
| Hand-written top-level list (`openai`, `python-dotenv`) | Readable, easy to upgrade | Transitive versions drift |
| `pip freeze` (what we do) | Exact snapshot, no extra tools | Mixes direct and transitive; no resolver step; platform-specific |
| `requirements.in` + `pip-compile` (pip-tools) or `uv pip compile` | You write only top-level; the tool writes a fully pinned `requirements.txt` ([uv docs](https://docs.astral.sh/uv/pip/compile/)) | One more tool |
| `pyproject.toml` + `uv lock` | Modern project standard with a real lock file | New workflow to learn |

For a small project, freeze is fine. If we later add `uv`, SETUP.md section 3 already points to it as the tool that automates this.

Also: `pip install --upgrade pip` upgrades pip itself in the venv. The "new version available" notice is informational; upgrading changes nothing in `requirements.txt`.
