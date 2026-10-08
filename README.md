# ჯიხვი voice assistant (Georgian)

A weekend prototype: a Georgian push-to-talk customer service assistant for a fictional mobile operator (ჯიხვი), built with LangGraph, an MCP tool server, Azure/ElevenLabs speech and an eval suite. The full README (architecture, how to run it, voice results) is written in step 3.5 of [BUILD_PLAN.md](BUILD_PLAN.md). This page currently covers the evaluation.

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
