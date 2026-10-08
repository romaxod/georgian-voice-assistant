#!/usr/bin/env python3
"""Stop-hook worker: extract the last turn of a session and append its decisions to DECISIONS.md.

Called by log-decisions.sh with the hook's JSON on stdin. Uses only the standard library,
so it runs with any python3, not just the project venv.
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))
LOG_FILE = PROJECT / "DECISIONS.md"
STATE_DIR = PROJECT / ".claude" / "decision-logger"
AGENT_FILE = PROJECT / ".claude" / "agents" / "decision-logger.md"
MAX_EXCERPT = 40_000  # characters sent to the model per turn


def log_run(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "runs.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f" …[+{len(text) - limit} chars]"


def is_human_prompt(entry: dict) -> bool:
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and any(b.get("type") == "text" for b in content) \
        and not any(b.get("type") == "tool_result" for b in content)


def summarize_tool_use(block: dict) -> str:
    name, inp = block.get("name", "?"), block.get("input", {}) or {}
    if name in ("Write",):
        return f"[Write {inp.get('file_path')}]\n{clip(str(inp.get('content', '')), 2500)}"
    if name in ("Edit",):
        return (f"[Edit {inp.get('file_path')}]\n- old: {clip(str(inp.get('old_string', '')), 800)}\n"
                f"+ new: {clip(str(inp.get('new_string', '')), 1500)}")
    if name == "Bash":
        return f"[Bash: {inp.get('description', '')}]\n{clip(str(inp.get('command', '')), 1500)}"
    if name in ("Agent", "SendMessage"):
        return f"[{name}: {inp.get('description') or inp.get('summary', '')}]\n" \
               f"{clip(str(inp.get('prompt') or inp.get('message', '')), 2000)}"
    return f"[{name}] {clip(json.dumps(inp, ensure_ascii=False), 400)}"


def last_turn(transcript: Path) -> str:
    entries = []
    with open(transcript, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    start = max((i for i, e in enumerate(entries) if is_human_prompt(e)), default=None)
    if start is None:
        return ""
    parts = []
    for e in entries[start:]:
        content = e.get("message", {}).get("content")
        role = e.get("type")
        if isinstance(content, str):
            parts.append(f"## {role}\n{clip(content, 4000)}")
            continue
        if not isinstance(content, list):
            continue
        for b in content:
            t = b.get("type")
            if t == "text":
                parts.append(f"## {role}\n{clip(b.get('text', ''), 6000)}")
            elif t == "tool_use":
                parts.append(summarize_tool_use(b))
            elif t == "tool_result":
                res = b.get("content")
                res = " ".join(x.get("text", "") for x in res if isinstance(x, dict)) if isinstance(res, list) else str(res)
                parts.append(f"[result] {clip(res, 300)}")
    return clip("\n\n".join(parts), MAX_EXCERPT)


def recent_titles(n: int = 40) -> str:
    if not LOG_FILE.exists():
        return "(none yet)"
    titles = re.findall(r"^### .+$", LOG_FILE.read_text(encoding="utf-8"), flags=re.M)
    return "\n".join(titles[-n:]) or "(none yet)"


def agent_instructions() -> str:
    text = AGENT_FILE.read_text(encoding="utf-8")
    return re.sub(r"\A---.*?---\s*", "", text, count=1, flags=re.S) + private_rules()  # strip frontmatter


def private_rules() -> str:
    """The privacy section of private/CONTEXT.md (gitignored, local only), if it exists.
    The agent runs without tools, so it can't read the file itself; its rules go into the prompt."""
    path = PROJECT / "private" / "CONTEXT.md"
    if not path.is_file():
        return ""
    m = re.search(r"^## Privacy section.*?(?=^## |\Z)", path.read_text(encoding="utf-8"), flags=re.M | re.S)
    return f"\n\n---\nPRIVATE RULES (local only; follow them, never quote them):\n{m.group(0)}" if m else ""


def main() -> None:
    if (STATE_DIR / "disabled").exists():
        log_run("skip: disabled")
        return
    hook = json.load(sys.stdin)
    transcript = Path(hook.get("transcript_path", ""))
    if not transcript.is_file():
        log_run(f"skip: no transcript ({transcript})")
        return
    excerpt = last_turn(transcript)
    if "## assistant" not in excerpt:
        log_run("skip: no assistant output in last turn")
        return

    prompt = (f"{agent_instructions()}\n\n---\nToday's date: {datetime.now():%Y-%m-%d}\n\n"
              f"Recent DECISIONS.md titles (avoid duplicates):\n{recent_titles()}\n\n"
              f"---\nTURN EXCERPT (session {hook.get('session_id', '?')}):\n\n{excerpt}\n\n"
              "---\nReturn NONE or the entries now.")

    env = {**os.environ, "DECISION_LOGGER_CHILD": "1"}
    with tempfile.TemporaryDirectory() as tmp:  # run outside the repo so project CLAUDE.md isn't loaded
        proc = subprocess.run(
            ["claude", "-p", "--model", "sonnet", "--tools", "",
             "--settings", '{"disableAllHooks": true}', "--no-session-persistence"],
            input=prompt, capture_output=True, text=True, cwd=tmp, env=env, timeout=280,
        )
    out = proc.stdout.strip()
    if proc.returncode != 0:
        log_run(f"error: claude exited {proc.returncode}: {clip(proc.stderr.strip(), 500)}")
        return
    if out == "NONE" or not out:
        log_run("ok: NONE")
        return
    first = out.find("### ")
    if first == -1:
        log_run(f"error: unexpected output: {clip(out, 300)}")
        return
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # parallel turns append one at a time
        f.write("\n" + out[first:].rstrip() + "\n")
        fcntl.flock(f, fcntl.LOCK_UN)
    log_run(f"ok: {out.count('### ')} entr{'y' if out.count('### ') == 1 else 'ies'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break the session because of logging
        log_run(f"error: {type(exc).__name__}: {exc}")
