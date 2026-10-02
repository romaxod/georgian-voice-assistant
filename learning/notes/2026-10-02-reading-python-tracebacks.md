# Reading Python tracebacks

Checked 2026-10-02 against Python 3.14.0 (this repo's interpreter), docs.python.org and PEP 657.

## 1. What you're learning, and why it matters

**Problem:** a program fails and prints a wall of text (or, worse, one unhelpful line). Where do you look first, and what is it telling you?

- A **traceback** is the list of function calls that were active when an exception was raised, oldest first, newest last. The **exception** is the object describing the failure.
- **Read bottom-up.** The last line is `ExceptionType: message`. Just above it is the *innermost frame*: the exact line that raised. Everything above is "how we got here".
- Each **frame** is two lines:
  ```
    File "/path/venv/__init__.py", line 71, in create     <- file, line number, function name
      env_dir = os.path.abspath(env_dir)                   <- the source line
  ```
- **Carets (`~~~^^^`)** under the source line mark the exact sub-expression that failed (3.11+, [PEP 657](https://peps.python.org/pep-0657/)). `~` spans the expression, `^` the failing operation. Useful in lines like `a["x"]["y"]()`.
- **Special frames:** `File "<string>"` means code passed with `python -c` or `exec`, so there is no file. `File "<frozen posixpath>"` is a standard-library module compiled into the interpreter, so there is no `.py` path (the line number still counts lines in that module).
- **Chained exceptions:** if an error happens while handling another, Python prints both.
  - `During handling of the above exception, another exception occurred:` means the second was raised inside an `except` block (accidental or implicit).
  - `The above exception was the direct cause of the following exception:` means `raise NewError(...) from err` (deliberate).
  - Read the *last* traceback for what finally escaped, then the first for the root cause.
- **Exception types are a tree.** `FileNotFoundError` is a subclass of `OSError`. `OSError` carries an `errno` (here `2`, `ENOENT`, "No such file or directory"), so `except OSError` catches it too. The message may or may not include the filename. Ours didn't, which is itself a clue.
- **Why the real traceback can be hidden:** command-line tools (`python -m venv`, `pip`) catch exceptions in their `main()` and print one friendly line, then exit non-zero. You get `Error: [Errno 2] No such file or directory` and nothing else.

## 2. In this repo

BUILD_PLAN step 0.2: `python -m venv .venv` printed only `Error: [Errno 2] No such file or directory`. To see the traceback we called the same code from Python and printed it ourselves:

```
python -c "import venv, traceback
try: venv.EnvBuilder(with_pip=True).create('.venv')
except Exception: traceback.print_exc()"
```

The bottom of the output was:

```
  File ".../venv/__init__.py", line 71, in create
    env_dir = os.path.abspath(env_dir)
  File "<frozen posixpath>", line 384, in abspath
FileNotFoundError: [Errno 2] No such file or directory
```

How to read it: `abspath('.venv')` of a *relative* path calls `os.getcwd()` to prepend the current directory. So the failing function pointed at bad **input** (the shell's working directory no longer existed), not at a bug in `venv`. See [stale working directory](2026-10-02-stale-working-directory.md). That is the general lesson: the innermost frame names what failed, and you then ask what it was fed.

This is the "Break it" step of the learning loop in `PROJECT_CONTEXT.md` ("read the traceback"). When we break the graph on purpose in later steps (bad input, missing API key, failing tool), the traceback is the evidence we trace.

## 3. How the pieces fit together

```
your code -> library -> stdlib -> OS call fails (errno 2)
                                     |
   exception raised and unwinds up through every frame
                                     |
   CLI main() catches it -> prints one line   (hides the traceback)
   or nothing catches it -> interpreter prints the full traceback
```

Tools to surface or inspect it:

- `traceback.print_exc()` (inside `except`) prints the full traceback to stderr. `traceback.format_exc()` returns it as a string, which is handy for logging.
- `python -m pdb script.py` runs under the debugger. On an uncaught exception it stops *post-mortem* inside the failing frame, where you can `where` (stack), `up`/`down`, and `p variable`. `python -m pdb -m venv .venv` works for modules too.
- `breakpoint()` in your code pauses there and opens pdb.
- `python -X dev` turns on extra runtime checks (for example unclosed-file `ResourceWarning`). It does *not* un-hide a CLI's swallowed traceback, so don't reach for it first.
- `python -X faulthandler` dumps a traceback when the interpreter crashes hard (segfault).

## 4. Related tools

- `rich` / `better_exceptions` render prettier tracebacks. Not needed now; understand the plain one first.
- Your editor's debugger (VS Code) is a GUI over the same idea as pdb.
- In LangGraph/LLM apps you will see very deep tracebacks. The same rule applies: read the last line, find the innermost frame that is *your* code.

## 5. Hands-on exercises

Work in a scratch folder, not the repo (`mkdir -p /tmp/tb && cd /tmp/tb`).

1. Create `t.py` with `import json`, `def load(s): return json.loads(s)["k"]`, then `load('{"a": 1}')`. Run it. Check: the last line is `KeyError: 'k'`, and the carets underline `json.loads(s)["k"]`'s subscript.
2. Run `python t.py 2>&1 | tail -1`. Check: you get only the exception line. That is all some logs will show you, so know what it can and can't tell you.
3. Run `python -m pdb -c continue t.py`, then type `where`, `p s`, `q`. Check: `p s` prints `'{"a": 1}'`, the argument that caused the failure.
4. Create `c.py`: `try: open("nope.txt")` / `except OSError: raise RuntimeError("config load failed")`. Run it. Check: two tracebacks joined by "During handling...". Change the raise to `raise RuntimeError("...") from None` and see the first one disappear. Then use `from e` (with `except OSError as e`) and check the joining sentence changes to "direct cause".
5. `python -c "print(FileNotFoundError.__mro__)"`. Check: `OSError` appears in the chain. Then `python -c "import errno; print(errno.ENOENT)"` prints `2`.
6. Reproduce the real case in a throwaway dir: `mkdir /tmp/tb/gone && cd /tmp/tb/gone && rmdir ../gone`, then `python -m venv x`. Check: the same one-line error. Run the `traceback.print_exc()` snippet from section 2 and find the `abspath` frame. Finish with `cd /tmp`.

## 6. Self-check: can you answer these without looking?

1. Which line of a traceback do you read first, and what are the two things it gives you?
2. What does `File "<frozen posixpath>"` mean, and why is there no `.py` path?
3. What is the difference between "During handling..." and "direct cause" chaining?
4. Why does `os.path.abspath(".venv")` raise `FileNotFoundError`, and what does that tell you about where the bug is?
5. Why did `python -m venv` show one line while `traceback.print_exc()` showed more?
6. Name two ways to stop in a debugger at the failing line.

<details><summary>Answers</summary>

1. The last: the exception type and message. Then the frame just above it (the innermost call, where it was raised).
2. A stdlib module frozen into the interpreter at build time; no source file on disk, but the function name and line number are still shown.
3. "During handling" = a new exception was raised inside an `except` block without `from`. "Direct cause" = `raise X from Y` on purpose.
4. A relative path must be joined to the cwd, so it calls `os.getcwd()`, which failed because the shell's cwd was gone. The bad thing is the environment/input, not `venv`.
5. The CLI catches the exception and prints a short message. `print_exc()` prints the stored traceback.
6. `python -m pdb script.py` (post-mortem on an uncaught exception) and `breakpoint()` in the code.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Exercises 1-6 with questions as they come up | ~40 min |
| B. Another AI tutor | Different explanations, extra practice tracebacks | ~40 min |
| C. Primary docs | Accurate wording on chaining and `traceback` | ~45 min |
| D. Video/course | Seeing someone step through one first | 15-60 min, then do the exercises |

**A. Prompt for a main session in this repo:**
> Walk me through learning/notes/2026-10-02-reading-python-tracebacks.md. Do hands-on exercises 1-6 one at a time in /tmp/tb: run each, show me the output, and ask me to read the traceback aloud (bottom-up) before explaining. Then quiz me on the self-check questions.

**B. Tool:** NotebookLM with the C links loaded, or ChatGPT/Gemini. Prompt:
> I'm a CS student. Using only these sources, teach me how to read a Python traceback (bottom-up, frames, carets, chained exceptions) and how to get the traceback when a CLI hides it. Then give me 3 broken snippets and make me diagnose each from the traceback alone. Sources: https://realpython.com/python-traceback/, https://docs.python.org/3/tutorial/errors.html, https://docs.python.org/3/library/traceback.html, https://peps.python.org/pep-0657/, https://realpython.com/python-pdb/

**C. Reading list:**
- Real Python, "Understanding the Python Traceback": <https://realpython.com/python-traceback/>. Start here; bottom-up reading and common exceptions.
- Python tutorial, "Errors and Exceptions" (section 8.5 Exception Chaining): <https://docs.python.org/3/tutorial/errors.html>. The two "During handling" / "direct cause" messages with examples.
- `traceback` module: <https://docs.python.org/3/library/traceback.html>. `print_exc`, `format_exc`, and the `chain` parameter.
- PEP 657, fine-grained error locations: <https://peps.python.org/pep-0657/>. Why the carets exist (Python 3.11).
- Real Python, "Python Debugging With Pdb": <https://realpython.com/python-pdb/>. Commands, `breakpoint()`, post-mortem.
- Python Morsels, "Deciphering Python's Traceback": <https://www.pythonmorsels.com/reading-tracebacks-in-python/>. Short, with a ~4 minute screencast.

**D. Video / course** (found by search 2026-10-02; I did not open the video pages, so check they play for you):
- "Getting the Most Out of a Python Traceback", Real Python video course: <https://realpython.com/courses/python-traceback/>. The video version of the article. Some Real Python lessons need a paid account.
- "Debugging in Python With pdb", Real Python video course: <https://realpython.com/courses/python-debugging-pdb/>.
- "Python 101 - Debugging Your Code with pdb (Video)", Mike Driscoll: <https://www.blog.pythonlibrary.org/?p=11549>. Covers `set_trace()` and `breakpoint()`.
- I could not confirm a specific YouTube video via search. If you want one, search YouTube for "python traceback explained" and pick one from a known channel.

Whatever you choose, finish with the exercises and the self-check.
