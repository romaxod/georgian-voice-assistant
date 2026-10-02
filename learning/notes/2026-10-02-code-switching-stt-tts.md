# Code-switching: Georgian with English tech words in STT and TTS

Checked 2026-10-02 against the linked docs. Provider docs change fast; re-check before relying on a limit.

## 1. What you're learning, and why it matters

**Problem.** Georgian developers say things like *"API-ს key როგორ შევცვალო?"*. That mix is **code-switching** (**intra-sentential** when it happens inside one sentence; **inter-sentential** between sentences). Speech systems are mostly built around one language at a time, so the mixed words come out wrong in transcripts (STT) or are read oddly (TTS). Roman's own testing (SETUP.md §2): Azure STT is mostly right on ordinary words and misses rarer ones; Eka scored 3/5 and Giorgi 3.5-4/5 on TTS.

**Why a recognizer decodes with one language at a time**
- An STT system has two parts. The **acoustic model** maps audio to likely sounds. The **language model (LM)** scores which word sequences are plausible *in one language* ("which word usually follows these?"). The decoder combines both scores.
- With Georgian chosen, the vocabulary and LM are Georgian. An English word like "key" has no entry, so the decoder picks the closest-sounding Georgian words (e.g. "ქი") or garbage.
- Rarer Georgian words fail the same way: low LM probability, so a more common word wins.

**Language ID (LID) modes in Azure** ([docs](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-identification))
- **At-start LID**: decides the language once from the first few seconds (up to 4 candidate languages). Use when the language doesn't change.
- **Continuous LID**: can change language during the audio (up to 10 candidates), but per the docs it "doesn't support changing languages within the same sentence". Their example: speaking Spanish and inserting English words doesn't get detected per word. So it helps with Georgian sentence, then English sentence; it does **not** fix our mixed sentence. English words are decoded as Georgian.

**Biasing: telling the recognizer which words to expect.** They differ in where the hint goes:
- **Phrase list** (Azure): words you pass at runtime, which raise those words' probability. No training. Azure's [language support table](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt) doesn't show it enabled for `ka-GE` (the page lists phrase list as a runtime feature "for locales where the feature is enabled"). Check by looking for the Phrase list toggle in Speech Studio with Georgian selected.
- **Keyterm prompting** (ElevenLabs Scribe v2): same idea, a list of terms with the request. Batch: up to 1,000 terms of 50 chars; realtime: 50 terms of 20 chars ([docs](https://elevenlabs.io/docs/capabilities/speech-to-text)). Georgian is in its "High Accuracy" tier (5-10% WER). Code-switching isn't documented.
- **Prompt / keywords** (OpenAI `gpt-transcribe`): `prompt` is free-text context, `keywords` literal terms ("hints, not required output"), `languages` the expected languages ([docs](https://developers.openai.com/api/docs/guides/speech-to-text)). The page doesn't list Georgian explicitly, so test before trusting it.
- Heavier option, not planned: Azure **custom speech** (train on your data; Georgian: plain-text only).

**WER (word error rate)** = (S + D + I) / N: substitutions + deletions + insertions, divided by the number of words in the **reference** (what was really said). By hand:
- Reference: `როგორ შევცვალო API key ახლა` (N = 5)
- Heard: `როგორ შევცვალო აპი ქი` (4 words)
- "API" became "აპი" (S), "key" became "ქი" (S), "ახლა" is missing (D). WER = (2 + 1 + 0) / 5 = 60%.
- Normalize first (case, punctuation) or you count noise. Note that the Georgian spelling of an English word counts as an error even if it sounds right; decide in advance whether that's what you want to measure.

**TTS side: grapheme-to-phoneme (G2P).** A TTS voice first converts letters (graphemes) into sounds (phonemes). A Georgian voice has Georgian letter-to-sound rules. Latin-script "API" or "LangGraph" isn't in those rules, so it may be spelled out, skipped, or read with Georgian-style sounds. Azure documents no ka-GE behavior for English words. Georgian is also not on its multilingual voice list (checked: the ka-GE rows are only `ka-GE-EkaNeural` and `ka-GE-GiorgiNeural`, standard type). Workarounds:
- Rewrite English terms in Georgian script before TTS ("API" -> "ეი-პი-აი"), a "speech-text" step separate from the display text.
- **SSML** (Speech Synthesis Markup Language, XML that controls speech). Basics: `<speak>` root, `<voice name="...">`, then content. `<sub alias="...">` says the alias instead of the enclosed text; the [pronunciation page](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-pronunciation) documents `sub`, `phoneme` (IPA etc.; each locale supports its own phone set), `say-as` and custom lexicons. I didn't test whether ka-GE honors `sub` or `phoneme`.
```xml
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ka-GE">
  <voice name="ka-GE-GiorgiNeural">
    <sub alias="ეი-პი-აი">API</sub>-ს გასაღები
  </voice>
</speak>
```

**Benchmark paper.** [arXiv 2605.19069](https://arxiv.org/pdf/2605.19069) exists: "Benchmarking Commercial ASR Systems on Code-Switching Speech: Arabic, Persian, and German". It does **not** cover Georgian, and I could only read its title and abstract-level content, so don't cite numbers from it. It shows the problem is general, not Azure-specific.

## 2. In this repo
- SETUP.md §2 "Code-switching" holds the findings; BUILD_PLAN.md adds tests: 1.5 (3 code-switched recordings, one TTS reply with an English word), 2.5 (a "speech-text" step before TTS), 2.6a (optional Scribe v2 keyterm comparison), 3.1 and 3.4 (code-switched eval category, with 2+ spoken cases).
- Roman's demo video: only the **demo interaction** goes through STT, and he picks which English words appear in it. Plan the demo sentences around terms you've tested.

## 3. How the pieces fit
```
mic -> STT (language model: ka only) -> text -> LLM -> reply text
reply text -> speech-text step (English terms -> Georgian script / <sub>) -> TTS -> audio
```
STT errors on English terms flow into the LLM; the LLM can often still guess "API-ს key" from context, so measure end-to-end, not only WER.

## 4. Related tools
- ElevenLabs Scribe v2, OpenAI `gpt-transcribe`: candidates with keyterm/keyword hints (see above).
- Azure custom speech and custom lexicon: more work, only if the cheap fixes fail.
- Multilingual TTS voices (Azure): not available for Georgian, so not usable here.

## 5. Hands-on exercises
1. In Speech Studio (Real-time STT, language fixed to Georgian), record 3 code-switched sentences. Write the reference for each, compute WER by hand with the formula above. Check: three numbers and a list of which words failed. (Same as BUILD_PLAN 1.5.)
2. In the Voice Gallery, have Giorgi read one sentence with "API" in Latin script and the same sentence with it in Georgian script. Check: you can describe the difference in one line.
3. Repeat exercise 1's worst sentence with the Phrase list toggle (advanced options). Check: if the toggle isn't available for Georgian, that confirms the docs.
4. Write a 10-entry keyterm list for this project, e.g. API, key, LangGraph, MCP, Azure, STT, TTS, token, prompt, ElevenLabs. Check: each entry has a Latin spelling and a Georgian-script spelling you'd want TTS to say.
5. Write the same 3 sentences' WER in a tiny table (S, D, I, N); later reuse it for 3.4.

## 6. Self-check
1. Why does an English word inside a Georgian sentence come out as Georgian words?
2. Difference between acoustic model and language model?
3. What does continuous LID fix, and what does it not fix?
4. Phrase list vs keyterm prompting vs prompt: how do they differ, and which work for Georgian?
5. Compute WER: reference "open the API key page", heard "open a API page".
6. Why might a Georgian TTS voice mangle "LangGraph", and name two fixes.

<details><summary>Answers</summary>

1. STT uses one language's vocabulary and LM per segment; no Georgian-LM entry for the English word, so it picks the closest Georgian-sounding words.
2. Acoustic: audio to likely sounds. Language: which word sequences are likely in that language.
3. It switches language between segments/sentences (up to 10 candidates); it doesn't switch inside a sentence.
4. Phrase list: runtime word boosts (Azure; not enabled for ka-GE). Keyterms: a term list sent with the request (Scribe v2, Georgian supported as a language). Prompt/keywords: free-text or literal hints (OpenAI; Georgian unconfirmed). All are hints, not guarantees.
5. "the"->"a" (S), "key" missing (D): S=1, D=1, I=0, N=5, WER = 2/5 = 40%.
6. G2P has only Georgian letter-to-sound rules for Latin text. Fixes: rewrite in Georgian script before TTS; SSML `<sub alias>` or `<phoneme>` (untested for ka-GE).
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Doing exercises 1-4 on your own voice | About 1 hr |
| B. Another AI tutor | Concept explanations and a quiz | About 45 min |
| C. Primary docs | Exact behavior and limits | About 1 hr |
| D. Video/course | Intuition for ASR and WER | Not verified |

**A. Prompt:**
> Walk me through learning/notes/2026-10-02-code-switching-stt-tts.md. Go through exercises 1-4 one at a time: have me record sentences, compute WER by hand and check my arithmetic, then quiz me on the self-check questions.

**B. Tool:** NotebookLM loaded with the C links, or ChatGPT/Gemini. Prompt:
> Using only these sources, explain why speech recognizers struggle with mid-sentence language mixing, how phrase lists and keyterms differ, and how SSML sub/phoneme fix TTS pronunciation. Then give me a 5-question quiz with answers. Sources: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-identification, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-pronunciation, https://elevenlabs.io/docs/capabilities/speech-to-text, https://developers.openai.com/api/docs/guides/speech-to-text

**C. Docs (opened 2026-10-02):**
- Azure language identification: at-start vs continuous, and the "same sentence" limit.
- Azure phrase list: what it does, weight 0-2, Speech Studio test steps.
- Azure language support (STT tab): the ka-GE row and phrase list footnote; TTS tab for the two voices.
- Azure SSML pronunciation: `sub`, `phoneme`, `say-as`, custom lexicon.
- ElevenLabs speech-to-text: accuracy tiers and keyterm limits.
- OpenAI speech-to-text guide: `prompt`, `keywords`, `languages`.
- WER definition: https://en.wikipedia.org/wiki/Word_error_rate (S, D, I and the formula).
- Overview of the field (survey, appeared in search, not read in full): https://arxiv.org/pdf/2507.07741

**D. Video:** I searched for WER and code-switching videos and the results were articles and papers, so I couldn't confirm any specific video or course. Search terms: "word error rate explained", "code-switching speech recognition lecture".
