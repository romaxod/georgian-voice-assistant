# How speech services work: STT, TTS, audio, latency and the Python SDK

Checked 2026-10-02 against Microsoft Learn pages linked below. Pipeline stages are the general industry picture; Microsoft doesn't document Azure's internals, so those parts are marked as general.

## 1. What you're learning, and why it matters

**Problem.** In step 1.5 you'll feed audio to a service and get text, then text and get audio. Knowing what happens in between explains the errors you saw (rare words wrong, voices flat) and the file formats and timing you'll hit.

**STT pipeline (general picture)**
`audio -> features -> acoustic model + language model -> text`
- **Features**: the audio is cut into ~25 ms frames and turned into numbers describing the sound's frequencies.
- **Acoustic model**: frames to likely sounds. **Language model**: which words are likely together. The decoder combines both (details and why it matters for English words in Georgian: [code-switching note](2026-10-02-code-switching-stt-tts.md)). Modern systems may merge both into one neural network, but the idea is the same.
- Output also gets **display formatting**: casing, punctuation and numbers (inverse text normalization, which the REST docs describe as turning "two hundred" into 200).

**Three ways to transcribe** ([quickstart](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-speech-to-text))
- **Real-time**: results while speech is happening; for a voice assistant. Single-shot (`recognize_once`) handles one utterance, up to about 30 s per the quickstart (the how-to page says 15 s; treat it as "short").
- **Fast transcription**: a REST call for a finished audio file, much faster than real time; supports language ID and diarization. Georgian supports it, and `italynorth` offers it (SETUP.md §2). The quota table lists F0 as "Not applicable" for it, so test on F0 before planning around it.
- **Batch**: asynchronous queue for many or long files.
- **Interim vs final results**: while you speak, `recognizing` events give partial guesses that can change; `recognized` gives the finished segment. The REST short-audio API gives final results only.
- **Silence segmentation**: the service decides an utterance ended after silence. The SDK property `Speech_SegmentationSilenceTimeoutMs` (100-5000 ms, default 500) controls it: higher means longer phrases, lower means earlier breaks. `InitialSilenceTimeoutMs` is how long it waits for you to start before returning "no match". Push-to-talk (BUILD_PLAN 2.5) sidesteps most of this.

**TTS pipeline (general picture)**
`text -> text normalization -> grapheme-to-phoneme -> prosody -> neural vocoder -> audio`
- **Normalization**: "25" or "10/5" become words. **G2P**: letters to sounds (why Latin words break a Georgian voice, see the other note). **Prosody**: pitch, speed, pauses and stress per phrase. **Neural vocoder**: a network that turns the planned sounds into a waveform.
- **Voices**: Georgian has only two *standard neural* voices, `ka-GE-EkaNeural` and `ka-GE-GiorgiNeural` (language-support page). The "HD" (Dragon HD) and multilingual voices exist for other languages but not Georgian. Your ratings: Eka 3/5, Giorgi 3.5-4/5, no mispronunciations, not natural (SETUP.md §2).
- **SSML** (Speech Synthesis Markup Language): XML that controls the above. Root `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ka-GE">`, then `<voice name="ka-GE-GiorgiNeural">`, then content. Useful tags: `<break time="500ms"/>` pause; `<prosody rate="-20%" pitch="+0%">` speed/pitch; `<sub alias="...">` say this instead; `<say-as interpret-as="...">` read numbers/letters. Which tags work depends on voice and locale; the pronunciation page documents `sub` and `say-as` (`characters`/`spell-out` work for all TTS locales). I haven't tested `prosody` on ka-GE.
```xml
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ka-GE">
  <voice name="ka-GE-GiorgiNeural">
    გამარჯობა.<break time="600ms"/>
    <prosody rate="-20%">ეს ბრძანება ნელა ითქმის.</prosody>
  </voice>
</speak>
```

**Audio basics for step 1.5**
- **PCM**: raw samples, no compression. **WAV**: a small header plus PCM. A sample is a measurement of air pressure; **sample rate** = measurements per second; **bit depth** = bits per measurement; **channels** = mono 1, stereo 2.
- **Size = sample rate x bytes per sample x channels x seconds.** 10 s of 16 kHz mono 16-bit: 16,000 x 2 x 1 x 10 = **320,000 bytes** (+44-byte header). The same 10 s at 48 kHz stereo: 1,920,000 bytes.
- **STT input**: the SDK's default is WAV PCM at 16 kHz or 8 kHz, 16-bit, mono ([compressed audio page](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-use-codec-compressed-audio-input-streams)). The REST short-audio API accepts WAV PCM 16 kHz mono or OGG Opus. 16 kHz covers speech (frequencies up to 8 kHz); more adds size, not accuracy. MP3 and others need GStreamer in the SDK.
- **TTS output**: the service supports 8, 16, 24 and 48 kHz; each standard voice is available at 24 kHz and 48 kHz ([REST TTS](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)). Example formats: `riff-24khz-16bit-mono-pcm` (WAV), `audio-24khz-48kbitrate-mono-mp3`. 24 kHz 16-bit PCM is 384 kbps; the MP3 above is 48 kbps.

**Latency** ([lowering TTS latency](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency))
- **First byte latency**: time from the request until the first audio chunk arrives; independent of text length. **Finish latency**: until all audio arrives; grows with text length.
- **Streaming** lets playback start at the first chunk instead of waiting for the whole file, so a long answer starts speaking sooner. Also: reuse the `SpeechSynthesizer` and pre-connect (the websocket handshake costs time). The SDK reports these in `result.properties` (e.g. `SpeechServiceResponse_SynthesisFirstByteLatencyMs`). This is what step 2.5's per-stage timing should show.
- Total voice latency = recording end + STT + LLM + TTS first byte + playback start.

**The Python SDK in plain terms** (names verified in the Python quickstarts; package `azure-cognitiveservices-speech`, imported as `speechsdk`)
- `SpeechConfig`: key plus region (or endpoint), the language (`speech_recognition_language`) and voice (`speech_synthesis_voice_name`). "Who am I and what language/voice."
- `audio.AudioConfig` (input: default microphone or `filename=`) and `audio.AudioOutputConfig` (output: speaker or `filename=`). "Where audio comes from and goes."
- `SpeechRecognizer(speech_config, audio_config)`: does STT. `recognize_once_async().get()` returns one result with `.reason` (`RecognizedSpeech`, `NoMatch`, `Canceled`) and `.text`. For longer audio: `start_continuous_recognition()` and connect callbacks to `recognizing`, `recognized`, `session_started`, `session_stopped`, `canceled`.
- `SpeechSynthesizer(speech_config, audio_config)`: does TTS. `speak_text_async(text).get()` or `speak_ssml_async(ssml).get()`; reason `SynthesizingAudioCompleted` means success. Pass `audio_config=None` to get bytes in `result.audio_data`. `start_speaking_text_async` plus `AudioDataStream` is the streaming path.
- `.get()` waits for the async call to finish. The quickstarts read key and endpoint from environment variables; yours are `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`, so build the config with subscription and region.

## 2. In this repo
Speech Studio results are in SETUP.md §2 (Eka 3/5, Giorgi 3.5-4/5, STT mostly right but rarer words wrong). Step 1.5 is the first code; 2.5 times each stage; 2.6a compares ElevenLabs. Account setup, keys and F0 limits: [azure-basics](2026-10-02-azure-basics.md).

## 3. How the pieces fit
```
mic -> WAV 16 kHz mono -> SpeechRecognizer -> text -> LLM -> text -> SpeechSynthesizer -> 24 kHz audio -> speaker
        (SpeechConfig + AudioConfig on both sides)
```

## 4. Related tools
- ElevenLabs Scribe (STT) and its TTS models, OpenAI `gpt-transcribe`: alternatives behind the same interface (BUILD_PLAN 2.6a).
- `ffmpeg`/`sox`: convert audio formats (e.g. to 16 kHz mono WAV).
- Azure Voice Live API and avatars: realtime end-to-end voice; out of scope.

## 5. Hands-on exercises
1. `file some.wav` or `python -c "import wave;w=wave.open('some.wav');print(w.getnchannels(),w.getframerate(),w.getsampwidth()*8,w.getnframes()/w.getframerate())"`. Check: channels, rate, bits and seconds match how you recorded.
2. Compute 10 s of 16 kHz mono 16-bit by hand (320,000 bytes), then create one with `python -c "import wave;w=wave.open('t.wav','wb');w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0'*320000);w.close()"` and `ls -l t.wav`. Check: 320,044 bytes.
3. Write the SSML above (one Georgian sentence, a `<break>` and a slower `<prosody>`), paste it into Speech Studio's audio content or SSML view if it accepts SSML. Check: you hear the pause and slower speech, or you learn the tag is ignored for ka-GE.
4. In the Voice Gallery, press play and count (phone stopwatch) the time until sound starts for a short vs a long sentence. Check: the start time barely changes with length (first-byte latency), while total duration does.
5. In Speech Studio real-time STT, watch interim text change while speaking. Check: partial words rewrite before the final line.

## 6. Self-check
1. What do the acoustic and language models each contribute?
2. Real-time vs fast vs batch: which for a voice assistant, and why?
3. Why does the STT side want 16 kHz mono 16-bit?
4. How many bytes is 5 s of 24 kHz mono 16-bit audio?
5. What does streaming TTS improve: first byte latency or finish latency?
6. What does `SpeechConfig` hold, and what does `AudioConfig` hold?

<details><summary>Answers</summary>

1. Acoustic: audio to sounds. Language: likely word sequences.
2. Real-time: results as you speak. Fast/batch are for files.
3. It's the SDK default; speech information fits in 16 kHz; larger files cost bandwidth with no gain.
4. 24,000 x 2 x 1 x 5 = 240,000 bytes.
5. Time until audio starts, since playback begins at the first chunk.
6. SpeechConfig: key/region, language, voice. AudioConfig: audio source or destination.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-5 plus step 1.5 prep | About 1 hr |
| B. Another AI tutor | Concepts and quiz | About 45 min |
| C. Primary docs | Exact SDK names and limits | About 1.5 hr |
| D. Video/course | Not verified | |

**A. Prompt:**
> Walk me through learning/notes/2026-10-02-how-speech-services-work.md. Do the 5 exercises one at a time (run the commands, show output, have me explain it), then quiz me on the self-check. Don't write the step 1.5 code yet.

**B. Prompt:**
> Using only these sources, explain how speech-to-text and text-to-speech pipelines work, what sample rate and PCM mean, why streaming lowers TTS latency, and what the Azure Speech SDK classes do. Then give a 5-question quiz. Sources: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-speech-to-text, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-text-to-speech, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-use-codec-compressed-audio-input-streams, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-pronunciation

**C. Docs (opened 2026-10-02; select Python on the quickstarts):**
- STT quickstart: `recognize_once_async`, results, formats.
- TTS quickstart: `SpeechSynthesizer`, voice name, SSML call.
- How to recognize speech (Python): continuous recognition, events, silence timeouts: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech?pivots=programming-language-python
- Compressed audio: default formats and GStreamer.
- Lower TTS latency: first byte vs finish, streaming, pre-connect.
- REST TTS: output formats and sample rates; REST short-audio STT: input formats and result fields.
- Hands-on module (from search, not read in full): https://learn.microsoft.com/training/modules/create-speech-enabled-apps

**D. Video:** I did not search for or confirm a specific video for this note. Search terms: "Azure Speech SDK Python quickstart", "sample rate bit depth PCM WAV explained". If you want one, ask for a verified pick.

---

## 8. Speech SDK in practice (step 1.5) *(added 2026-10-03)*

Observed 2026-10-03 on WSL2, Python 3.14, `azure-cognitiveservices-speech` 1.52.0, Azure F0 in `italynorth`. Checked against the Microsoft Learn "how to recognize speech" page, the `CancellationDetails` API page and the Azure-Samples Python console samples. The code is `speech_smoke.py`; line-by-line in `docs/code/speech_smoke.py.md`.

**Problem.** A smoke test that "works" can still hide the first sentence of a recording, swallow an error, or fail for a reason that has nothing to do with your code. These are the traps we actually hit.

**`recognize_once()` vs continuous recognition**
- `recognize_once()` returns after the **first utterance** (silence at the end, or at most 15 s of audio per the how-to page). On a 5.5 s file with two sentences it returned only `Გამარჯობათ ჯიხვის ცხელი ხაზია.` and silently dropped the second.
- `start_continuous_recognition()` keeps going until the audio ends or you stop it. The same file gave **2 utterances** (two `recognized` events). `speech_smoke.py` joins the parts with a space.
- You can't switch modes on one recognizer: calling `recognize_once` after continuous mode raised `RuntimeError` containing `SPXERR_SWITCH_MODE_NOT_ALLOWED (0x1e)` and a long C++ call stack. Make a new `SpeechRecognizer` per mode.

**The event model.** Continuous recognition is callback-based: you `connect` a function to each event and the SDK calls it from **its own thread**.
- `session_started` / `session_stopped`: the audio session opened / closed. `recognizing`: interim text. `recognized`: a final utterance (`evt.result.reason`, `evt.result.text`). `canceled`: the session ended early *or* ended normally (below).
- The main thread has to wait. We use a `threading.Event`: `session_stopped` calls `done.set()`, the main thread calls `done.wait(timeout=duration + 30)` (returns `False` on timeout, a safety net), then `stop_continuous_recognition()`.

**Exceptions inside callbacks are swallowed.** The real bug from the break test: the `canceled` handler read `evt.reason`, but a canceled event has no `reason`; it's `evt.cancellation_details.reason`. The `AttributeError` happened on the SDK thread and **nothing was printed**. With a wrong key the script said "No speech recognized" instead of an authentication error. Rule: keep callbacks tiny (append to a list, set an event) and do the real work on the main thread after `wait()`. Timeline with the wrong key: `session_started` at 0.00 s, `canceled` 0.23 s, `session_stopped` 0.23 s. You'd see this only by logging each event.

**`canceled` is not always an error.** It also fires with `CancellationReason.EndOfStream` when a file simply ends. Only `CancellationReason.Error` is a failure; then read `cancellation_details.error_details` and the code.
- SDK inconsistency: recognition `CancellationDetails` has `.code`; synthesis `SpeechSynthesisCancellationDetails` has `.error_code` (I checked both with `dir()`). `explain_cancel` handles both with `hasattr`.

**TTS to a file**
- `SpeechSynthesizer(speech_config=..., audio_config=None)` doesn't open a speaker; the bytes are in `result.audio_data`. The default would open the default speaker through ALSA, which doesn't exist in WSL (see [audio on Linux and WSL](2026-10-03-audio-on-linux-and-wsl.md)).
- `SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm`: "Riff" formats include the 44-byte WAV header, so `Path.write_bytes(result.audio_data)` gives a valid `.wav`. A raw-PCM format would need a header added.

**Break tests and their output**
| Change | Result |
|---|---|
| wrong key | `AuthenticationFailure: WebSocket upgrade failed: Authentication error (401)` |
| region `nowhere` | `ConnectionFailure ... DNS resolution failed ... wss://nowhere.stt.speech.microsoft.com/...` |
| region `westus` with the italynorth key | still 401 |
- The region is part of the **hostname** (`<region>.stt.speech.microsoft.com`), so a nonsense region fails at DNS. A real but wrong region reaches a server that doesn't know your key: keys are region-scoped ([Azure basics](2026-10-02-azure-basics.md)).

**Measured (F0, italynorth):** TTS 0.8-1.8 s per sentence; STT 1.0-2.0 s for 5-6 s of file audio. Files are processed faster than real time; a live mic would take as long as you speak plus the silence timeout. Step 2.5 should time each stage separately.

**Exercises**
1. Add `recognizer.session_started.connect(...)`, `recognizing`, `recognized`, `canceled`, `session_stopped` handlers that each print `time.perf_counter() - start` and the event name. Check: for a 2-sentence file you see `recognizing` lines before each `recognized`, and `canceled` (EndOfStream) just before `session_stopped`.
2. Record two sentences with a pause (`python speech_smoke.py record two --seconds 6`). Write a throwaway script using `recognize_once_async().get()` on it. Check: only the first sentence; then run `stt` and compare.
3. In one handler write `1/0`. Check: nothing is printed and the script carries on. Then wrap the body in `try/except Exception: traceback.print_exc()` and see the error appear.
4. Set a wrong `AZURE_SPEECH_KEY` for one command (`AZURE_SPEECH_KEY=x python speech_smoke.py stt audio/q1.wav`; `load_dotenv` doesn't override, see [env vars](2026-10-02-env-vars-and-dotenv.md)). Check: the 401 message and the 0.2 s timeline.
5. Run `tts` once for a short and once for a long sentence with `--no-play`. Check: time barely grows; file size grows (24 kHz x 2 bytes = 48,000 bytes per second).

**Self-check**
1. Why did `recognize_once` return half the recording?
2. Where does a callback run, and what happens to an exception raised in it?
3. Is every `canceled` event a failure?
4. Why `audio_config=None` for TTS in WSL, and why can the bytes go straight into a `.wav`?
5. Why does region `westus` give 401 but `nowhere` gives a DNS error?

<details><summary>Answers</summary>

1. It stops after the first utterance; continuous recognition fires `recognized` per utterance until the audio ends.
2. On an SDK thread; the exception is swallowed with no message. Keep callbacks tiny and check results on the main thread.
3. No: `EndOfStream` is normal. Only `CancellationReason.Error` is.
4. Default output opens a speaker via ALSA, which WSL lacks; a Riff format output includes the WAV header.
5. The region is a hostname part: `nowhere` doesn't resolve; `westus` resolves but doesn't know your region-scoped key.
</details>

**Ways to learn it (choose later)**

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-5 on your own `speech_smoke.py` | About 1 hr |
| B. Another AI tutor | Event model and threading explained from the docs | 45 min |
| C. Primary docs | Exact event and class names | 1 hr |
| D. Course | Microsoft's free training module | 1-2 hr |

- **A. Prompt:** > Walk me through section 8 of learning/notes/2026-10-02-how-speech-services-work.md using speech_smoke.py. Do exercises 1-5 one at a time (run, show output, have me explain), then quiz me on the self-check.
- **B. Prompt** (NotebookLM or ChatGPT/Gemini): > Using only these sources, explain continuous vs single-shot recognition in the Azure Speech SDK for Python, which events fire and in what order, and how to handle cancellation. Then give a 5-question quiz. Sources: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech?pivots=programming-language-python, https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.cancellationdetails, https://github.com/Azure-Samples/cognitive-services-speech-sdk/tree/master/samples/python/console, https://docs.python.org/3/library/threading.html#event-objects
- **C. Docs (opened 2026-10-03):**
  - [How to recognize speech (Python)](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech?pivots=programming-language-python): continuous recognition section, events, 15 s single-shot limit, error handling.
  - [CancellationDetails API](https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.cancellationdetails): the `code`, `error_details`, `reason` attributes (the page lists no descriptions).
  - [SpeechRecognizer API](https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.speechrecognizer): appeared in search results, not read in full.
  - [Azure-Samples Python console samples](https://github.com/Azure-Samples/cognitive-services-speech-sdk/tree/master/samples/python/console): `speech_sample.py` has `speech_recognize_continuous_from_file()` with the session_stopped/canceled pattern; `speech_synthesis_sample.py` for TTS.
  - [threading.Event](https://docs.python.org/3/library/threading.html#event-objects): `set`, `wait(timeout)` returns `True`/`False`.
- **D. Course:** Microsoft Learn, ["Fundamentals of Azure AI Speech"](https://learn.microsoft.com/en-us/training/modules/recognize-synthesize-speech/) (free module; found in search, I didn't take it). I couldn't confirm a specific YouTube video with creator and link for the Python Speech SDK; search terms: "Azure Speech SDK Python continuous recognition".
