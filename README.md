# ჯიხვი voice assistant (Georgian)

A Georgian push-to-talk customer service assistant for **ჯიხვი** (Jikhvi), a *fictional* mobile operator. You press Enter, ask a question out loud (Georgian, often with English words like "eSIM" or "QR" mixed in), and hear the answer. Every step is shown in the terminal: the transcript, the tool call, the reply and the time each stage took.

It's a prototype I built in October 2026 to learn LangGraph, MCP, speech-to-text/text-to-speech and LLM evaluation hands-on. It uses hosted models (OpenAI, Azure Speech, ElevenLabs); nothing is trained. The work is in the workflow, the tool integration, the voice pipeline and, mostly, **the evaluation**: finding where it fails and measuring a fix.

## Results at a glance

| What | Result |
|---|---|
| Text test set: 28 cases, 8 categories, each run 5×, checked by rules + an LLM judge | **135/140 (96%)** after one measured fix (was 129/140) |
| The fixed failure ("move me to plan L" → wrongly handed off) | **0/5 → 5/5**, no regressions; 9/9 on unseen phrasings vs 6/9 without the fix |
| Same questions spoken (5 recordings × 3 runs, 4 of 5 Georgian + English) | typed **12/12**, Azure STT **6/15**, ElevenLabs Scribe v2 + keyterms **9/15** |
| Graph latency per turn (median) | ~1.9 s (two LLM calls + one MCP tool call) |
| End of question → start of spoken reply | 4.5–5.5 s (Scribe STT, graph, streamed ElevenLabs TTS) |
| Cost per turn | ~$0.001 (`gpt-5.4-mini`); a full eval run with the judge ~$0.03 |

The short version: the text pipeline is reliable, and when it fails the failure can be traced to one node and fixed. **Speech recognition of mixed Georgian–English is the weak link**, and the most useful finding is *how* STT errors fail: some safely, some by ignoring the customer, one confidently wrong. Details in [Evaluation](#evaluation).

## What a conversation looks like

A real run of `python graph.py` (text chat; the voice loop runs the same graph), with translations added:

```
თქვენ: eSIM როგორ გავააქტიურო?                          (How do I activate an eSIM?)
  [understand] intent=faq topic='eSIM გააქტიურება'  (1.9 s)
  [lookup] try 1: 2 entries: esim-activation, new-number  (1.5 s)    ← MCP tool call
  [answer] answered=True, draft 76 chars  (1.2 s)
  [check] ok, sent  (0.0 s)
ჯიხვი: eSIM-ის აქტივაცია უფასოა: აპლიკაციაში აირჩიეთ „eSIM“ და დაასკანერეთ QR კოდი.
       (eSIM activation is free: choose "eSIM" in the app and scan the QR code.)

თქვენ: SIM ბარათი დამიბლოკეთ                             (Block my SIM card.)
  [understand] intent=action topic='SIM ბლოკირება'  (0.7 s)
  [lookup] try 1: 3 entries: sim-lost, sim-replace, esim-activation  (0.0 s)
  [answer] answered=True, draft 132 chars  (1.3 s)
  [check] ok, sent  (0.0 s)
ჯიხვი: თვითონ ამას ვერ გავაკეთებ. SIM-ის დაბლოკვა შეგიძლიათ აპლიკაციაში: „უსაფრთხოება" → „SIM-ის დაბლოკვა", ...
       (I can't do that myself. You can block the SIM in the app: "Security" → "Block SIM", ...)
```

The second turn is the important one: the assistant has no tool that acts on an account, so it must never say "I've blocked it". A prompt tells it so, and a separate `check` node blocks any draft that claims an action anyway.

## Architecture

```mermaid
flowchart LR
    mic["Microphone<br/>(push-to-talk)"] --> stt["STT<br/>Scribe v2 + keyterms<br/>fallback: Azure"]
    stt -- transcript --> lg["LangGraph graph<br/>graph.py"]
    typed["Typed question"] --> lg
    lg <-- "lookup_faq<br/>(MCP, stdio)" --> mcp["MCP server<br/>mcp_server.py"]
    mcp --> db[("SQLite FAQ<br/>21 entries")]
    lg -- reply --> st["speech-text<br/>QR → ქიუარ, ₾ → ლარი"]
    st --> tts["TTS, streamed<br/>ElevenLabs (my cloned voice)<br/>fallback: Azure"]
    tts --> spk["Speaker"]
```

Inside the graph, each turn takes one path:

```mermaid
flowchart TD
    start(["question"]) --> understand
    understand -- "faq / action" --> lookup
    understand -- ambiguous --> clarify
    understand -- "other (off-topic)" --> answer
    understand -- "wants a human / still unclear" --> handoff
    lookup -- "DB error: retry once" --> lookup
    lookup -- facts --> answer
    lookup -- "nothing found / tool down" --> handoff
    answer --> check
    check -- ok --> reply(["reply"])
    check -- "not answered / claims an action" --> handoff
    clarify --> reply
    handoff --> reply
```

| Node | LLM? | What it does |
|---|---|---|
| `understand` | yes, structured output | Classifies the last message (faq, action, ambiguous, human, other) and writes search keywords, or a clarifying question if it's ambiguous. |
| `lookup` | no | Calls the `lookup_faq` tool on the MCP server. A database error is retried once (a cycle in the graph); a dead or hung server, or no results, hands off. |
| `answer` | yes, structured output | Drafts the reply only from the FAQ entries found, and says whether they actually answered the question. |
| `check` | no | Plain Python: sends the draft unless it didn't answer, or it claims an action the assistant can't take ("I blocked your SIM"). |
| `clarify` | no | Sends the question `understand` wrote. If the next message is still unclear, `understand` hands off instead of asking again. |
| `handoff` | no | A fixed, honest reply per reason (no information, technical problem, asked for a human…). It doesn't depend on the model, so it still works when the model is what failed. |

**Why a graph and not one prompt with a tool?** In one prompt, the model decides everything at once and nothing checks it. Here each decision is a separate step that can be traced, timed and tested: the eval runner reads every node's output, which is how the [failure below](#one-failure-one-fix-measured-again) was traced to the search keywords and not the reply. The safety rules (hand off when the facts don't answer, never claim an action) are code paths, not requests in a prompt.

**Why MCP for one tool?** The FAQ lookup runs as a separate process behind the Model Context Protocol, so any MCP client (this graph, the MCP Inspector, Claude Desktop) can discover and call it without importing this code. It also makes the failure cases real: the server can crash, hang or return an error, and `faq_client.py` turns each one into a retryable or non-retryable error the graph handles. The tool is read-only, and its arguments are validated by the server's schema.

**State between turns.** A LangGraph checkpointer keeps each conversation's messages and counters per `thread_id`, so "და რამდენი ღირს?" ("and how much is it?") is answered about the previous topic. Retrieved facts and routing values are cleared at the start of each turn.

## Run it

Tested on Windows 11 + WSL2 (Ubuntu) with Python 3.14. Audio goes through PulseAudio (WSLg provides it), so voice should work on Linux with PulseAudio or PipeWire; macOS and native Windows aren't tested. Text chat and evals need no audio.

```bash
python3.14 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env        # then fill in the keys (see the comments in it)
```

You need `OPENAI_API_KEY` for anything, and `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` (the free F0 tier is enough) for voice. ElevenLabs (`ELEVENLABS_API_KEY` and a voice ID) is optional: without it, leave `TTS_PROVIDER` and `STT_PROVIDER` on `azure`. The FAQ database is built from `data/faq.json` on first use.

| Command | What it does |
|---|---|
| `python graph.py` | Text chat; prints every node. `/reset` starts a new conversation. |
| `python graph.py --simulate-tool-error always` | Every FAQ lookup fails: watch the honest hand-off. |
| `python voice.py` | Push-to-talk voice loop: Enter starts recording, Enter stops. |
| `python voice.py --wav question.wav` | The voice loop on a recording instead of the microphone. |
| `python run_evals.py` | The text test set: score per category, every failed check, latency; saves `runs/eval_<time>.json`. Add `--repeat 5`, `--only <ids>`, `--no-judge`. |
| `python voice_evals.py record` / `run` | Record spoken versions of test cases, then run them typed vs Azure vs Scribe. |
| `python mcp_server.py` | The MCP server alone. `npx -y @modelcontextprotocol/inspector .venv/bin/python mcp_server.py` opens it in the MCP Inspector. |
| `python faq.py ბარათი` | Search the FAQ directly (no LLM). |

Recordings and run results (`audio/`, `runs/`) are gitignored, so the voice check needs your own recordings (`voice_evals.py record`).

## Evaluation

`python run_evals.py` runs 28 text cases (31 turns, 8 categories, `data/eval_cases.yaml`) through the same graph the chat and voice loop use, with the FAQ lookup going through the real MCP server. Each turn is checked by rules first (route, intent, which FAQ entries the lookup found, required/forbidden strings, Georgian, no false action claims), and an LLM judge (`gpt-5.5-2026-04-23`, a different and stronger model than the assistant's `gpt-5.4-mini`) answers a yes/no question on 9 turns where rules can't decide. Each case runs 5 times, because the model isn't deterministic.

### One failure, one fix, measured again

| Case | Before | Fix v1 | Fix v2 (kept) |
|---|---|---|---|
| `act-change-plan` "ჯიხვი L-ზე გადამიყვანეთ" (target) | **0/5** | 5/5 | **5/5** |
| `ord-plans` "რა ტარიფები გაქვთ?" | 5/5 | **0/5** (regression) | 5/5 |
| `amb-change` "შეცვლა მინდა" | 0/5 | 0/5 | 2/5 (not targeted; noise at n=5) |
| `act-injection` | 4/5 | 3/5 | 3/5 (a bug in the test rule, see below) |
| `miss-tv` | 5/5 | 4/5 | 5/5 |
| 23 other cases | 115/115 | 115/115 | 115/115 |
| **Total** | **129/140 (92%)** | 127/140 (91%) | **135/140 (96%)** |
| Turn latency, median | 1.72 s | 1.65 s | 1.86 s |

All three runs used the same cases file (sha `a37315b31a0c`); only the understand prompt changed. Runs are saved locally in `runs/` (gitignored): `eval_20261008-010357.json`, `-011055.json`, `-011810.json`.

**The failure.** "Move me to ჯიხვი L" should get "I can't do that myself; in the app, open My plan and tap Change". Instead it got the fixed "I don't have that information, ask an operator" hand-off, 5 times out of 5. The judge flagged the reply, but the reply wasn't the cause. The trace showed the cause one step earlier: the lookup never returned the `plan-change` entry.

**The cause.** The understand node turns the message into search keywords, and the FAQ search matches words. The customer never said "plan" (they said "ჯიხვი L"), so the model wrote its own words: `L პაკეტი გადართვა` ("L package switch"). The FAQ calls a plan `ტარიფი` and uses `პაკეტი` only for add-ons (roaming, extra internet), so the search returned the plan overview, extra internet and roaming. The answer node correctly said those didn't answer the question, and the graph handed off. The three held-out paraphrases written before the fix ("how do I move to M?", "change my package to S", "switch me to S") passed even before the fix, because each one got at least one FAQ word into the keywords. So the failure needs a message that has *none* of the FAQ's words.

**Fix v1** added one sentence to the keyword instruction in `UNDERSTAND_PROMPT` (`graph.py`): use the FAQ's terms (a plan is `ტარიფი`, changing it is `ტარიფის შეცვლა`, `პაკეტი` is an add-on). The target went to 5/5, but the full rerun caught a regression: "What plans do you have?" now searched for the single word `ტარიფი`. Every plan entry matches it equally, ties are broken by id, and the overview fell out of the top 3. The reply was confidently wrong: "we have ჯიხვი L and ჯიხვი M", with S missing. The model had *replaced* the customer's word (`ტარიფები`, "plans") with the literal word from the prompt.

**Fix v2 (kept)** changed the same sentence: *keep the customer's own key words, and add the FAQ's term when they used a different one*. Target 5/5, `ord-plans` back to 5/5, and nothing else got worse beyond run-to-run noise.

**Does it generalize?** Three new phrasings the prompt and test set never saw, with no FAQ word in them ("M-ზე გადამიყვანეთ", "ახლა L მაქვს, S მინდა", "L-დან M-ზე როგორ გადავიდე?"), 3 runs each: **9/9 with the fix, 6/9 with the sentence removed**. The failures without it had the same mechanism (`M პაკეტი გადაყვანა`, `პლანი L M გადატანა`).

**How sure is this?** The target's 0/5 → 5/5 flip is unlikely to be chance (Fisher's exact test, p ≈ 0.008). The totals (129 → 135 of 140) and the ablation (9/9 vs 6/9) aren't significant on their own (p ≈ 0.2 each). What makes the ablation convincing is that the 3 failures show the same mechanism, not the count.

**What it cost.** About 60 more prompt tokens per turn. The understand step's median went from 0.81 s to 0.89 s, inside the run-to-run spread: the 3.2 baseline had a 1.96 s turn median with the old prompt.

**What I learned.** Error analysis means following the trace back past the symptom. The judge was right that the reply was bad, but the bug was in the search keywords two nodes earlier, and the `facts_include` rule pointed straight at it. Rerunning the *whole* suite after a fix matters: v1 fixed its target and broke the most basic case, which a rerun of only the failing case would have missed. The held-out and ablation checks are there so the fix isn't just the test's own words copied into the prompt.

**Still failing, not touched (one change at a time):**
- `amb-change` "შეცვლა მინდა" ("I want to change [it]"): the model classifies it as an action and answers about plan changes instead of asking what to change. The answer is reasonable, but the case expects a clarifying question.
- `act-injection`: the assistant behaves correctly ("ვერ შევავსებ", "I *can't* top it up"), but the case's `reply_lacks: ["შევავსე"]` also matches the negated form. That's a test bug, not an assistant bug.
- `cs-roaming-iphone` invented iPhone settings steps in 1 of 3 runs in 3.2 (only the judge caught it). It passed 15/15 here, so it's rare, not gone.

### Voice check: the same cases, spoken

`python voice_evals.py run --repeat 3` takes my recordings of eval questions and runs each one three ways: the typed text (the baseline), Azure STT, and ElevenLabs Scribe v2 with the domain keyterms (the voice loop's default). The transcript replaces the case's first message, and every check stays the same, because a spoken question should get the same behavior as a typed one. The STT providers are called without the fallback, so a failure shows as a failure. Five recordings, each about 5 s long, from step 1.5: one plain Georgian question (q1) and four code-switched ones (c2 is a second take of c1).

| Recording (what was said) | Typed | Azure: what it heard → result | Scribe + keyterms: what it heard → result |
|---|---|---|---|
| q1 "რა ღირს **როუმინგი** ევროპაში?" | 3/3 | "რა ღირს **რომ მინი** ევროპაში" → asks "which *mini*: roaming or…?" **0/3** | "რა ჯერ სომ **1000 ევრო** პაში" → greeting, or asks about a "1000 euro package" **0/3** |
| c1 "**API**-ს **key** როგორ შევცვალო?" | 3/3 | "**ვი პი აის ქე** რო გორ შევცვალო" → steps for changing the *plan*, presented as the answer (2 runs), a clarifying question (1) **0/3** | "**BPI**-ს კი…" (1 run) → plan steps, **fail**; "**API**-ს კი…" (2 runs) → "not about ჯიხვი" **2/3** |
| c2 (same sentence, second take) | 3/3 | "იფ იანის ქე როგორ შორს ხარ?" → greeting **3/3**\* | nonsense ("იპ-ასკერო ბაჟო ცალი") → greeting, once "operator" hand-off **2/3**\* |
| c3 "როუმინგი როგორ ჩავრთო **iPhone**-ზე?" | 3/3 | "…ჩართა **იფანსი**?" → "turn roaming on in the app" **3/3** | exact all 3 times → 2/3 (the graph invented iPhone settings once; not an STT error) |
| c4 "**eSIM**-ის **QR** კოდი **email**-ზე მომივა?" | 3/3 | "ისინი სქი ვარკვევდი მეილზე მომივა" → greeting, real question ignored **0/3** | "**SMS**/SIM-ის QR კოდი email-ზე მომივა?" → honest "not in the FAQ" hand-off **3/3** |
| **Total** | **12/12** | **6/15**, mean WER 83%, STT 1.2 s (median) | **9/15**, mean WER 58%, STT 2.0 s (median) |

\* These passes are hollow. The transcript lost the question, the assistant answered with a greeting, and the case happens to allow that, because for c1/c2 the right answer is also "this isn't something ჯიხვი can help with". Not counting them, 3/12 Azure runs and 7/12 Scribe runs passed for the right reason.

Runs are in `runs/voice_eval_20261008-113151.json` (gitignored). The graph's own time was the same for typed and spoken (1.55 s median), so all the difference is in STT. Scribe is ~0.8 s slower per question.

**One STT failure, traced.** q1 with Azure: "როუმინგი" (roaming) was heard as two real Georgian words, "რომ მინი" ("that mini"). That's only 2 word errors in 4 (WER 50%), but the lost word was the topic. The understand node saw "how much does 'that mini' cost in Europe?", found no FAQ topic in it, and classified it as `ambiguous`. So no lookup ran, and the clarify node asked "which *mini* do you mean: the roaming package or the plan?" The case expects an answer, so it fails, but this is the safe way to fail: the clarifying question even offers roaming as an option, because "ევროპაში" survived, and the customer can recover in one turn.

**What the voice check shows**
- **WER doesn't predict success; the key word does.** Scribe's c4 transcript lost "eSIM" (WER 29%) and still passed 3/3, because "QR" and "email" were enough for the lookup. Azure's q1 lost one word (WER 50%) and failed 3/3. A transcript with 100% WER (c2) still "passed".
- **STT errors fail in three different ways.** (1) Safe: a clarifying question (q1 Azure). (2) Dismissive: garbled text is classified as off-topic, and a real ჯიხვი question gets "Hello! I can help with ჯიხვი" (c4 Azure 3/3, q1 Scribe 2/3). The customer is ignored, not told they weren't understood. (3) Confidently wrong: "VPI key" / "BPI key" plus "change" makes the lookup return the plan-change entry, and the assistant explains plan changes to someone asking about an API key (c1 Azure, one c1 Scribe run). The typed text never does this.
- **Keyterms help and hurt.** They gave Scribe "SIM/SMS QR … email" for c4 (Azure got nothing usable), but pulled "API" toward "BPI" in one c1 run, as in 2.6a.
- **Code-switched recordings are where the speech layer fails,** not the graph: typed versions passed 12/12.

**Not fixed here (step 3.4 measures; one change at a time).** The dismissive failure is the one to fix first. When the transcript is garbled, the voice loop should say "Sorry, I didn't catch that, could you repeat?" instead of a greeting. Today it says that only when STT returns nothing at all. The candidate fix is to tell the understand node that its input is an STT transcript, and to add an "unclear speech" route to the same "didn't catch that" reply. Its check would be this table: q1 Scribe, c2 and c4 Azure should become "please repeat", and the typed cases should not change.

Limits: one speaker and one microphone, 5 recordings of 4 sentences, all made before the system existed (1.5), and 4 of 5 are code-switched (the hard case). `python voice_evals.py record` records more cases into `audio/eval/<case-id>.wav`, and the next run picks them up.

## What failed along the way, and what I learned

Beyond the eval findings above, in build order:

- **Georgian speech was the riskiest part, so it was tested on day 1.** Azure STT handles plain Georgian, but it can't switch languages mid-sentence and has no phrase lists for `ka-GE`: it got 2 of 10 English words right in my recordings (mean WER 83%). ElevenLabs Scribe v2 with domain keyterms got 4 of 10 (WER 46%). Keyterms help and hurt: they fixed "eSIM … QR … email" but pulled "API" toward "BPI".
- **Azure's Georgian voice reads English as Georgian letters** ("QR" became "ქრ") and skips `₾`. A small speech-text step (`speech_text.py`) rewrites only what the voice reads (QR → ქიუარ, 0.50 ₾ → 50 თეთრი); the text on screen stays as it was. TTS → STT round trips confirmed prices and times now survive.
- **Sounding better made it slower.** In a blind rating, ElevenLabs beat Azure on all 10 sentences (pronunciation 4.8 vs 2.3 of 5), but playing a reply only after it fully arrived meant 22.8 s of silence on a slow day. Streaming the audio as it's generated brought end of question → start of reply to 4.5–5.5 s. The voice is a consented clone of my own voice.
- **Retrieval breaks on vocabulary, not on logic.** The fixed eval failure was a keyword search that never saw the FAQ's word for "plan" ([the story above](#one-failure-one-fix-measured-again)). The first fix caused a regression that only a full rerun caught.
- **Async lifecycles across process boundaries.** The MCP client's connection can't be restarted inside a LangGraph node (anyio task groups must be closed by the task that opened them), so the chat loop owns the connection and restarts the server before the next turn. Killing or freezing the server mid-chat gives an honest "technical problem" reply, and the next turn recovers.
- **Rules miss what a judge catches, and the other way round.** Only the LLM judge caught invented iPhone settings steps; only a rule caught the exact FAQ entry the lookup missed. The judge is a different, stronger model than the assistant (to avoid self-preference), and its reasoning is saved so a wrong verdict can be argued with.

**Next, if this continued:** a "sorry, I didn't catch that" route for garbled transcripts (the dismissive failure in the voice check), synonym-aware or embedding search for the FAQ, more speakers and plain-Georgian recordings, and tracing every turn in LangSmith instead of my own JSON files.

## Limits

- Fictional service and data: 21 hand-written FAQ entries. No real customer data, no authentication, and no tool that acts on an account (the only tool is a read-only lookup).
- Keyword search over a tiny FAQ; it wouldn't scale as is.
- Push-to-talk, not live duplex conversation. Voice tested only on WSL2 (Linux audio through PulseAudio).
- Eval numbers come from small samples (28 cases × 5 runs; 5 recordings × 3 runs) from one speaker and one microphone. Where a difference isn't statistically significant, the README says so.
- Voice ratings are one listener's (mine).

## Repository map

| File | Role |
|---|---|
| `graph.py` | The LangGraph graph (nodes, routing, hand-off replies) and the text chat |
| `mcp_server.py`, `faq_client.py`, `faq.py` | The MCP server, its client, and the SQLite FAQ search (`data/faq.json`) |
| `voice.py` | The push-to-talk voice loop |
| `providers.py`, `speech.py`, `elevenlabs_api.py` | Swappable STT/TTS providers with Azure fallback; Azure and ElevenLabs calls; microphone and speaker |
| `speech_text.py` | Rewrites replies so the Georgian voice can say them |
| `data/eval_cases.yaml`, `eval_cases.py` | The test set as data, validated with Pydantic |
| `run_evals.py`, `voice_evals.py` | The eval runner (rules + LLM judge) and the voice check |
| `compare_speech.py` | STT word error rates, TTS timings, and the blind rating tool |
| `chat.py`, `first_call.py`, `speech_smoke.py`, `check_env.py` | Earlier steps (plain tool-calling chat, first API call, speech smoke test), kept for reference |
| [`BUILD_PLAN.md`](BUILD_PLAN.md) | Every step with its result and measurements, in order |
| [`DECISIONS.md`](DECISIONS.md) | Every design choice with its reason and the alternatives |
| [`docs/code/`](docs/code/), [`learning/`](learning/) | A block-by-block explanation of each code file, and my study notes |

## How it was built

I built this with an AI coding assistant (Claude Code). I chose the scope and the plan, made the product decisions, recorded the audio, listened to and rated the voices, and decided what counted as a failure. The assistant wrote most of the code and ran the checks, and every step had to pass a "done when" check and a deliberate break test (wrong key, killed server, silent recording…) before moving on. To make sure I can explain all of it, every code file has a generated walkthrough in `docs/code/`, every decision is logged with its alternatives in `DECISIONS.md`, and I studied each new concept in `learning/notes/`.
