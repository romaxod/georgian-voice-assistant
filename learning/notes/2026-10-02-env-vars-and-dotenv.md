# Environment variables and python-dotenv

*(short note)* Checked 2026-10-02 against python-dotenv 1.2.4 (installed source, and I ran the examples below with fake values) and docs.python.org. Where `.env` and keys fit is also in [api-tokens-and-pricing](2026-10-02-api-tokens-and-pricing.md); this note covers the mechanism.

## 1. What and why

**Problem:** the code needs secrets (API keys) and settings (region) that must not be in the source or in git, and that differ per machine.

- An **environment variable** is a name/value string pair stored in a *process*. A child process gets a **copy** of its parent's variables when it starts. Changing a variable in the child never affects the parent.
- Shell: `export NAME=x` sets it for the shell and everything it launches afterwards. `NAME=x command` sets it for that one command only (`A=x bash -c 'echo $A'` prints `x`, and afterwards `A` is unset again). `env` / `printenv NAME` list what a process would pass down.
- Python: `os.environ` is a dict-like mapping of the variables. `os.environ["NAME"]` raises `KeyError` if missing. `os.getenv("NAME")` returns `None` (or a default you pass: `os.getenv("NAME", "dflt")`). Use `getenv` when absence is a normal case and you want to print a friendly error; use `[]` when absence is a bug you want to fail on. `os.environ` is a snapshot taken at startup plus your own changes ([docs](https://docs.python.org/3/library/os.html)).
- A **`.env` file** is a plain text file of `NAME=value` lines. `python-dotenv`'s `load_dotenv()` reads it and copies those lines into `os.environ` of the *current* Python process. It does not change your shell.

## 2. In this repo

`check_env.py` does `load_dotenv()`, then `os.getenv(name)` for `OPENAI_API_KEY`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, and prints only `len(value)` (164 / 84 / 10 characters). **Printing a secret's length (or just "set") is the safe check; never print the value**, because terminals, logs and chat transcripts keep it.

- **Override rule:** `load_dotenv()` defaults to `override=False`: a variable already set in the process wins over the `.env` line (signature confirmed in the installed 1.2.4, and README). So the step 1.1 break test `OPENAI_API_KEY=sk-wrong python first_call.py` really sends the fake key; the key in `.env` is ignored for that run. I ran this pattern with a throwaway `.env`: shell `A=shell`, `.env` `A=one` gave `shell`, and `load_dotenv(override=True)` gave `one`.
- **How it finds the file:** `load_dotenv()` with no path calls `find_dotenv()`, which starts in the folder of the *script that called it* and walks up through parent folders until it finds a file named `.env` (returns `""` and `load_dotenv` returns `False` if none). In a REPL, `python -c`, or under a debugger there is no script file, so it starts from the current working directory instead. I confirmed: the same `-c` snippet found `.env` from the project folder and returned `False` from `/`. To be explicit: `load_dotenv("/path/.env")`.
- **Syntax** (tested): `# comment` lines are ignored; spaces around the key, `=` and the value are ignored (`  B = two words`); an unquoted value may have a trailing ` # comment`; quotes keep a `#` inside the value (`C="a # b"`); a leading `export ` is allowed; `E=` gives an empty string `''` (which `if value:` treats as missing). `${OTHER}` is expanded; a bare `$OTHER` is not.
- **Why `OpenAI()` needs no key argument:** the SDK constructor reads `OPENAI_API_KEY` from the environment itself (its docstring says so). That is why `load_dotenv()` only has to run *before* `OpenAI()` is created. If the variable is missing you get `OpenAIError: Missing credentials...` at construction, before any network call.

## 3. How it fits together

```
.env (file, gitignored) --load_dotenv()--> os.environ (this process) --> OpenAI() reads OPENAI_API_KEY
shell: VAR=x python script.py ------------> os.environ (wins over .env unless override=True)
```

## 4. Related tools

- `direnv` loads `.env`-style files into your *shell* when you `cd`; `uv run --env-file` and Docker `--env-file` do similar. We use python-dotenv because it is one line in Python.
- Real secret managers (Azure Key Vault, etc.) are what a production system would use; a `.env` is only for local development.
- Source: python-dotenv README, <https://github.com/theskumar/python-dotenv> (opened: override default, `.env` syntax, `${VAR}` expansion, gitignore advice).
