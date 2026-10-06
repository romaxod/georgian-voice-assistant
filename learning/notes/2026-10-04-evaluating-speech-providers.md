# Comparing speech providers fairly: WER by dynamic programming, term recall, MOS, leakage

Step 2.6a, `compare_speech.py`. Sources opened 2026-10-04. Builds on [WER by hand](2026-10-02-code-switching-stt-tts.md) (definition, S/D/I), [first-byte latency](2026-10-02-how-speech-services-work.md) and [text normalization](2026-10-03-georgian-unicode-mtavruli.md).

## 1. What you're learning, and why it matters

**Problem: "ElevenLabs sounds better" is an opinion.** To choose a provider, and to defend the choice, you need numbers from a test that doesn't favour either side.

**How WER is really computed.** By hand you count S, D, I. A program needs the *smallest* number of edits turning the hypothesis into the reference. That is **Levenshtein edit distance on words**, solved with **dynamic programming** (fill a table where cell `[i][j]` = cheapest way to turn the first `j` hypothesis words into the first `i` reference words):

`D[i][j] = min( D[i-1][j] + 1 (delete), D[i][j-1] + 1 (insert), D[i-1][j-1] + (ref[i] != hyp[j]) (match or substitute) )`

Real table for c1: reference `api ს key როგორ შევცვალო` (5 words) vs Azure's `ვი პი აის ქე რო გორ შევცვალო` (7 words). Rows = reference words, columns = hypothesis words:

```
      -  ვი პი აის ქე რო გორ შევცვალო
 -    0  1  2  3  4  5  6  7
api   1  1  2  3  4  5  6  7
ს     2  2  2  3  4  5  6  7
key   3  3  3  3  4  5  6  7
როგორ 4  4  4  4  4  5  6  7
შევც. 5  5  5  5  5  5  6  6     <- bottom-right = 6 edits
```

6 edits / 5 reference words = **120%**. WER **can exceed 100%** because the divisor is the *reference* length: insertions are errors with no reference word to "pay" for them (Wikipedia and the Hugging Face course both say so). `compare_speech.wer()` keeps only one row of this table (`row`, plus `prev` for the diagonal) because each row needs just the previous one (Wikipedia: memory drops to O(min(m,n))).

**Normalization comes first.** `words()` lowercases and turns punctuation into spaces, on both sides: `API-ს` becomes `api`, `ს`. Without it `"შევცვალო."` and `"შევცვალო"` would count as an error. Every normalization choice changes the score, so the same rule must apply to every provider. (jiwer, the standard tool, has transforms for this; our version is ~10 lines.)

**A second metric: term recall.** WER weighs every word equally, but the assistant lives or dies on `eSIM`, `QR`, `roaming`. `terms_found()` asks only: did each key term come through? A Georgian-script spelling counts (`იმეილ`, `ქიუარ`), because the graph can use it. It matches at the **start of a word** (`(?<!\w)` + the form) since Georgian suffixes attach (`eSIM-ის`, `აიფონზე`).

**One variable per column.** Azure -> Scribe v2 -> Scribe v2 + keyterms. The second step changes the model; the third changes only the biasing. If you changed both at once you couldn't say which one helped.

**Test-set leakage.** In ML, if the test data influenced training or tuning, the score is flattering. Here: keyterms are built from `data/faq.json` (Latin terms like 4G, 5G, GB, MB, PIN, PUK, QR, SIM, eSIM) plus a few domain words. `API` and `key` are deliberately **not** in the list, although they're in recordings c1/c2: adding them would be tuning on the test set and make Scribe look better than it will be on new questions. Say that whenever you quote the numbers.

**TTS can't use WER; humans rate it.** **MOS (mean opinion score):** listeners rate clips 1-5 and you average; the standard setup is an ACR (absolute category rating) test from ITU-T P.800. `compare_speech.py rate`:
- shuffles the 20 clips (10 sentences x 2 providers) so order doesn't reveal the provider (blind),
- asks pronunciation and naturalness separately,
- saves after each clip so a crash keeps ratings.
- **Match the voice gender** (Giorgi is male, so pick a male ElevenLabs voice): otherwise "which one is the woman" gives it away and biases the rating.
- **Small-sample honesty:** 10 sentences, one rater (Roman), no significance test. Report it as "one listener's preference", not as proof.
- **Time to first audio vs total time:** first audio is what the caller waits for when playback starts as chunks arrive; total includes the rest of the generation. Report medians (a single slow request skews a mean).

## 2. In this repo

- Run: `.venv/bin/python compare_speech.py stt`, then `tts`, then `rate`. Results are saved to `runs/*.json` (gitignored).
- Providers are called directly, not via `WithFallback` (see [swappable providers](2026-10-04-swappable-providers-and-fallbacks.md)).
- STT runs one request at a time because Azure F0 allows one concurrent STT request.

**Azure baseline (Roman's 5 recordings, run 2026-10-03; unchanged on 2026-10-06):**

| File | WER | Terms | Azure heard |
|---|---|---|---|
| q1 | 50% | 0/1 | რა ღირს რომ მინი ევროპაში. |
| c1 | 120% | 0/2 | ვი პი აის ქე რო გორ. შევცვალო. |
| c2 | 100% | 0/2 | |
| c3 | 60% | 1/2 | |
| c4 | 86% | 1/3 | ისინი სქი ვარკვევდი მეილზე მომივა. |
| Mean | **83%** | **2/10** | ~1.2 s per file |

c4 check: reference `esim ის qr კოდი email ზე მომივა` = 7 words; hypothesis 5 words, only `მომივა` matches, so 6 edits / 7 = 86%. Azure Giorgi TTS: first audio 0.6-1.05 s, total 1.4-1.6 s per reply.

**Scribe results (run 2026-10-06, `runs/stt_compare_20261006-154451.json`). WER / terms found:**

| File | Azure | Scribe v2 | Scribe v2 + 18 keyterms |
|---|---|---|---|
| q1 (`როუმინგი`) | 50% / 0/1 | 125% / 0/1 ("აა, რაღაც 1000 ევრო პაში") | 75% / 0/1 |
| c1 (API key) | 120% / 0/2 | **20%** / 1/2 ("API-ს კი როგორ შევცვალო?") | 40% / 0/2 ("BPI-ს კი ...") |
| c2 (API key) | 100% / 0/2 | 100% / 0/2 | 100% / 0/2 |
| c3 (iPhone) | 60% / 1/2 | 20% / 1/2 | **0%** / 2/2 (exact) |
| c4 (eSIM, QR, email) | 86% / 1/3 | 100% / 0/3 | **14%** / 2/3 ("SIM-ის QR კოდი email-ზე მომივა?") |
| **Mean** | 83%, 2/10, 1.3 s | 73%, 2/10, 1.8 s | **46%**, 4/10, 1.5 s |

What to take from it (and what not):
- **Keyterms gave the biggest single gain** (73% -> 46%, with the same model). Changing one variable per column is what lets you say that.
- **Biasing can pull toward the wrong Latin word.** `API` was not a keyterm (on purpose), plain Scribe got it, and with keyterms on it became `BPI`: pushing the recognizer toward Latin spellings also pushed a word that wasn't in the list. Biasing is not free.
- **Scribe isn't uniformly better:** q1, a Georgian loanword, got *worse* (50% -> 125%; insertions again).
- **Strict scoring misses near-hits:** c4's `SIM` instead of `eSIM` counts as a miss though the graph could use it. A looser term matcher would show 3/3. Decide such rules before looking at results.
- **5 files, one speaker, one session:** an indication, not proof. Azure's mean is unchanged from the 2026-10-03 run (83%).

**TTS (run 2026-10-06, `runs/tts_compare_20261006-160112.json`; 934 characters per provider; Roman's blind rating of 20 clips):**

| Provider | Pronunciation | Naturalness | First audio (median) | Whole reply (median) |
|---|---|---|---|---|
| Azure ka-GE-GiorgiNeural | 2.3 | 1.6 | 0.74 s | 1.23 s |
| ElevenLabs eleven_v4_turbo, voice "Brian" | 4.8 | 3.9 | 0.62 s | 3.78 s |

ElevenLabs won on all 10 sentences. Caveats: one rater; and the two voices differ in timbre, so blinding hides *which provider* made a clip, not the fact that two different voices alternate (the rater can still learn "the deeper one is B"). Gender was matched (male) but timbre can't be.
- **Latency lesson:** first audio is similar (0.62 vs 0.74 s), but `voice.py` plays only after the *whole* file has arrived, so ElevenLabs currently adds about 2.5 s of silence per turn (3.78 - 1.23). Streaming playback (not implemented) would make first audio the number that counts. See first-byte vs finish latency in [How speech services work](2026-10-02-how-speech-services-work.md).
- Quality vs latency is now a real trade-off: much better voice, slower whole reply until playback streams.

## 3. How the pieces fit

Fixed inputs (recordings with known text, FAQ sentences) -> each provider alone -> normalized text -> WER + term recall (STT) or clips -> blind ratings + timings (TTS) -> one table. Only the provider differs between columns.

## 4. Related tools

- **`jiwer`** (`pip install jiwer`): standard WER/CER library (RapidFuzz edit distance, text transforms). Not installed here; our function is for learning, and I confirmed `wer()` usage from its README.
- **Hugging Face `evaluate`:** wraps jiwer, used in the HF audio course.
- **CER (character error rate):** better for agglutinative languages like Georgian where one wrong suffix makes a whole word wrong; worth adding.
- **UTMOS / automatic MOS predictors, MUSHRA tests:** automatic or more sensitive alternatives to human MOS. Not used; too heavy for one listener.

## 5. Hands-on exercises

1. Compute c4's WER by hand with the DP table (7 reference rows x 5 hypothesis columns). Check: bottom-right cell is 6; then `.venv/bin/python -c "import compare_speech as c; print(c.wer('eSIM-ის QR კოდი email-ზე მომივა?','ისინი სქი ვარკვევდი მეილზე მომივა.'))"` prints 0.857...
2. Run `.venv/bin/python compare_speech.py stt --wav audio/c1.wav` (Azure column works without a key; Scribe rows show the "key not set" error). Explain the WER and terms numbers on that row.
3. Make WER exceed 100% on purpose: `wer("a b", "x y z w")`. Check: 2.0 (2 substitutions + 2 insertions over 2 words).
4. Change `words()` to keep punctuation, re-run exercise 1's hypothesis `"...მომივა."` and see the score change. Explains why normalization must be identical for all providers.
5. Design two more recordings with **no** keyterms in the list (e.g. everyday Georgian with one English word not in `KEYTERMS`). Write the reference and term-forms dict in the `RECORDINGS` style. Check: for each term, would a Georgian-script spelling count?
6. Open `runs/stt_compare_20261006-154451.json` and find the c1 rows. Check: Scribe's transcript with and without keyterms differ in one word (`API-ს` vs `BPI-ს`). Then write a looser `terms_found` rule that would count `SIM` for `eSIM` and rerun the scoring on the saved JSON; say what it changes.

## 6. Self-check

1. Why is WER an edit distance and what does each cell of the table mean?
2. Why can WER be above 100%?
3. Why normalize, and why the same way for every provider?
4. What does term recall catch that WER doesn't?
5. Why were `API` and `key` left out of the keyterms?
6. Why shuffle clips and match the voice gender in the TTS rating? What can't you claim from 10 sentences and one rater?

<details><summary>Answers</summary>

1. WER needs the minimum number of word edits; cell `[i][j]` is the cheapest way to turn the first j hypothesis words into the first i reference words.
2. It divides by reference length, but insertions add errors without adding reference words.
3. Case/punctuation differences aren't recognition errors; unequal rules would favour a provider.
4. Whether the words that matter (eSIM, QR) survived, accepting Georgian spellings.
5. They appear in the test recordings; adding them is leakage and would inflate Scribe's score.
6. Shuffling hides the provider from the rater; matching gender removes an obvious tell. Not claimable: statistical significance or "better for everyone"; it's one listener on 10 sentences.

</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-6 | 1 hr |
| B. Another AI tutor | WER/MOS theory and the leakage argument | 30 min |
| C. Primary docs | Definitions and a standard tool | 1 hr |
| D. Video | Not verified | - |

**A. Prompt:**
> Walk me through learning/notes/2026-10-04-evaluating-speech-providers.md. Do exercises 1-5 one at a time: let me fill the DP table, then verify with code. Then quiz me on the self-check, including why API and key were excluded from the keyterms.

**B. NotebookLM loaded with the C links, or ChatGPT/Gemini.** Prompt:
> Using only these sources, explain word error rate as word-level Levenshtein distance with a worked DP table, why it can exceed 100%, how MOS tests work, and why test-set leakage matters when tuning with keyterms. Quiz me with 5 questions. Sources: https://en.wikipedia.org/wiki/Word_error_rate, https://en.wikipedia.org/wiki/Levenshtein_distance, https://huggingface.co/learn/audio-course/chapter5/evaluation, https://github.com/jitsi/jiwer, https://en.wikipedia.org/wiki/Mean_opinion_score, https://elevenlabs.io/docs/capabilities/speech-to-text

**C. Docs (opened 2026-10-04):**
- [Wikipedia, Word error rate](https://en.wikipedia.org/wiki/Word_error_rate): formula; states WER can exceed 1.0.
- [Wikipedia, Levenshtein distance](https://en.wikipedia.org/wiki/Levenshtein_distance): DP matrix and the memory optimization.
- [Hugging Face Audio Course, "Evaluation metrics for ASR"](https://huggingface.co/learn/audio-course/chapter5/evaluation): WER with jiwer and the effect of normalization.
- [jiwer on GitHub](https://github.com/jitsi/jiwer): the standard WER package.
- [Wikipedia, Mean opinion score](https://en.wikipedia.org/wiki/Mean_opinion_score): 1-5 scale, ACR, ITU-T P.800 (I did not open the ITU standard itself).
- [ElevenLabs speech-to-text](https://elevenlabs.io/docs/capabilities/speech-to-text) (opened 2026-10-02) and the [API reference](https://elevenlabs.io/docs/api-reference/speech-to-text/convert): keyterm limits.

**D. Video:** my searches for WER, Levenshtein and MOS returned articles and papers, so I couldn't confirm any video or course. Search terms: "Levenshtein distance dynamic programming explained", "word error rate explained", "mean opinion score speech quality".
