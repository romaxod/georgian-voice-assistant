# Swappable providers and graceful degradation: interfaces, strategy, fallback, circuit breaker

Step 2.6a. Sources opened 2026-10-04 (see section 7).

## 1. What you're learning, and why it matters

**Problem 1: the voice loop must not care which company speaks.** If `voice.py` called `speech.synthesize()` (Azure) directly, trying ElevenLabs would mean editing the loop. Worse, if ElevenLabs is down mid-demo, the assistant is silent.

- **Interface:** a promise about method names and arguments. Here: `TTS.synthesize(text, timing) -> WAV bytes` and `STT.transcribe(path) -> str`. Both raise `SpeechError`.
- **Strategy pattern:** put each interchangeable algorithm (Azure TTS, ElevenLabs TTS) in its own class behind one interface, and let the caller hold "a TTS" without knowing which. Adding a third provider means one new class; `voice.py` doesn't change. This is also **dependency on abstractions**: `voice.py` imports `make_tts()` and `Provider`, never `elevenlabs_api`.
- **Factory function:** `make_tts()` / `make_stt()` read `TTS_PROVIDER` / `STT_PROVIDER` (or `--tts` / `--stt`) and build the right object. The `if name == ...` lives in one place.

**Problem 2: interface choices in Python.** Four ways to say "these classes look alike":

| Way | How | Check happens |
|---|---|---|
| Duck typing | nothing declared; just have `synthesize()` | at call time |
| Base class (`Provider`, used here) | `class AzureTTS(Provider)`; shared code lives in the base | never for the methods (see below) |
| `abc.ABC` + `@abstractmethod` | base class that refuses to be instantiated if a method is missing | at instantiation |
| `typing.Protocol` | declare the shape; any class with those methods matches, no inheritance | by a type checker (mypy), not at runtime |

Why a plain base class here: the four classes share real code (`name`, and the `used` property that `WithFallback` overrides). Honest caveat: `Provider` doesn't declare `synthesize`/`transcribe`, so the call works by duck typing and a type checker would complain about `list[Provider]` in `compare_speech.py`. A `Protocol` per interface (`TTS`, `STT`) is the cleaner next step.

**Problem 3: what to do when a provider fails.** Three different tools, often confused:

- **Retry:** call again, usually after a delay. Right for **transient** faults (overload, timeout).
- **Fallback:** call a *different* provider for the same task. Right when the primary may be down for a while.
- **Circuit breaker:** after repeated failures, **stop calling** the primary for a while, so every request doesn't wait for a timeout. States: **closed** (calls go through), **open** (calls fail fast), **half-open** (after a cooldown, let a trial call through; success closes, failure reopens).

**Retryable vs not.** Same idea as `FaqToolError(retryable)` in step 2.4 (see [failure handling](2026-10-03-failure-handling-and-guardrails.md) and the retry-policy paragraph in [MCP](2026-10-03-mcp-servers.md)): the error carries a flag saying whether trying again can help. A missing key, 401, 402, 404, 422 won't fix themselves. 429, 5xx, timeouts and connection errors might.

## 2. In this repo

- `providers.py`: `Provider` base (`name`, `used`), `AzureTTS`, `ElevenLabsTTS`, `AzureSTT`, `ScribeSTT`, `WithFallback(primary, backup, kind)`, `make_tts()`, `make_stt()`.
- `SpeechError(message, retryable=True)` in `speech.py`. `WithFallback._call` catches it, sets `primary_off = not e.retryable`, prints a line, and runs the same call on Azure.
- This is a **simplified circuit breaker**: it has "closed" and a permanent "open" (`primary_off`), but **no half-open**. Retryable failures only skip the primary for that one turn (no counter, no cooldown).

Real output from the break tests:

```
[stt] scribe_v2 + 18 keyterms: ELEVENLABS_API_KEY is not set in .env (SETUP.md §4)
[stt] using azure for the rest of the session          <- no key: retryable=False
(HTTP 401: invalid_api_key: Invalid API key)           <- fake key, then Azure
[tts] using azure ka-GE-GiorgiNeural for this turn     <- connection refused, on both turns; primary_off=False
```

Choices and reasons:
- **Azure is the backup**: it's what the pipeline was built and tested on (1.5, 2.5), and the F0 tier is free so it can't run out of credit mid-demo.
- **`compare_speech.py` calls providers directly, not through `WithFallback`.** A fallback turns "ElevenLabs failed" into "Azure answered", so the table would score Azure twice and hide the failure. In an eval, failures must show as failures. Rule: *fallbacks belong in production paths, never inside measurements.*
- `WithFallback.synthesize` calls `timing.clear()` so a first-audio time from a half-finished primary isn't reported for the backup.
- If the backup also fails, its error propagates: there's nothing left to fall back to.

## 3. How the pieces fit

```
voice.py --> Provider (TTS or STT) --+-- AzureTTS / AzureSTT
                                     +-- WithFallback --> primary (ElevenLabsTTS / ScribeSTT)
                                                     \--> backup  (Azure*)   [after SpeechError]
```

`make_*()` builds the object; `voice.py` only calls `.synthesize()` / `.transcribe()` and prints `.used` (which provider really answered).

## 4. Related tools

- **`tenacity`, `backoff`:** Python retry libraries (exponential backoff, jitter). Not used: we want to fall back immediately, not make a spoken reply wait.
- **`pybreaker`, Resilience4j (Java), Polly (.NET):** real circuit-breaker libraries with half-open states and thresholds. Too heavy for one fallback.
- **LiteLLM / LangChain `with_fallbacks()`:** the same pattern for LLM calls. Our LLM calls aren't wrapped yet.
- **Service meshes / load balancers:** do breaking at the infrastructure level in large systems.

## 5. Hands-on exercises

1. Read `WithFallback._call`. With no key (`ELEVENLABS_API_KEY=` empty), run `python voice.py --stt elevenlabs` and say one sentence. Check: the "[stt] ... for the rest of the session" line, then Azure answers every later turn without trying Scribe again.
2. Set `ELEVENLABS_API_KEY=fake` for one run (`ELEVENLABS_API_KEY=fake python voice.py --stt elevenlabs`). Check: "HTTP 401", then Azure.
3. Write a throwaway test (not in the repo) with a class `Boom(Provider)` whose `transcribe` always raises `SpeechError("x", retryable=True)` and a `Fine` provider that returns "ok". Wrap them in `WithFallback`, call twice. Check: `used` is `Fine`'s name both times, and `primary_off` stays `False`. Repeat with `retryable=False`: check `primary_off` becomes `True` and `Boom` is not called the second time (add a counter).
4. Add a half-open state: record `opened_at = time.monotonic()` when switching off and, after 60 s, let one call try the primary again. Decide what a failure in half-open does. Check with a fake clock in a test.
5. Add a third fake provider and make `make_tts("fake")` return it, without touching `voice.py`. Check: that's the whole change.
6. Explain in two sentences why `compare_speech.py tts` exits when one provider fails instead of falling back.

## 6. Self-check

1. What do the strategy pattern and a factory each contribute here?
2. Retry vs fallback vs circuit breaker: one sentence each.
3. Which errors are `retryable=False` and why does that switch the primary off for the session?
4. What's missing compared with a real circuit breaker?
5. Why must evals not use `WithFallback`?
6. How would you make a voice assistant resilient to a provider outage?

<details><summary>Answers</summary>

1. Strategy: each provider is a class behind one interface, so the caller doesn't change when one is added. Factory: one function decides which class to build from config.
2. Retry: same call again. Fallback: a different provider for the same call. Breaker: stop calling a failing provider for a while so every request doesn't pay the timeout.
3. Missing key, 401, 402, 404, 422: the request will fail the same way next time, so retrying each turn only adds delay.
4. A failure counter/threshold and a half-open trial state (it stays off for the session).
5. It would hide failures: Azure's output would be scored under the primary's name.
6. Interface + config switch, fallback to a free/tested provider, classify errors (transient vs permanent), timeouts so a hang is a failure, fail fast when the primary is known-down (breaker), report which provider answered, test each failure mode on purpose, and degrade honestly (text on screen if no audio). Mention a retry with backoff for transient faults and monitoring of the fallback rate.

</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-5 on this code | 45 min |
| B. Another AI tutor | Pattern vocabulary, short answers | 30 min |
| C. Primary docs | Exact definitions of the three states | 1 hr |
| D. Video | Not verified (see below) | - |

**A. Prompt for a main session:**
> Walk me through learning/notes/2026-10-04-swappable-providers-and-fallbacks.md. Do exercises 1-5 one at a time (run, show output, let me explain), then quiz me on the self-check, including "how would you make a voice assistant resilient to a provider outage?"

**B. NotebookLM loaded with the C links, or ChatGPT/Gemini.** Prompt:
> Using only these sources, explain the strategy pattern, Python's duck typing vs ABC vs Protocol, and retry vs fallback vs circuit breaker (closed/open/half-open). Then quiz me with 5 questions and give a model answer for "how would you make a voice assistant resilient to a provider outage?". Sources: https://refactoring.guru/design-patterns/strategy, https://peps.python.org/pep-0544/, https://docs.python.org/3/library/abc.html, https://martinfowler.com/bliki/CircuitBreaker.html, https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker, https://learn.microsoft.com/en-us/azure/architecture/patterns/retry

**C. Docs (opened 2026-10-04):**
- [Martin Fowler, "Circuit Breaker"](https://martinfowler.com/bliki/CircuitBreaker.html): short; closed/open/half-open.
- [Azure Architecture Center, Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker): states, "types of exceptions", "accelerated circuit breaking" (a response can trip it immediately, like our non-retryable errors), and how it differs from Retry.
- [Azure Architecture Center, Retry pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry): cancel vs retry immediately vs retry after delay; idempotency.
- [refactoring.guru, Strategy](https://refactoring.guru/design-patterns/strategy): the pattern with diagrams.
- [PEP 544, Protocols](https://peps.python.org/pep-0544/) and [`typing.Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol): structural subtyping.
- [`abc` module](https://docs.python.org/3/library/abc.html): `ABC`, `@abstractmethod`.

**D. Video:** searches returned articles, not confirmable videos, so I'm not listing one. Search terms: "circuit breaker pattern explained", "ArjanCodes strategy pattern python" (a video by that title/creator was mentioned in search results but without a link I could open).
