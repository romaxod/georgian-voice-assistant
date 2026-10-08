# STT error propagation in a cascaded voice pipeline, and how to evaluate it

Step 3.4, `voice_evals.py`. Sources opened 2026-10-08. Builds on [WER and term recall](2026-10-04-evaluating-speech-providers.md), [the cascaded pipeline and latency](2026-10-03-voice-latency-and-tts-normalization.md), [rule checks and judges](2026-10-08-running-evals-and-llm-judges.md) and [error analysis](2026-10-08-error-analysis-and-fixing-one-failure.md). Not repeated here.

## 1. What you're learning, and why it matters

**Problem:** the text evals (3.2) pass, but a user speaks. Does the assistant still work when the transcript is wrong? And which number tells you?

**Cascaded vs end-to-end.**
- **Cascaded:** audio -> STT -> text -> LLM/graph -> text -> TTS -> audio. This repo. Modular (swap a part, read the transcript in the middle, test the text half alone) but a mistake in STT reaches the graph, which cannot know its input is wrong. This is called **error propagation**.
- **End-to-end speech-to-speech:** one model takes audio and returns audio (e.g. OpenAI's realtime models). Lower latency, keeps tone and emotion, but no transcript in the middle to inspect, and tool use and guardrails are harder to control.

**Component metric vs task metric.**
- **WER** measures the STT component only: every word counts equally.
- **Task metrics** measure what the user cares about: **task success** (did the case pass), **intent accuracy**, **slot / concept error rate** (were the key entities and values right), **keyword/entity error rate** (our term recall). **SemDist** (Kim et al., Interspeech 2021) compares reference and hypothesis in a sentence-embedding space, to capture meaning rather than spelling.
- Old result: Wang, Acero & Chelba (2003) got up to 17% lower slot understanding error with a recognizer that had 46% *higher* WER. Better words are not always better understanding.

**This repo's numbers (3 repeats, 5 recordings, one speaker).**

| source | passed | mean WER | STT median | graph median |
|---|---|---|---|---|
| typed (baseline) | 12/12 | 0 | - | 1.55 s |
| Azure ka-GE | 6/15 | 83% | 1.21 s | 1.55 s |
| Scribe v2 + 18 keyterms | 9/15 | 58% | 1.96 s | 1.55 s |

WER does not predict success: c4 Scribe ("SMS QR კოდი email-ზე მომივა?", WER 29%) passed 3/3 because `QR` + `email` drove the lookup; q1 Azure (WER 50%) failed 3/3 because the one word that mattered (როუმინგი -> "რომ მინი") was lost. **Which** words are wrong matters more than **how many**.

**Paired evaluation.** Each recording runs typed and spoken in the same repeat, and the spoken run is labeled against its typed twin: `same`, `STT broke it` (typed passed, transcript differs), `graph (exact transcript)` (STT was perfect, graph still failed: not a speech problem), `STT error`. Only the speech layer changes between the pair, so the difference is attributable to it. This is the same one-variable-at-a-time idea as the provider comparison.

**Three failure modes seen downstream.**
1. **Safe:** garbled topic -> `intent=ambiguous` -> a clarifying question ("which mini?"). Recoverable.
2. **Dismissive:** a real question misread as off-topic -> a greeting (c4 Azure 3/3, q1 Scribe 2/3). The user gets nothing and doesn't know why.
3. **Confidently wrong:** "VPI/BPI key ... შევცვალო" -> lookup returns the plan-change entry -> the assistant explains plan changes (c1 Azure 2/3). Worst for customer service: no sign anything went wrong.

**Mitigations from dialogue-systems practice** (none built yet; 3.5 candidates):
- **ASR confidence scores:** STT returns a score per word or utterance; low score -> reprompt or confirm. (Scribe and Azure expose word-level data; we don't use it.)
- **N-best hypotheses:** the top few transcripts, not one; the LLM or lookup can pick the one that makes sense. LLM-based ASR error correction takes the N-best list as input (Ma et al. 2023).
- **Explicit vs implicit confirmation:** explicit ("Did you say X?") only when a mistake is costly or hard to undo; implicit (restate it in the answer: "About roaming in Europe: ...") otherwise, and the user can correct you. Google's conversation-design guide has exactly this rule.
- **Reprompt ("didn't catch that, please repeat"):** a route for transcripts that look garbled. Google's guide for no-match: reflect what was heard, narrow the ask, escalate after repeated failures.
- **Tell the LLM its input is an ASR transcript** in the `understand` prompt: "may contain mishearings; Latin terms may be spelled in Georgian; if it makes no sense, say so rather than guess."
- **ASR-robust SLU:** train or prompt the understanding step on noisy transcripts.

**Hollow passes.** c2 was transcribed as nonsense ("იპ-ასკერო ბაჟო ცალი"), the graph greeted ("I can help with ჯიხვი"), and `cs-api-key` allows that outcome, so the case passed **for the wrong reason**. Excluding c2: Azure 3/12, Scribe 7/12. Guards:
- Don't allow broad outcomes (`greet`, `clarify`) on a case unless needed; or add a check the wrong behavior can't satisfy (`reply_has`/`facts_include` of the right fact).
- Paired labels: a pass with a transcript that differs a lot from the typed text deserves a look (show `heard` next to the verdict).
- Read samples of passes, not only failures.

**Small-sample honesty.** One speaker, 5 recordings, 3 repeats: "Scribe 9/15 vs Azure 6/15" is a hint, not a ranking (see Fisher/Wilson in the error-analysis note). The failure *modes* are the real finding.

## 2. In this repo

- `python voice_evals.py record [case-id ...]` (push-to-talk with `speech.Recorder`, play back, keep/redo -> `audio/eval/<case-id>.wav`).
- `python voice_evals.py run --repeat 3` -> `runs/voice_eval_20261008-113151.json`; `--no-judge` for rules only.
- Providers are called directly, no fallback (a fallback would hide which engine heard what). The first turn is replaced by the transcript; later turns stay typed. Empty transcript -> `not_heard`, graph not run, like `voice.py`. No TTS: it changes nothing that is checked.
- STT runs in `asyncio.to_thread` because the MCP client shares the event loop (see [async note](2026-10-03-python-async-await.md)).
- Break tests: silent wav -> `not_heard`; wav with unknown case id skipped; wrong ElevenLabs key -> one readable error per Scribe row, run completes.
- Replacing a turn: `model_copy(update=...)` skips validation, see the [Pydantic addition](2026-10-07-yaml-data-files-and-pydantic-validation.md).

## 3. How the pieces fit

```
wav -> STT (Azure | Scribe) -> transcript -> understand -> lookup -> answer -> checks (rules + judge)
typed text ------------------^ (baseline, same repeat)        compare pass/fail -> label
```

## 4. Related tools

- **Pipecat Evals** can run text mode (skips STT/TTS) or audio mode (synthesizes the user's voice, streams it through the agent's real STT). Our setup is a small version of audio mode with real recordings instead of synthetic voice.
- **Hosted voice-agent testers** (e.g. Hamming) simulate callers at scale; overkill here.
- **jiwer** for WER; **SemDist** or an LLM judge for meaning-level comparison of transcripts.

## 5. Hands-on exercises

1. Record the other cases: `python voice_evals.py record ord-plans act-block-sim act-change-plan`, then `python voice_evals.py run --repeat 1 --no-judge`. Check: new rows appear with `heard` vs `said` and a label each.
2. Find a hollow pass: open the JSON, list rows with `passed` true and `wer` > 0.5 (`python -c "import json;..."`). Check: you can name the outcome that let it pass.
3. Design the "unclear speech" fix on paper: when does the graph say "didn't catch that"? Success criterion from the table: c2 and c4 Azure should become *reprompt*, not greeting; typed 12/12 must stay 12/12; q1 Scribe must not regress. Write down what counts as a pass for a reprompt (new expected outcome?).
4. Make a hollow-pass-proof c2: which `reply_has` or outcome restriction would make the nonsense transcript fail?
5. Compare WER and pass rate per recording in one small table; is there a recording where lower WER means worse outcome?

## 6. Self-check: can you answer these without looking?

1. Why can WER be 50% and the run still fail, or 29% and pass?
2. What does the paired design isolate, and what does `graph (exact transcript)` tell you?
3. Name the three failure modes and rank them by risk for a real customer service.
4. What is a hollow pass and one guard against it?
5. Explicit vs implicit confirmation: when each?
6. Why is "Scribe beat Azure" not safe to claim?

<details><summary>Answers</summary>

1. WER counts all words equally; the outcome depends on whether the words the lookup/intent relies on survived (QR + email did; "როუმინგი" didn't).
2. Only the speech layer differs between the pair, so a pass-to-fail change is caused by STT. `graph (exact transcript)` = STT was exact but the graph still failed: not an STT problem.
3. Safe (clarify), dismissive (greeting for a real question), confidently wrong (wrong fact). The third is worst: the user is misled silently.
4. A check that passes for the wrong reason (c2: nonsense -> greeting, which the case allows). Guard: stricter expectations, or read passes whose transcript differs from the typed text.
5. Explicit when an error is costly or hard to undo; implicit (restate in the answer) otherwise.
6. One speaker, 5 recordings, 3 noisy repeats, keyterms tuned for the domain; and c2 is hollow.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | doing exercises 1-4 on your data | 1-2 h |
| B. Another AI tutor | WER vs SemDist, confidence/N-best concepts | 1 h |
| C. Primary docs and papers | citing evidence | 2 h |
| D. Video / course | architecture trade-offs, latency | 1-2 h |

**A.** Paste in a main session: "Read learning/notes/2026-10-08-stt-error-propagation-and-voice-evals.md and walk me through exercises 1-4 using voice_evals.py and runs/voice_eval_20261008-113151.json. Explain each result before moving on."

**B.** NotebookLM (add the C links as sources) or ChatGPT/Gemini. Prompt: "Using these sources: https://arxiv.org/abs/2104.02138, https://www.microsoft.com/en-us/research/?p=154834, https://developers.google.com/assistant/conversation-design/confirmations, https://arxiv.org/abs/2307.04172, explain why WER predicts downstream NLU success poorly, give 3 examples, and quiz me on confirmation strategies for a telecom support voice bot."

**C.**
- [Wang, Acero, Chelba 2003, "Is Word Error Rate a Good Indicator for Spoken Language Understanding Accuracy"](https://www.microsoft.com/en-us/research/?p=154834): the 46% worse WER / 17% better slot error result.
- [Kim et al. 2021, "Semantic Distance"](https://arxiv.org/abs/2104.02138): why WER misleads for intent/NER, and SemDist.
- [Skit.ai: "Evaluating an ASR in a Spoken Dialogue System"](https://tech.skit.ai/evaluating-an-asr-in-a-spoken-dialogue-system/): blog list of alternatives (concept accuracy, SemDist, task metrics).
- [Ma et al. 2023, "Can Generative Large Language Models Perform ASR Error Correction?"](https://arxiv.org/abs/2307.04172): LLM correction from N-best lists.
- [Google Conversation Design: Confirmations](https://developers.google.com/assistant/conversation-design/confirmations): explicit vs implicit, when.
- [Pipecat: evaluations overview](https://docs.pipecat.ai/pipecat/fundamentals/evaluations/overview): text mode vs audio mode testing.

**D.**
- Course: [Building AI Voice Agents for Production](https://www.deeplearning.ai/short-courses/building-ai-voice-agents-for-production) (DeepLearning.AI with LiveKit; Russ d'Sa, Shayne Parmelee, Nedelina Teneva; 1 h): modular pipeline vs real-time APIs, latency.
- Video: [What Is the Best Architecture for Voice AI Agents? Cascade vs Speech-to-Speech](https://www.youtube.com/watch?v=lMGIC6gXFvY) (Concretio, per YouTube oEmbed; I confirmed title and channel but did not watch it, so quality is unchecked).
- I did not find a verified video specifically on WER vs downstream task success; search "WER vs intent accuracy voice agent evaluation".

Checked: pages above opened 2026-10-08; the Harris et al. (IWSDS 2024) paper on ASR errors and response appropriateness appeared in search but its PDF was unreadable, so it is not listed.
