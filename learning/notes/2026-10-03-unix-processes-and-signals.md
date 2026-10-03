# Unix processes and signals (as used in the break tests)

*(short note)* Date: 2026-10-03. Commands run in this WSL shell today; man pages `signal(7)`, `credentials(7)`, `pgrep(1)` and the Python `signal` docs opened. Related: [async note](2026-10-03-python-async-await.md), [MCP client side](2026-10-03-mcp-servers.md), [CLI basics](2026-10-03-python-cli-basics.md).

## 1. What and why

**Problem.** The 2.4 break tests had to make a server process die or hang on purpose, and stop it cleanly on Ctrl-C. That needs the process vocabulary.

- **Signal:** a small message the kernel delivers to a process. A process may catch most signals and run its own handler.
  - `SIGINT` (2): Ctrl-C. Python turns it into `KeyboardInterrupt`; catchable.
  - `SIGTERM` (15): "please exit", the default of `kill <pid>`; catchable, so the program can clean up.
  - `SIGKILL` (9): `kill -9`. **Cannot be caught, blocked or ignored** (`signal(7)`); the process just disappears, no cleanup. Our test: client saw `Connection closed`.
  - `SIGSTOP` (19): freezes the process, also uncatchable; `SIGCONT` (18) resumes it. A stopped process holds its pipes open but never answers, so it simulates a **hung** server, which `kill` doesn't. Our test: client timed out after 5 s, and after `SIGCONT` the same session worked.
- **PID and finding it:** `pgrep -af mcp_server.py` lists PIDs plus full command lines (`-f` matches the whole command line, not just the program name; `-a` prints it). On Linux each process also has `/proc/<pid>/cmdline` (arguments separated by NUL bytes: `tr '\0' ' ' < /proc/<pid>/cmdline`). The test helper found the server's PID by scanning `/proc/*/cmdline`.
- **`ps -o pid,pgid,sid,stat,cmd -p <pid>`:** `STAT` shows `T` for stopped, `S` sleeping, `Z` zombie.
- **Process group / session** (`credentials(7)`): a *process group* ("job") is processes sharing a group id; a *session* groups jobs, usually one terminal. When you press Ctrl-C the terminal sends SIGINT to every process in the **foreground** job only. The MCP SDK starts the server with `start_new_session=True` (its own session), so a terminal Ctrl-C reaches only `graph.py`; `graph.py` then stops the server itself on the way out. Without that, both would get SIGINT at once.
- **Exit codes:** `128 + signal number` when killed by a signal: 137 = SIGKILL (9) (measured). The 144 in the gotcha below would be 128 + 16; I did not work out which signal the tool harness reports that way, so treat 144 as "the shell was killed".

## 2. In this repo

- Break test 1: `kill -9 <server pid>` -> next call `MCPError(-32000, 'Connection closed')`.
- Break test 2: `kill -STOP <pid>` -> `MCPError(-32001, ... timed out)` after exactly 5 s. Restart was slow (7.0 s) because the SDK's shutdown is: close stdin, wait, SIGTERM, then SIGKILL after `FORCE_KILL_TIMEOUT = 2.0` s (`mcp/client/stdio.py`), and a stopped process doesn't act on SIGTERM until continued.
- **Gotcha hit today:** `pkill -f mcp_server.py` inside the test shell killed *that shell* (exit code 144), because the shell's own command line contained the text `mcp_server.py` (the whole test script was passed as `bash -c "..."`). `pgrep`/`pkill` exclude only themselves, not their parent shell. I reproduced it again while writing this note: a `pgrep -af "sleep 300"` listed the running shell, and a later `pkill -f` pattern killed it. Fixes: match with a bracket trick, `pkill -f "[m]cp_server.py"` (the regex `[m]cp_server.py` matches `mcp_server.py` but not its own literal text), or look up PIDs by `/proc/<pid>/cmdline` `argv[0]` or by `pgrep -P <parent>`, or keep the PID from `$!` when you start the process.
- **Test driver pattern:** to drive an interactive program from a script, start it with `subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, text=True)`, run a **reader thread** that does `for line in proc.stdout: queue.put(line)`, and in the main thread `queue.get(timeout=...)`. Why: reading a pipe blocks, and a blocked read would hide a hang; the thread + queue turns "blocked" into a timeout you can test.

## 3. Exercises

1. `sleep 300 & P=$!; kill -STOP $P; ps -o stat= -p $P; kill -CONT $P; ps -o stat= -p $P`. Check (measured): `T`, then `S`. Then `kill -9 $P; wait $P; echo $?` prints `137`.
2. `tr '\0' ' ' < /proc/$P/cmdline` (before killing it). Check: prints `sleep 300`.
3. `.venv/bin/python -c "import signal,os,time; signal.signal(signal.SIGTERM, lambda *a: print('caught TERM')); os.kill(os.getpid(), 15); time.sleep(.1)"` then the same with `SIGKILL`: `signal.signal(signal.SIGKILL, ...)` raises `OSError: [Errno 22] Invalid argument`. Check: SIGKILL cannot get a handler.
4. Start `.venv/bin/python graph.py`, then in a second terminal `ps -o pid,pgid,sid,cmd -C python`. Check: the server has a different `sid` from `graph.py`.

## 4. Sources (opened 2026-10-03)

- `signal(7)`: https://man7.org/linux/man-pages/man7/signal.7.html ("SIGKILL and SIGSTOP cannot be caught, blocked, or ignored")
- `credentials(7)`, process groups, sessions, Ctrl-C going to the foreground job: https://man7.org/linux/man-pages/man7/credentials.7.html
- `pgrep(1)`, `-f`, `-a`, "never report itself": https://man7.org/linux/man-pages/man1/pgrep.1.html
- Python `signal` module (handlers run in the main thread, `KeyboardInterrupt` default for SIGINT): https://docs.python.org/3/library/signal.html
- `kill(1)`: https://man7.org/linux/man-pages/man1/kill.1.html (not opened; the flags I used were tested above). I did not find a tutorial I could open and verify, so the man pages are the sources.
