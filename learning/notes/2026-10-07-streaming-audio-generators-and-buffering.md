# Streaming audio playback: generators, buffering and underruns

**Written:** 2026-10-07. Python behaviour checked with a throwaway script and the Python docs; PulseAudio attribute meanings from search-result excerpts of the official `pa_buffer_attr` docs (the page itself returned 403 to me).

## 1. What you're learning, and why it matters

**Problem.** In 2.6a the loop played a reply only after all of it was downloaded. One 140-character ElevenLabs reply took 15.1 s to generate, so 22.8 s passed before the caller heard anything. Streaming plays the first chunk while the rest is still coming. That needs three ideas: generators (hand out data as it arrives), backpressure (don't read faster than you play) and a small buffer (survive uneven arrival).

**Generators**
- A function with `yield` returns a **generator** (an iterator) when called; its body does **not** run yet. Execution starts at the first `next()` (Python reference, yield expressions). So `elevenlabs_api.stream()` sends no HTTP request, and reads no `.env` settings, until someone asks for the first chunk.
- At each `yield` the function's state is frozen and resumed later (PEP 255).
- `yield from it` re-yields everything from `it`; `close()` and exceptions are forwarded to it (PEP 380).
- A `with` block around a `yield` stays open while the consumer is mid-iteration, and cleans up when the generator finishes, raises, or is closed. I checked: `next(g)` printed the first chunk, `g.close()` ran the `with` exit ("closed"). `close()` raises `GeneratorExit` at the paused `yield`; that is how a half-read HTTP connection gets closed.
- An exception raised inside a generator surfaces in the consumer at the `next()` (the `for` line), which is why `play_stream` can catch a `SpeechError` from the TTS.
- Hints: `Iterator[bytes]` (what `stream` returns) vs `Iterable[bytes]` (what `play_stream` accepts: anything you can loop over, including a list). Both from `collections.abc`.

**Fallback with streams.** `WithFallback.stream` falls back to Azure only if the primary fails *before its first chunk*. After the caller heard half a sentence in the clone voice, replaying the whole reply in Azure's voice is worse than an honest error, so it re-raises. Contrast with whole-file fallback in [swappable providers](2026-10-04-swappable-providers-and-fallbacks.md): there nothing has been heard yet, so switching is free.

**Backpressure.** Producer (HTTP stream) and consumer (speaker) run at different speeds. `PaSimple.write()` blocks while PulseAudio's buffer is full, so the loop reads the network only as fast as the speaker plays. Consequence: an "all audio received after X s" number is meaningless during playback (it just equals the reply length), so it was removed from `play_stream`'s stats.

**Buffering and underruns**
- An **underrun** is the speaker needing audio that hasn't arrived. PulseAudio then pauses and waits until `prebuf` bytes are queued again; the caller hears a gap.
- `tlength` = the target fill level the server tries to keep (we set 0.5 s). `prebuf` = audio needed before playback starts or resumes (0.2 s). `-1` means "server chooses" (about 2 s, with prebuf equal to tlength), which would delay the first sound.
- Trade-off: small buffer = early start but more stutter risk; big buffer = fewer gaps but later start. This is a **jitter buffer**. Production VoIP/WebRTC uses an *adaptive* one (NetEQ) that grows and shrinks with measured jitter and stretches audio slightly to catch up.
- **Whole samples.** A 16-bit sample is 2 bytes and an HTTP chunk can end between them, so a leftover byte is carried into the next chunk. `drain()` waits until the last sample has really played, before the stream is closed.

## 2. In this repo

- Files: `elevenlabs_api.py` (`stream`, `synthesize` which just collects `stream`), `providers.py` (`AzureTTS.stream`, `ElevenLabsTTS.stream`, `WithFallback.stream`), `speech.py` (`play_stream`, `wav_pcm`), `voice.py` (`speak`). Line-by-line is in `docs/code/`.
- Gap estimate in `play_stream`: before writing a chunk, `behind = (now - time playback (re)started) - seconds written since then`. If `behind > 0.05 s` the speaker had already run dry, so count a gap and reset the clock.
- Results (clone, Scribe STT + graph + clone TTS): sound 0.55-0.62 s after the reply text is ready; 3.7-5.5 s from end of question to reply start (2.6a: 22.8 s). `compare_speech.py tts` medians over 10 sentences: first audio Azure 0.46 s, ElevenLabs premade 0.54 s, clone 0.58 s; whole sentence 0.88 / 1.62 / 1.61 s. The 2.6a Free-plan figure (3.78 s) came from another day, so I don't attribute the difference to the plan.
- **Diagnosis worth copying.** One `voice.py` run had 22 gaps (6.9 s of pauses) on a 140-char reply. Instead of tuning the buffer: (a) same text with no playback, 8 times: 1.8-2.2 s for ~10 s of audio; (b) feed the player already-downloaded chunks: no false gaps, 6.6 s of audio played in 6.4 s; (c) real stream through the player, 3 times: 0 gaps; (d) full loop twice: first sound at 0.55-0.62 s, no gaps. Conclusion: intermittent slowness on ElevenLabs' side, not the player. Lesson: isolate one component at a time and repeat before "fixing".
- Break tests that passed: wrong clone ID gives `HTTP 404 voice_not_found` and Azure for the rest of the session; a fake provider failing after one chunk raises, no Azure replay, `used` stays the primary; failing before audio falls back to Azure for that turn; `ELEVENLABS_VOICE=roman` gives `unknown ELEVENLABS_VOICE 'roman'; use one of ready, clone`.

## 3. How the pieces fit together

```
ElevenLabs --HTTP chunks--> stream() generator --> play_stream loop --write()--> PulseAudio buffer --> speaker
                 (lazy: starts at first next())     (blocks when buffer full = backpressure)
```

## 4. Related tools

- **WebSocket TTS input streaming:** ElevenLabs' `stream-input` endpoint takes text in pieces (`chunk_length_schedule` default `[120, 160, 250, 290]` characters before each audio chunk, `flush` to force output), so LLM tokens can be sent as they are generated. We send the full reply text; the saving would be overlapping LLM and TTS.
- **Sentence-level chunking:** synthesize sentence 1 while the LLM writes sentence 2.
- **Adaptive jitter buffers:** WebRTC NetEQ (see C). Our fixed 0.5 s/0.2 s is the simple version.
- `sounddevice` callbacks or `asyncio` queues would replace the blocking `write()`; not needed for one stream.

## 5. Hands-on exercises

1. In a scratch copy of the call, add `print("request")` as the first line of `stream()`'s body, create `g = stream("გამარჯობა")`, print, then `next(g)`. Check: "request" appears only at `next`.
2. Write a generator that yields 0.1 s of silence-free tone chunks with `time.sleep(0.15)` between them (slower than real time) and pass it to `speech.play_stream(gen, 24000)`. Check: `gaps` is non-empty.
3. Set `PREBUFFER_SECONDS` to 0, then 1.5 in `speech.py` (revert afterwards) and run exercise 2 plus a real `voice.py` reply. Check: compare `first_audio` and `gaps`; 1.5 delays the first sound, 0 stutters more.
4. Wrap a generator in `try/finally: print("closed")`, `next()` once, then `del g` or `g.close()`. Check: "closed" prints.
5. Make a generator that raises after two yields; consume with `for` inside `try/except`. Check: the exception arrives at the loop line.
6. Run `python compare_speech.py tts` and read first audio vs whole sentence. Check: which provider wins each, and why that matters for perceived speed.

## 6. Self-check

1. When does a generator function's body start running?
2. Why does `WithFallback.stream` not fall back after the first chunk?
3. Why can't we report "all audio received after X s"?
4. What do `tlength` and `prebuf` control, and what happens on an underrun?
5. Why carry a leftover byte between chunks?
6. Why were three isolated tests run before touching the player?

<details><summary>Answers</summary>

1. At the first `next()`/loop iteration, not at the call.
2. The caller already heard part of the reply; replaying all of it in another voice is worse than an error.
3. `write()` blocks when the buffer is full, so the stream is read at playback speed; the last chunk always arrives near the end.
4. Target buffer fill and the amount needed before (re)starting playback. On underrun playback pauses until `prebuf` is refilled, which the listener hears as a gap.
5. Chunks can end mid-sample; PulseAudio needs whole 2-byte samples.
6. To locate the slowness: no playback (provider speed), pre-downloaded chunks (player), real stream (both). Only one component changes at a time.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-3 on the real code | 45 min |
| B. Another AI tutor | Generators and jitter buffers explained from the links | 45 min |
| C. Primary docs | Exact generator semantics, buffer attributes | 1 hr |
| D. Video / talk | Seeing generators used as pipelines | 15 min to 3 hr |

**A. Prompt:**
> Read learning/notes/2026-10-07-streaming-audio-generators-and-buffering.md. Walk me through exercises 1, 2 and 3 one at a time with the real code (revert any edit afterwards), showing output, then ask me the self-check questions.

**B. Tool:** NotebookLM with the C links, or ChatGPT/Gemini. Prompt:
> Using only these sources, teach me how Python generators work (laziness, yield from, close) and how a jitter buffer and PulseAudio prebuf/tlength trade latency against glitches. Finish with 5 quiz questions. Sources: https://docs.python.org/3/reference/expressions.html#yield-expressions, https://peps.python.org/pep-0255/, https://peps.python.org/pep-0380/, https://webrtc.googlesource.com/src/+/HEAD/modules/audio_coding/neteq/g3doc/index.md, https://www.dabeaz.com/generators

**C. Reading:**
- [Yield expressions (Python reference)](https://docs.python.org/3/reference/expressions.html#yield-expressions): generator methods, `close()`, `GeneratorExit`. Opened.
- [PEP 255](https://peps.python.org/pep-0255/): why generators exist, frozen local state. Opened.
- [PEP 380](https://peps.python.org/pep-0380/): `yield from`. Opened.
- PulseAudio [`pa_buffer_attr`](https://distributions.freedesktop.org/software/pulseaudio/doxygen/structpa__buffer__attr.html): `tlength`, `prebuf`, `minreq`, `maxlength`. Seen in search results only, not opened (the freedesktop.org page gave 403).
- [WebRTC NetEQ overview](https://webrtc.googlesource.com/src/+/HEAD/modules/audio_coding/neteq/g3doc/index.md): adaptive jitter buffer, concealment, time-stretching. Opened.
- [ElevenLabs WebSocket TTS](https://elevenlabs.io/docs/api-reference/text-to-speech/v-1-text-to-speech-voice-id-stream-input): partial-text input. Opened.
- Related: [audio on Linux/WSL](2026-10-03-audio-on-linux-and-wsl.md), [latency budget](2026-10-03-voice-latency-and-tts-normalization.md), [httpx streaming](2026-10-04-calling-http-apis-with-httpx.md).

**D. Video / talk:**
- David Beazley, "Generator Tricks for Systems Programmers" (PyCon 2008 tutorial, updated for Python 3.7): slides and code at https://www.dabeaz.com/generators . Confirmed in search results; this is slides, not a video.
- David Beazley, "Generators: The Final Frontier" (PyCon 2014, 3 h): https://dabeaz.com/finalgenerator/index.html . Slides confirmed; no recording link found.
- Corey Schafer, "Python Tutorial: Generators - How to use them and the benefits you receive" (about 11 min): title and channel confirmed in a search result, but I could not confirm the URL; search that title on YouTube.
- I found no verified video on jitter buffers; search "jitter buffer WebRTC explained" and check the source.
