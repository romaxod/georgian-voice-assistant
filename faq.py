"""Step 1.3: the ჯიხვი FAQ in SQLite, and lookup_faq(topic) to search it.

data/faq.json is the source of truth (easy to read and diff); data/faq.db is built from it
automatically and isn't committed. Step 1.4 gives lookup_faq to the model as a tool.

Run:  python faq.py ბარათი          search and print the matching entries as JSON
      python faq.py --build         rebuild data/faq.db from data/faq.json
"""
import argparse
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
JSON_PATH = DATA_DIR / "faq.json"
DB_PATH = DATA_DIR / "faq.db"

# Common Georgian case/plural endings. Cutting one off lets "ბარათი" also match "ბარათის", "ბარათით".
SUFFIXES = ("ების", "ებს", "ები", "ის", "ით", "ში", "ზე", "ად", "ს", "ი")
# Question words that appear in almost every entry, so they'd match everything.
STOPWORDS = {"რა", "და", "როგორ", "რომ", "თუ", "ან", "მე", "ჩემი", "არის", "როდის", "შემიძლია"}
MAX_TERMS = 5  # caps the size of the generated SQL, whatever the caller sends


def build_db() -> None:
    """(Re)create data/faq.db from data/faq.json."""
    entries = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DROP TABLE IF EXISTS faq")
        conn.execute(
            "CREATE TABLE faq (id TEXT PRIMARY KEY, topic TEXT, question TEXT, answer TEXT, keywords TEXT)"
        )
        # Placeholders, not string formatting: the values are sent separately from the SQL text.
        conn.executemany(
            "INSERT INTO faq VALUES (:id, :topic, :question, :answer, :keywords)", entries
        )
    conn.close()  # "with" commits the transaction but doesn't close the connection


def _ensure_db() -> None:
    if not DB_PATH.exists() or DB_PATH.stat().st_mtime < JSON_PATH.stat().st_mtime:
        build_db()


def _stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _words(topic: str) -> list[str]:
    words = [w.strip(".,!?;:\"'„“()-").lower() for w in topic.split()]
    words = [w for w in words if w and w not in STOPWORDS]
    return list(dict.fromkeys(words))[:MAX_TERMS]  # dedupe, keep order


def _escape_like(text: str) -> str:
    # % and _ are LIKE wildcards; escape them so a user's "%" means a literal percent sign.
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def lookup_faq(topic: str, limit: int = 3) -> list[dict]:
    """Return up to `limit` FAQ entries matching the words in `topic`, best match first.

    Each entry is a plain dict (id, topic, question, answer), so it can go straight into json.dumps.
    An empty or unmatched topic returns [].
    """
    words = _words(topic)
    if not words:
        return []
    _ensure_db()

    # Each word adds points to an entry; the entry's score is the sum. Per word:
    #   +2 the exact word is in topic or keywords (spaces around both sides = whole-word match)
    #   +2 its stem is in the topic (the entry's headline), +1 its stem is anywhere in the entry
    # Stems shorter than 3 letters skip the substring checks: "m" would match every "SIM" and "MB".
    # Only "?" placeholders go into the SQL text. The user's words travel separately in `params`.
    tags = "(' ' || topic || ' ' || keywords || ' ')"
    everything = "(topic || ' ' || question || ' ' || answer || ' ' || keywords)"
    parts, params = [], []
    for word in words:
        parts.append(f"2 * ({tags} LIKE ? ESCAPE '\\')")
        params.append(f"% {_escape_like(word)} %")
        stem = _stem(word).rstrip("-")
        if len(stem) >= 3:
            parts.append(f"2 * (topic LIKE ? ESCAPE '\\') + ({everything} LIKE ? ESCAPE '\\')")
            params += [f"%{_escape_like(stem)}%"] * 2
    sql = (
        f"SELECT id, topic, question, answer, {' + '.join(parts)} AS score FROM faq "
        f"WHERE score > 0 ORDER BY score DESC, id LIMIT ?"
    )
    params.append(limit)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["answer"]
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [{k: row[k] for k in ("id", "topic", "question", "answer")} for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the ჯიხვი FAQ.")
    parser.add_argument("topic", nargs="*", help="words to search for, e.g. ბარათი")
    parser.add_argument("--build", action="store_true", help="rebuild data/faq.db from data/faq.json")
    args = parser.parse_args()

    if args.build:
        build_db()
        print(f"built {DB_PATH} from {JSON_PATH.name}")
    if args.topic:
        print(json.dumps(lookup_faq(" ".join(args.topic)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
