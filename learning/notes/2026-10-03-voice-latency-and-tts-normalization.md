# Voice pipelines: latency budget and TTS text normalization

Written 2026-10-03 for step 2.5. Checked: `voice.py`, `speech_text.py`, the step 2.5 "Result" line in BUILD_PLAN.md, a run of `python speech_text.py` here, and the sources in section 7 (opened that day). General TTS/STT background is in [how speech services work](2026-10-02-how-speech-services-work.md) and [code-switching](2026-10-02-code-switching-stt-tts.md); this note doesn't repeat it.

## 1. What you're learning, and why it matters

**Problem A: the caller hears silence after they stop talking.** A voice assistant is a chain of slow steps, and the caller only notices the gap before the reply starts.

- **Cascaded pipeline:** `STT -> LLM graph -> speech-text -> TTS -> playback`. Each box waits for the one before it.
- **The metric:** "until the reply starts" = STT + graph + speech-text + TTS (not playback, which happens while the caller already hears the answer). `voice.py`'s `print_times()` prints exactly this sum.
- **Latency budget:** you split a target (say 2 s) across the stages and see which one is over. Stages that run one after another add up; stages that overlap don't.
- **Streaming** = start the next stage on partial output instead of waiting for the full output.
- **Human reference:** Stivers et al. (PNAS 2009, 10 languages) found people minimise silence between turns; average gaps differ between languages by up to about 250 ms around the cross-language mean. The figure usually quoted is a gap of roughly 200 ms. I opened an abstract summary, not the full paper, so treat "about 200 ms" as the commonly cited value.
- **Product targets** (vendor blogs, not research): ElevenLabs' latency guide gives example P50 stage times of capture+endpointing 120 ms, STT 60 ms, network 60 ms, LLM first token 250 ms, TTS 110 ms, total about 680 ms (P95 about 1560 ms). Other vendor posts say 500-800 ms feels natural and above ~1.5 s degrades. These come from streaming systems.

**Problem B: the TTS voice can't read written text as written.** Prices, times and English terms in a Georgian answer get skipped or mangled.

- **Text normalization / verbalization** = rewriting written forms into the words a person would say (`15 ₾` -> "15 ლარი"). It is the first step of the TTS front end, before grapheme-to-phoneme ([note](2026-10-02-code-switching-stt-tts.md)).
- **Rule-based** (regexes, or grammars compiled to finite-state transducers as in Google's Kestrel/Sparrowhawk): predictable, easy to fix one case. **Neural/LLM-based**: handles odd inputs but can invent words; Sproat & Jaitly (2016) found RNNs made rare but serious errors (wrong numbers) and needed a rule-based filter. For customer service, wrong digits (prices, numbers) are the worst failure, so rules are the safe default.

**Problem C: the transcript can be wrong before the graph sees it.** STT errors flow downstream; see section 2.

## 2. In this repo

**Measured with Roman's step-1.5 recordings** (`python voice.py --no-play --wav audio/q1.wav audio/c3.wav audio/c4.wav audio/rt_georgian.wav`):

| Stage | Time | Note |
|---|---|---|
| STT | 1.2-1.4 s | for about 5 s of audio; a silent file took 0.71 s and skipped the graph |
| graph | 1.4 s (clarify, 1 LLM call) to 2.7 s (faq, 2 LLM calls) | faq: understand ~1.0 s + MCP lookup 0.0-0.6 s + answer ~1.1 s |
| speech-text | ~0 ms | regexes |
| TTS | 1.0-1.2 s | |
| **until reply starts** | **3.6-5.1 s** | typed turn: 2.48 + 1.23 = 3.7 s; playback 6.2 s on top |

The budget is far over any streaming-agent target. The sequential LLM calls and non-streaming STT/TTS are the reasons.

**Where it could be cut (not implemented; talking points):**
- **Streaming STT while recording:** feed Azure a `PushAudioInputStream` as the chunks arrive, so recognition is finished right after the second Enter instead of starting then (saves most of the 1.2-1.4 s).
- **Streaming TTS:** `start_speaking_text_async` + `AudioDataStream`, play from the first chunk. Azure's doc says first-byte latency doesn't depend on text length while finish latency does, so long answers gain most.
- **Stream the LLM answer sentence by sentence into TTS** (ElevenLabs suggests sentence boundaries). Azure also has an input-text-streaming mode on its websocket v2 endpoint, but it takes no SSML.
- **Fewer LLM calls:** `understand` and `answer` run in sequence; merging them or using a smaller model for `understand` saves about 1 s.
- **Reuse/pre-connect the synthesizer:** a new websocket costs TCP + TLS + upgrade each time (Azure recommends `Connection.open(True)` when the user starts talking). We create one per call. Also keep the region close to the user.
- **Not a lever here:** speech-text is already ~0 ms.

**Push-to-talk vs automatic endpointing.** Push-to-talk: the user presses Enter to start and stop, so the program never guesses when speech ends. **VAD** (voice activity detection) detects speech vs silence; **endpointing** uses it to decide the turn ended (typically after a silence threshold; too short cuts people off, too long adds delay). **Barge-in** = the caller interrupts while the assistant talks, so the program must stop playback and listen. Both need continuous audio capture and echo handling. The scope guardrail chose push-to-talk to keep step 2.5 about the pipeline, not about turn-taking; mention it as a known simplification.

**STT errors propagate.** q1 "რა ღირს როუმინგი ევროპაში?" was heard as "რა ღირს რომ მინი ევროპაში." and the graph asked "რომელ მინი პაკეტს გულისხმობთ: როუმინგის თუ ინტერნეტის?". It behaved sensibly on wrong input, but the answer was wrong for the real question. c4 (garbled code-switched speech) became `intent=other`. So evaluate STT and the graph separately and together: Phase 3.4 (see BUILD_PLAN.md).

**`speech_text.py`** (called by `voice.py` just before TTS; the screen text is unchanged). Measured problems with `ka-GE-GiorgiNeural` via TTS -> STT round trips:

| Written | Heard back | After rewrite |
|---|---|---|
| `15 ₾` | `₾` silent | "15 ლარი" (0.50 ₾ -> "50 თეთრი") |
| `10:00-დან` | "10 0 0 დან" | "10 საათიდან" |
| `„ჯიხვი S"` | S dropped | "ჯიხვი ეს" |
| `GB` | "იგებ" | "გიგაბაიტ..." |
| `QR` | dropped | "ქიუარ"; round trip heard "ქი ვარ" |
| `eSIM` ("ისიმის") | "ის იმის" | still unjudged: ears needed |

Rules (all regex): `PRICE` (lari/tetri), `CLOCK`, `24/7`, `RANGE` ("1-3" -> "1-დან 3-მდე"), `PERCENT`, `NETWORK` ("5G" -> "5 ჯი"), then `TERMS` (dict of "stem|ending", so "GB-ს" -> "გიგაბაიტს": the nominative ending drops before a case suffix), linking vowels (`საათ`+`დან` -> "საათიდან", +`მდე` -> "საათამდე"), `LETTERS` fallback for short all-caps words (API -> ეიპიაი), and `leftover_latin()` which warns about words still in Latin letters.

- **Why plain text, not SSML:** `<sub alias="ქიუარ">QR</sub>` and `<say-as>` do the same job, but every reply would need SSML wrapping and XML escaping. Also Azure's doc says most `say-as` types (date, time, currency...) are supported only for a list of languages that doesn't include Georgian; only `characters`/`spell-out` work for all locales. So the rewrite is the portable option.
- **The round trip as a cheap automated check:** synthesize, transcribe, compare. It catches silent or dropped words. Limit: it tests TTS and STT together, so a correct-sounding word that STT mishears fails, and a wrong-sounding word STT forgives passes. Only listening judges pronunciation.

## 3. How the pieces fit

```
mic -> Recorder -> STT ->[transcript]-> graph (understand -> lookup -> answer)
   -> reply text (screen) -> speakable() -> TTS -> WAV -> play
        until the reply starts = STT + graph + speech-text + TTS
```

## 4. Related tools

- **Streaming voice frameworks** (LiveKit Agents, Pipecat, Vapi): handle streaming, VAD and barge-in for you. We build the loop by hand to learn it.
- **OpenAI/Gemini realtime speech-to-speech APIs:** skip the cascade; lower latency, but Georgian quality and control over what is said are worse for customer service.
- **Sparrowhawk / NeMo text processing:** serious rule-based normalizers, but they don't ship Georgian grammars; we wrote the few rules we need.
- **SSML `sub` / custom lexicon:** the Azure-native way to fix pronunciations; see above.

## 5. Hands-on exercises

1. `python speech_text.py`. Check: prints each FAQ/fixed reply that changes ("24 of 29 texts changed" at the time of writing) and any "left in Latin letters" warning.
2. `python speech_text.py "ჯიხვი S 15 ₾, 10:00-დან 19:00-მდე, 1-3 დღე, API, GB-ს"`. Check: numbers and terms are spelled out as in the table.
3. Add `"USB": "იუესბი"` to `TERMS`, run `python speech_text.py "USB კაბელი"`, then try an unknown word like `"XYZZY"`. Check: the first is rewritten; the second prints a "left in Latin letters" line.
4. Compute a budget: with the table above, subtract what streaming STT (say 1.0 s saved) and a merged LLM call (1.0 s saved) would give on the faq path. Check: your total, and which stage is now largest.
5. Run `python voice.py --no-play --wav audio/q1.wav` and read the `[time]` line. Check: the four stage times add up to "until the reply starts".
6. Round trip: `python speech_smoke.py tts "15 ₾" --out audio/raw.wav --no-play`, then `python speech_smoke.py tts "$(python speech_text.py '15 ₾')" --out audio/fixed.wav --no-play`, then `python speech_smoke.py stt audio/raw.wav` and the same for `fixed.wav`. Check: only the rewritten one comes back with "ლარ".

## 6. Self-check

1. Which stages count in "until the reply starts", and why not playback?
2. Name three ways to cut it and which stage each attacks.
3. Push-to-talk vs VAD endpointing vs barge-in: one line each.
4. Why can a normalization step be correct for the text and still wrong for the ear?
5. Why does `speech_text.py` prefer plain text over SSML `sub`?
6. Why is a TTS -> STT round trip only a proxy?

<details><summary>Answers</summary>

1. STT, graph, speech-text, TTS: the caller waits for all of them before hearing anything. Playback runs while they already hear the reply.
2. Streaming STT (STT), streaming TTS from the first chunk (TTS), sentence-wise LLM output into TTS or fewer LLM calls (graph), pre-connected/reused synthesizer (TTS).
3. User presses a key / program detects the end of speech from silence / user interrupts the assistant mid-reply and playback stops.
4. The rule fixes what is written (e.g. "ისიმ"), but how the neural voice pronounces it can still sound off; only listening tells.
5. Same audio without wrapping and escaping every reply in XML; and Azure's `say-as` types mostly aren't available for Georgian.
6. Two models are tested at once; STT can forgive a mispronunciation or mishear a fine one.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-6 on the real numbers | 45 min |
| B. Another AI tutor | Latency budget reasoning, normalization concepts | 45 min |
| C. Primary docs | Azure streaming and SSML, the normalization papers | 1.5 hr |
| D. Course/video | Seeing a production voice agent built and tuned | 1 hr |

**A. Prompt for a main session in this repo:**
> Walk me through learning/notes/2026-10-03-voice-latency-and-tts-normalization.md. Do exercises 1-6 one at a time, show me real output, then quiz me on the self-check questions.

**B. NotebookLM** (load the C links) or ChatGPT/Gemini. Prompt:
> Using only these sources, explain a voice agent's latency budget (STT, LLM, TTS, streaming), what TTS text normalization is and how rule-based and neural approaches differ, then give me a 5-question quiz. Sources: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-pronunciation, https://arxiv.org/abs/1611.00068, https://github.com/google/sparrowhawk, https://elevenlabs.io/blog/voice-agent-latency-optimization

**C. Docs (opened 2026-10-03):**
- [Azure: lower speech synthesis latency](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency): first-byte vs finish latency, streaming (`AudioDataStream`), pre-connect, reuse, text streaming.
- [Azure SSML pronunciation](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-pronunciation): `sub`, `say-as` table and its language note, custom lexicon.
- [Sproat & Jaitly, "RNN Approaches to Text Normalization: A Challenge"](https://arxiv.org/abs/1611.00068): read the abstract and intro; why neural errors matter.
- [Google Sparrowhawk](https://github.com/google/sparrowhawk): README for tokenizer/classifier vs verbalizer. The related Kestrel paper is in Natural Language Engineering (found in search, not opened).
- [ElevenLabs, voice agent latency optimization](https://elevenlabs.io/blog/voice-agent-latency-optimization): stage-by-stage budget (a vendor source).
- [Stivers et al. 2009, PNAS](https://www.pnas.org/doi/10.1073/pnas.0903616106): the human turn-gap paper (the PNAS site returned 403 to me; I read the summary at [cognitionandculture.net](https://cognitionandculture.net/blogs/icci-blog/universals-and-cultural-variation-in-turn-taking-in-conversation)).

**D. Course/video:**
- [DeepLearning.AI, "Building AI Voice Agents for Production"](https://www.deeplearning.ai/short-courses/building-ai-voice-agents-for-production): free short course, about 1 hour, taught by Russ d'Sa and Shayne Parmelee (LiveKit) and Nedelina Teneva (RealAvatar). Lessons "Voice Agent Overview", "End-to-end Architecture", "Optimizing Latency with Code Example". Page opened; I haven't taken it.
- Standalone YouTube video: I couldn't confirm one by search. Try "voice agent latency STT LLM TTS" or "text normalization for speech synthesis" on YouTube and check the creator before trusting it.

*(added 2026-10-07)* Streaming TTS playback (first sound after about 0.6 s instead of waiting for the whole reply, gaps and buffering): see [Streaming audio playback](2026-10-07-streaming-audio-generators-and-buffering.md).
