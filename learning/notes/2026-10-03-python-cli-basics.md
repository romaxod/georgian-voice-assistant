# Python for interactive CLI programs

*(short note)*

Date: 2026-10-03. Checked against the Python 3 docs (tutorial pages on errors and introduction, `argparse` HOWTO, `__main__`, built-in functions) and by running throwaway snippets. The code is `chat.py`; its line-by-line explanation is `docs/code/chat.py.md`.

## 1. What and why

**Problem:** a program that talks to a user in a loop must read lines, stop cleanly, take options, and be testable without a human typing. Python's standard library covers it.

- **`input(prompt)`** prints the prompt and returns one line without the newline. At **end of input** it raises `EOFError` (docs: "When EOF is read, EOFError is raised"). End of input happens when you press Ctrl-D (Linux/macOS; Ctrl-Z then Enter on Windows) or when piped input runs out. **Ctrl-C** raises `KeyboardInterrupt`. Neither is a bug, so `chat.py` treats both as "quit".
- **`while True:` + `break` / `continue`.** `break` leaves the loop (empty line, `exit`); `continue` skips to the next round (after `/reset` or a failed API call).
- **Catching several exceptions:** `except (EOFError, KeyboardInterrupt):` takes a *tuple*; any listed class or subclass matches. Order matters when classes are related: `AuthenticationError` is caught first in `chat.py` because it is also an `APIStatusError`, which is caught below.
- **`argparse`** builds the command line: `ArgumentParser(description=...)`, `add_argument("--no-memory", action="store_true", help=...)`, `parse_args()`. `store_true` makes a flag: `args.no_memory` is `True` if given, else `False` (dashes become underscores). `--help` is generated for free: `python chat.py --help`.
- **Lists and slicing.** `history` is a list of dicts: `{"role": "user", "content": "..."}`. `append(x)` adds at the end, `pop()` removes and returns the last, `clear()` empties it. `history[-1]` is the last *element* (an error on an empty list); `history[-1:]` is a *new list* with at most one element (empty list, no error). `chat.py` needs a list for `input=`, hence `[-1:]`. Slicing past the start is safe: `h[-4:]` on a 3-item list returns all 3.
- **Type hints** (`history: list[dict]`, `-> None`, `-> float`) document intent for readers and tools like mypy. Python does **not** enforce them at runtime.
- **`if __name__ == "__main__": main()`.** When you run a file, its `__name__` is `"__main__"`; when another file imports it, `__name__` is the module name. The guard means importing `chat.py` (for a test) doesn't start the chat. Putting the work in `main()` also keeps variables out of module scope.
- **`getattr(obj, name, default)`** reads an attribute by name and returns `default` instead of raising `AttributeError`. `chat.py` uses `getattr(e, 'message', e)` so it works for exceptions that lack a `message` attribute.
- **Testing by piping stdin.** `printf 'q1\nq2\n' | .venv/bin/python chat.py` feeds lines to `input()` and then EOF ends the loop. `<<< 'text'` (bash here-string) sends one line. Because stdin is not a terminal, nothing echoes what "you typed", so the next output continues on the same line as the prompt: `თქვენ: ჯიხვი: ...`. I confirmed with a throwaway loop that piped `a`, `b` give `Q: 'a'`, `Q: 'b'`, then `EOFError`.

## 2. In this repo

`chat.py` uses every item above. Example: `printf '...\n...\n' | .venv/bin/python chat.py --no-memory` combines a pipe and a flag; `OPENAI_API_KEY=sk-wrong .venv/bin/python chat.py <<< 'გამარჯობა'` tests the error path and exits with code 1 (`echo $?`).

## 3. How it fits

`argparse` decides *how* the program runs, the `while True` loop reads and dispatches, `try/except` turns expected failures (end of input, API errors) into clean exits, and piping lets you run the same loop in a test without a keyboard.

## 4. Related tools

- `click` and `typer`: nicer third-party CLI libraries. `argparse` is enough and has no install.
- `sys.stdin.readline()` / `for line in sys.stdin`: read lines without a prompt.
- `pytest` with `monkeypatch` or `capsys`: test `input()` loops in code instead of in the shell.
- `readline`/`prompt_toolkit`: line editing and history in interactive prompts.

## 5. Small Python bits from `faq.py` *(added 2026-10-03)*

Checked against the `pathlib`, `json` and `argparse` docs and by running snippets.

- **`Path(__file__).parent / "data"`**: `__file__` is the script's own path; `.parent` is its folder; `/` joins path pieces. Paths built this way work from any current directory, unlike `"data/faq.json"`, which depends on where you ran `python` from.
- **`Path.read_text(encoding="utf-8")`** opens, reads, closes in one call. Always pass the encoding for Georgian text; the default depends on the OS (on Windows it may not be UTF-8).
- **`.stat().st_mtime`**: last-modified time in seconds (float). `faq.py` compares db and JSON mtimes to decide whether to rebuild.
- **`json.loads(s)`** parses a **string**; **`json.load(f)`** parses an open **file**. `json.dumps(obj, ensure_ascii=False, indent=2)`: without `ensure_ascii=False` Georgian prints as `ბ` escapes (valid JSON, unreadable); `indent=2` pretty-prints.
- **`argparse` `nargs="*"`**: a positional argument takes zero or more words into a list, so `python faq.py ჯიხვი M` gives `["ჯიხვი", "M"]` and `" ".join(...)` rebuilds the query. No quotes needed. Empty list when omitted.
- **`dict.fromkeys(list)`** makes a dict with the list items as keys; dicts keep insertion order and keys are unique, so `list(dict.fromkeys(words))` removes duplicates while keeping order (a `set` would lose order).
- **JSON-friendly returns:** `lookup_faq` returns a list of plain `dict`s (`{k: row[k] ...}`), not `sqlite3.Row` objects, because `json.dumps` can't serialize `Row`. In step 1.4 the result can go straight into a tool message.

## 6. Monkeypatching a module attribute for a break test *(added 2026-10-03)*

To test "what if the database fails?" without breaking the real DB, replace the function at run time:

```python
import chat
def broken(topic): raise sqlite3.OperationalError("boom")
chat.lookup_faq = broken      # works
```

- **Why `chat.lookup_faq` and not `faq.lookup_faq`:** `chat.py` does `from faq import lookup_faq`, which copies the *name* into `chat`'s namespace. `run_tool` looks the name up there. Patching `faq.lookup_faq` changes a different binding, and `chat` would keep calling the original. Rule: **patch where it's looked up**, not where it's defined.
- Equivalent in a test framework: `unittest.mock.patch("chat.lookup_faq", side_effect=sqlite3.OperationalError("boom"))` used as a `with` block or decorator; it restores the original afterwards (plain assignment doesn't). Docs: <https://docs.python.org/3/library/unittest.mock.html#where-to-patch> (section "Where to patch"; I did not open this page, it is from memory of the docs structure, so check it).
- Used in step 1.4 to show the model receives `{"error": ...}` and answers honestly ([function calling note](2026-10-03-function-calling-responses-api.md)).

## 7. From `speech_smoke.py` *(added 2026-10-03)*

Checked against the `argparse`, `threading`, `time` and `wave` docs (threading.Event page opened) and by running the script.

- **Subcommands:** `commands = parser.add_subparsers(dest="command", required=True)`, then `rec = commands.add_parser("record", help=...)` and `rec.add_argument(...)` per command, like `git commit`. `dest="command"` stores the chosen name in `args.command`; `required=True` makes a missing subcommand an error (otherwise it is `None`). Each subparser has its own options and `--help`.
- **Nested functions as callbacks (closures):** `on_recognized` is defined inside `transcribe` and uses the local list `parts`. An inner function can *read* and *mutate* outer variables; `parts.append(x)` mutates the list, so no `nonlocal` is needed. Writing `parts = []` inside it would create a new local instead, and rebinding an outer name needs `nonlocal parts`. The SDK later calls the function from another thread, and it still sees `parts`.
- **`threading.Event`:** a flag shared between threads. `done.set()` raises it; `done.wait(timeout=30)` blocks until set and returns `True`, or `False` if the timeout passed first. Used to let the main thread sleep until the SDK's `session_stopped` callback fires.
- **`time.perf_counter()`:** a high-resolution clock for timing; only differences are meaningful (`end - start`). `time.time()` is wall-clock and can jump.
- **`wave` module:** `with wave.open(path, "rb") as w:` then `getframerate()` (Hz), `getsampwidth()` (bytes per sample), `getnchannels()`, `getnframes()`, `readframes(n)` (bytes). Duration = `getnframes() / getframerate()`; e.g. 88,000 frames at 16 kHz = 5.5 s.
- **`array("h", bytes)`:** `from array import array` turns raw bytes into a compact array of signed 16-bit ints (`"h"`), so `max(map(abs, samples))` finds the loudest sample. It uses your machine's byte order (little-endian here, matching WAV).

## 8. Typing bits from `graph.py` *(added 2026-10-03)* *(short note)*

Checked against the `typing` docs (TypedDict, Annotated, Literal sections opened) and by running snippets. Type hints are still not enforced by Python; libraries (LangGraph, Pydantic) *read* them at runtime.

- **`TypedDict`:** a dict type with known keys: `class State(TypedDict): messages: list`. At runtime it is a plain `dict`. `total=False` makes every key optional, which `State` needs because each node returns only some keys and the first call has no `facts` yet. That is why code uses `state.get("facts")` for optional keys.
- **`Annotated[T, meta]`:** the type `T` plus extra metadata that type checkers ignore. A library can read it: `Annotated[int, "x"].__metadata__` is `('x',)` and `.__origin__` is `int`. LangGraph reads the metadata to find the **reducer**: `Annotated[list[AnyMessage], add_messages]`, `Annotated[float, operator.add]`.
- **`Literal["faq","other"]`:** only these exact values are allowed. A type checker flags `"typo"`; Pydantic raises `ValidationError`; used as a return type on `route_after_understand`, LangGraph reads it as the list of possible next nodes.
- **`X | None`** (Python 3.10+): same as `Optional[X]`; `lookup_error: str | None`. `llm: ChatOpenAI | None = None` is the "optional argument with a default made inside" idiom: `llm = llm or ChatOpenAI(...)`.
- **`operator.add`:** the `+` operator as a function: `operator.add(2, 3) == 5`, `operator.add([1], [2]) == [1, 2]`. A reducer is called `reducer(old, new)`, so it sums floats and joins lists.
- **`uuid.uuid4()`:** a random unique id; `str(uuid.uuid4())` gives text like `'3f2b...'`. Used for `thread_id` (new conversation) and for message ids.

## Sources

- Python tutorial, Errors and Exceptions (8.3 Handling Exceptions covers multiple exceptions): <https://docs.python.org/3/tutorial/errors.html>
- Python `argparse` tutorial (HOWTO), including `store_true`: <https://docs.python.org/3/howto/argparse.html>
- Python tutorial, An Informal Introduction (lists, slicing, negative indices): <https://docs.python.org/3/tutorial/introduction.html>
- `__main__` and the `main()` pattern: <https://docs.python.org/3/library/__main__.html>
- Built-in functions (`input`, `getattr`): <https://docs.python.org/3/library/functions.html>
- `typing` (TypedDict, Annotated, Literal): <https://docs.python.org/3/library/typing.html> *(opened 2026-10-03)*
- Real Python, "How to Build Command Line Interfaces in Python With argparse": <https://realpython.com/command-line-interfaces-python-argparse> (title and URL confirmed in a search result; the page returned 403 to my fetch, so I haven't read it).
- Related notes: [reading tracebacks](2026-10-02-reading-python-tracebacks.md), [env vars and dotenv](2026-10-02-env-vars-and-dotenv.md).
