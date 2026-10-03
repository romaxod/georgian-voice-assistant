# SQLite from Python

Date: 2026-10-03. Checked against the Python `sqlite3` docs, sqlite.org ("Appropriate Uses", command-line shell) and by running snippets in this repo (SQLite 3.45.1, Python 3.14). Line-by-line code: `docs/code/faq.py.md`.

## 1. What you're learning, and why it matters

**Problem:** the assistant needs a store of facts (the 21 FAQ entries) it can search, without running a database server and without stuffing everything into the prompt.

- **SQLite** is a database engine that lives in a library and stores everything in **one file** (`data/faq.db`). No server process, no accounts, no network. Your program opens the file like any other.
- **Postgres/MySQL** are client/server databases: a separate process, many clients over the network, many simultaneous writers. Choose them when data lives on another machine, many writers need it at once, or it's huge. sqlite.org's own guide says the same: SQLite fits local data, low write concurrency (one writer at a time), under about a terabyte. A 21-row read-mostly FAQ is the ideal case.
- **`sqlite3` module** (standard library, nothing to `pip install`) is Python's interface:
  - `conn = sqlite3.connect(path)` opens (or creates) the file. `":memory:"` gives a throwaway in-RAM database.
  - `conn.execute(sql, params)` runs one statement; `conn.executemany(sql, list_of_dicts)` runs it once per item (`INSERT INTO faq VALUES (:id, :topic, ...)` takes each dict's keys; `:name` is a **named placeholder**).
  - `.fetchall()` returns all rows; by default each row is a tuple. `conn.row_factory = sqlite3.Row` makes rows addressable by column name (`row["answer"]`).
- **Transactions.** A **transaction** groups statements so they all apply or none do. Python opens one implicitly before an `INSERT`/`UPDATE`/`DELETE`; `conn.commit()` saves it, `conn.rollback()` undoes it. Nothing is permanent until commit.
- **The `with` gotcha.** `with sqlite3.connect(p) as conn:` commits on success and rolls back on an exception, but **does not close the connection** (docs: "neither implicitly opens a new transaction nor closes the connection"). Verified: after a `with` block, `conn.execute("select 1")` still works. So close explicitly, either `try/finally: conn.close()` (what `lookup_faq` does) or `contextlib.closing(...)`. An unclosed connection holds a file handle, and on Windows/`/mnt/c` can keep the file locked.
- **Source vs generated data.** `data/faq.json` is the **source of truth**: text, readable in `git diff`, reviewed by humans. `data/faq.db` is a binary built from it, so it is gitignored (`data/*.db`). Committing binaries bloats history and can't be diffed or merged. The rule: commit what people edit, regenerate what machines derive.

## 2. In this repo

- `build_db()` reads the JSON, drops and recreates table `faq` (`id TEXT PRIMARY KEY, topic, question, answer, keywords`) and bulk-inserts with `executemany`.
- `_ensure_db()` rebuilds when the db is missing or its mtime is older than the JSON's (the `make` idea: output older than input means stale).
- `lookup_faq` opens a connection, sets `row_factory`, queries inside `try/finally`, and converts rows to plain dicts.
- Poke at the file. The system `sqlite3` command isn't installed here, but Python 3.12+ ships a small shell: `.venv/bin/python -m sqlite3 data/faq.db`. It only knows a few dot-commands (`.tables` and `.schema` fail with "unknown command"), so use SQL: `select name, sql from sqlite_master;`. With the real CLI (`sudo apt install sqlite3`) you get `.tables`, `.schema`, `.headers on`, `.mode box`.

## 3. How the pieces fit

```
faq.json --(build_db, if stale)--> faq.db --(lookup_faq: SELECT)--> list of dicts --> json.dumps / tool result
 committed                         gitignored
```

## 4. Related tools

- **Postgres:** the right answer for a real production system (many users, many writers, network). Same SQL, different driver (`psycopg`).
- **`json` file loaded into a list:** fine for 21 entries, but you'd re-implement search yourself. SQL gives filtering, ordering and limits for free and shows a real pattern.
- **SQLAlchemy / ORMs:** map tables to Python classes. Overkill here.
- **`:memory:` databases and `pytest`:** good for tests.

## 5. Hands-on exercises

1. `.venv/bin/python -m sqlite3 data/faq.db`, then `select id, topic from faq limit 5;`. Check: you see Georgian topics.
2. `touch data/faq.json` then `.venv/bin/python faq.py ბარათი`. Check: `ls -l --time=ctime data/faq.db` shows a new timestamp (it rebuilt); run again, it doesn't change.
3. In a Python REPL: `c = sqlite3.connect(":memory:")`, `with c: c.execute("create table t(a)")`, then `c.execute("select 1")`. Check: no error, so the connection is still open. Call `c.close()` and retry; now `ProgrammingError`.
4. Insert a row inside `with c:` then raise an exception inside the block. Check: the row is gone (rollback).
5. Fetch with and without `row_factory = sqlite3.Row`; compare `row[0]` and `row["answer"]`.

## 6. Self-check

1. Why SQLite and not Postgres for this FAQ? 2. What does `with sqlite3.connect()` do and not do? 3. Why is `faq.db` gitignored but `faq.json` committed? 4. What's a transaction and when is data saved? 5. What does the mtime check do?

<details><summary>Answers</summary>

1. Local, read-mostly, tiny data, no server to run; Postgres adds ops cost for nothing here. 2. Commits/rolls back, does not close. 3. JSON is the editable, diffable source; the db is a generated binary. 4. A group of statements applied all-or-nothing; saved at commit. 5. Rebuilds the db when the JSON is newer, so edits take effect without a manual step.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Doing the exercises on this repo | 30 min |
| B. Another AI tutor | Quizzing, extra examples | 30 min |
| C. Primary docs | Exact semantics (transactions, placeholders) | 1 h |
| D. Video/course | Seeing SQL basics end to end | 1.5 h |

**A.** Paste: "Read learning/notes/2026-10-03-sqlite-from-python.md and walk me through exercises 1-5 on faq.py and data/faq.db, one at a time, explaining each result."

**B.** NotebookLM (or ChatGPT/Gemini) with the C links as sources. Prompt: "Using https://docs.python.org/3/library/sqlite3.html and https://www.sqlite.org/whentouse.html, explain transactions in Python's sqlite3, why `with connection` doesn't close it, and when to choose SQLite over Postgres; then quiz me with 5 questions."

**C.**
- <https://docs.python.org/3/library/sqlite3.html>: read "How-to guides" on placeholders and the context-manager notes, plus the `Row` section.
- <https://www.sqlite.org/whentouse.html>: when SQLite is (and isn't) appropriate.
- <https://sqlite.org/cli.html>: the `sqlite3` shell and its dot-commands.

**D.**
- "Learn How to Use SQLite Databases With Python", John Elder (Codemy.com) on the freeCodeCamp.org channel, about 1.5 h, covers creating tables, insert/select, WHERE and LIKE: <https://www.youtube.com/watch?v=byHcYRpMgI4> (title, creator and link taken from freeCodeCamp's article page, which I opened; I didn't watch the video).
- Course: I didn't verify a specific course; search "SQLite tutorial" and use the sqlitetutorial.net site (seen in a search result, not opened).
