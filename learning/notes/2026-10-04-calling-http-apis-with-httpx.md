# Calling a REST API directly with httpx (instead of an SDK)

Step 2.6a, `elevenlabs_api.py`. Sources opened 2026-10-04; httpx 0.28.1 installed.

## 1. What you're learning, and why it matters

**Problem: you need ElevenLabs, and there are two ways to call it.** Use its `elevenlabs` Python SDK, or send HTTP requests yourself. For two endpoints we chose raw HTTP: you see exactly what goes over the wire, you control timeouts and error messages, and you can time the first audio chunk. Knowing the raw layer also makes every SDK less magical (the OpenAI and Azure SDKs do the same underneath).

**Anatomy of a request** (all visible in `elevenlabs_api.py`):
- **Method + URL + query params:** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format=pcm_24000`. `params={...}` builds the `?` part.
- **Headers:** auth is `xi-api-key: <key>` (header names differ per vendor; OpenAI uses `Authorization: Bearer`).
- **Body:** `json={"text": ..., "model_id": ...}` serializes to JSON and sets `Content-Type: application/json`.
- **Status code** in the response. **Body** after it.

**`multipart/form-data`** (the STT upload): a body made of several parts separated by a random **boundary** string; each part has a name and optional filename and content type. Needed because one request carries both a binary file and text fields. In httpx: `files={"file": (name, fileobj, "audio/wav")}` for the file and `data={...}` for the text fields. Form fields are strings, so `"false"` not `False`; a list value is sent as the **same field repeated** (`keyterms` once per term).

**Streaming.** A normal call waits for the whole body. With `httpx.stream(...)` used as a **context manager** (`with ... as response`), headers arrive first and `response.iter_bytes()` yields chunks as the server sends them (HTTP/1.1 **chunked transfer encoding**: the server sends the body in pieces without knowing the total length). The `/stream` TTS endpoint sends audio while still generating, so the first chunk arrives long before the last. That gap is "time to first audio" ([latency note](2026-10-02-how-speech-services-work.md)). The `with` closes the connection even if you raise inside.
- **Why `response.read()` before reading an error body:** in streaming mode the body is not loaded. `response.json()` or `.text` on it would raise `ResponseNotRead`. The code calls `read()` only on the error path.

**Timeouts.** `httpx.Timeout(20.0, connect=5.0)`: 20 s for each **read** (wait for the next chunk), write and pool; only 5 s for **connect** (establishing the TCP connection). A dead host should fail in 5 s, a slow-but-alive generation may take longer. It is a per-operation limit, not a total deadline. Defaults in httpx are 5 s each.

**Two kinds of failure, handled differently:**
- **Exceptions** (no response at all): `httpx.HTTPError` is the base; under it `TimeoutException` (ConnectTimeout, ReadTimeout...) and `NetworkError` such as `ConnectError`. Our `network_error()` maps them to a `SpeechError`.
- **HTTP status codes** (the server answered "no"): a 4xx/5xx is **not** an exception by default. You check `response.status_code`, or call `response.raise_for_status()` which raises `HTTPStatusError`. We check the code ourselves so we can read the body first.

| Code | Meaning here | Retry? |
|---|---|---|
| 401 | key rejected / no credit | no |
| 402 | needs a paid plan. Seen for real on the free plan: `payment_required: Free users cannot use library voices via the API` (premade voices work) | no |
| 404 | wrong voice id | no |
| 422 | a field failed validation | no |
| 429 | too many requests | yes, later |
| 5xx | server trouble | yes |

**Reading error bodies.** ElevenLabs returns `{"detail": {"status": ..., "message": ...}}`, but for a 422 it returns FastAPI-style `{"detail": [{"loc": [...], "msg": ...}]}`, one item per bad field (`loc` says which). `http_error()` handles both shapes and falls back to `response.text` if the body isn't JSON.

**SDK vs raw HTTP:**

| | SDK | raw httpx |
|---|---|---|
| Typed models, autocompletion | yes | no |
| Built-in retries, pagination, new endpoints | yes | you write them |
| Transparency, fewer dependencies | less | more |
| Risk | SDK lags the API or hides behavior | you must keep up with API changes |

## 2. In this repo

- `elevenlabs_api.synthesize()`: streaming POST, times the first chunk, joins bytes, wraps in WAV ([raw PCM vs WAV](2026-10-03-audio-on-linux-and-wsl.md)).
- `elevenlabs_api.transcribe()`: multipart POST to `/v1/speech-to-text` with `model_id=scribe_v2`, `language_code=kat`, `tag_audio_events=false`, repeated `keyterms`.
- I checked the multipart encoding offline: building `httpx.Request("POST", url, data={..., "keyterms": ["SIM","eSIM"]}, files=...)` and calling `.read()` shows `name="keyterms"` appearing twice, once per term.
- **Where `httpx` comes from:** not from `openai`. `pip show openai` says it requires `httpx2` (a different package, 2.13.1). `import httpx` works because `langchain-core` and `langgraph-sdk` need `httpx` 0.28.1; both are pinned in `requirements.txt`. (The module docstring said "dependency of openai" and was fixed on 2026-10-06.) See [dependencies](2026-10-02-dependencies-and-pinning.md): importing a package you didn't ask for directly is fragile, so keep the direct `httpx==0.28.1` pin.
- ElevenLabs' TTS default `model_id` is `eleven_multilingual_v2`, which has no Georgian. That's why the code always sends `model_id` explicitly.

## 3. How the pieces fit

`providers.py` calls `elevenlabs_api.synthesize/transcribe` -> httpx builds the request -> ElevenLabs answers with a status + bytes/JSON -> status or exception becomes a `SpeechError(retryable=...)` -> `WithFallback` decides what to do ([note](2026-10-04-swappable-providers-and-fallbacks.md)).

## 4. Related tools

- **`requests`:** older, sync only; httpx has almost the same API plus async and HTTP/2. Not used because httpx is already installed.
- **`aiohttp`:** async only. Our speech calls are sync and run in a thread/`to_thread`.
- **`elevenlabs` SDK:** the alternative discussed above.
- **`curl`:** the reference for "what exactly is sent"; add `-v`.
- **httpx2:** the OpenAI SDK's new dependency. Not explored.

## 5. Hands-on exercises

1. Run `.venv/bin/python elevenlabs_api.py tts "გამარჯობა"` with a real key. Check: a WAV file and "first audio X s, done Y s".
2. Repeat the same call with `curl -v -X POST "https://api.elevenlabs.io/v1/text-to-speech/$ELEVENLABS_VOICE_ID/stream?output_format=pcm_24000" -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" -d '{"text":"hi","model_id":"eleven_v4_turbo"}' -o /tmp/x.pcm`. Check: you can match each header and the status line to the httpx call. (Don't paste your key anywhere else.)
3. Trigger a 422 on purpose: in a scratch script, post `json={"model_id": "eleven_v4_turbo"}` (no `text`). Check: status 422 and a `detail` list whose `loc` ends in `"text"`.
4. In a scratch copy, replace the status check with `response.raise_for_status()` inside the `with`. Check: for a 401 you get `httpx.HTTPStatusError` with the status in the message but nothing about `invalid_api_key`, and (streaming) calling `response.json()` first raises `ResponseNotRead`.
5. Set `ELEVENLABS_VOICE_ID` to nonsense. Check: 404 with a hint, and `retryable=False`.
6. Run `httpx.get("http://127.0.0.1:9", timeout=httpx.Timeout(5.0, connect=1.0))` in a REPL. Check: `ConnectError` immediately; print `type(e).__mro__` and find `HTTPError`.

## 6. Self-check

1. Why is a 404 response not an exception, but a refused connection is?
2. Why `response.read()` before the error body?
3. What do `connect=5.0` and `20.0` limit differently?
4. How do you send a file plus a list of strings in one request?
5. Which of 401/402/404/422/429/503 are worth retrying?
6. Name one reason to use an SDK and one to avoid it.

<details><summary>Answers</summary>

1. The server answered; HTTP's job is done and the status is data. A refused connection never produced a response.
2. A streamed body isn't loaded until you read it.
3. Connect: time to establish the connection. 20 s: how long to wait for each chunk of data.
4. `files={"file": (name, fileobj, type)}` plus `data={"field": ["a","b"]}`; httpx encodes multipart/form-data with the field repeated.
5. 429 (after a delay) and 503/5xx. Not 401/402/404/422: they will fail identically.
6. Use: typed models, retries, maintained against API changes. Avoid: hidden behavior, extra dependency, can't time the first chunk.

</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-6 | 45 min |
| B. Another AI tutor | HTTP basics, multipart | 30 min |
| C. Primary docs | Exact httpx behavior, API fields | 1 hr |
| D. Video | Not verified | - |

**A. Prompt:**
> Walk me through learning/notes/2026-10-04-calling-http-apis-with-httpx.md. Do exercises 2-6 one at a time, showing real output, and have me explain each before moving on. Then quiz me on the self-check.

**B. NotebookLM loaded with the C links, or ChatGPT/Gemini.** Prompt:
> Using only these sources, explain how an HTTP POST with JSON and a multipart/form-data upload look on the wire, how httpx streams a response, the difference between httpx exceptions and HTTP status codes, and which status codes are retryable. Quiz me with 5 questions. Sources: https://www.python-httpx.org/quickstart/, https://www.python-httpx.org/advanced/timeouts/, https://www.python-httpx.org/exceptions/, https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status, https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type, https://elevenlabs.io/docs/api-reference/text-to-speech/stream, https://elevenlabs.io/docs/api-reference/speech-to-text/convert

**C. Docs (opened 2026-10-04):**
- [httpx QuickStart](https://www.python-httpx.org/quickstart/): "Sending Form Encoded Data" (lists as repeated keys), "Sending Multipart File Uploads", "Streaming Responses", "Exceptions", "Timeouts".
- [httpx Timeouts](https://www.python-httpx.org/advanced/timeouts/): connect/read/write/pool.
- [httpx Exceptions](https://www.python-httpx.org/exceptions/): the hierarchy (`HTTPError` > `RequestError` > `TransportError` > `TimeoutException`/`NetworkError`; `HTTPStatusError` separate).
- [MDN HTTP status codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status): 401, 402, 404, 422, 429, 503.
- [MDN Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type): the multipart/form-data and `boundary` section.
- [ElevenLabs: Stream speech](https://elevenlabs.io/docs/api-reference/text-to-speech/stream): endpoint, `xi-api-key`, `output_format` values (`pcm_24000`), body fields.
- [ElevenLabs: Speech to text](https://elevenlabs.io/docs/api-reference/speech-to-text/convert): multipart fields, keyterm limits (1000, under 50 characters, at most 5 words).

**D. Video:** my search returned only articles for httpx, so I can't confirm a video. Search terms: "httpx python tutorial", "HTTP multipart form data explained", "HTTP status codes explained".
