# Error analysis: finding the cause, fixing one thing, proving it

Date: 2026-10-08. Numbers are from step 3.3 (README "Evaluation", BUILD_PLAN 3.3). The p-values and intervals below I computed with plain Python (`math.comb`; scipy isn't installed here). Sources opened on 2026-10-08.

## 1. What you're learning, and why it matters

**Problem:** the eval says "act-change-plan fails 0/5". What do you change, and how do you know the change helped and broke nothing? Without a method you end up tweaking prompts until one run looks good.

**Error analysis** = read the failing runs, find *where* the pipeline went wrong, group failures, then fix the most worthwhile one.
- **Symptom vs cause.** The judge said "the reply doesn't tell the customer how to change the plan". That is the symptom. The per-node trace showed the cause two nodes earlier: `understand` wrote the search topic `L პაკეტი გადართვა`; the FAQ says `ტარიფი` for plans, so `lookup` never returned `plan-change` (the `facts_include` rule showed this). `answer` then correctly said "nothing relevant" and the graph handed off. Fixing the reply text would have been fixing the wrong node. Method: walk the trace from the bad output backwards, and at each node ask "given its input, was its output reasonable?" The first node that fails that test is the cause.
- **Open coding / axial coding** (borrowed from qualitative research; Hamel Husain and Shreya Shankar teach it for LLM apps). *Open coding*: read many traces and write a free-text note on each problem, no categories yet. *Axial coding*: group the notes into a **failure taxonomy** (e.g. "search keywords miss FAQ vocabulary", "invented steps", "strict test"). Then count each category. Their guide suggests starting with about 100 traces, and stopping when new traces teach nothing new ("saturation"). We had 3 failing cases, so we did it by hand, but the habit is the same.
- **Picking which failure to fix.** Criteria used here: *frequency* (how often), *determinism* (0/5 means reproducible, so a before/after is measurable), *severity* (a customer's request is refused), *traceability* (cause found). `cs-roaming-iphone` (invented steps) is severe but rare (1/3, then 15/15), so a fix can't be measured. `amb-change` is arguably a too-strict expectation. `act-change-plan` won on determinism and traceability.

**Fix one variable at a time.** If you change the prompt and the model and the search together, you can't say which one helped. Here only one sentence in `UNDERSTAND_PROMPT` changed; the cases file sha (`a37315b31a0c`) was identical across all three runs, and the prompt sha changed `29d1bf528461 → 40484bef910f → c252e4e37535`.
- **Iterating on the same variable is fine** (v1 → v2 are two attempts at the same sentence). Adding a second variable (say, also changing the search scoring) is not.
- **Rerun the whole suite after each fix.** v1 fixed the target (0/5 → 5/5) and broke `ord-plans` ("რა ტარიფები გაქვთ?") 5/5 → 0/5. A rerun of only the target case would have shipped that. Aggregate went 129 → 127.
- **Prompts have side effects.** v1 said "use the FAQ's terms: a plan is `ტარიფი`". The model *replaced* the customer's word with the literal word from the prompt. A one-word query ties every plan entry (see the addition in the keyword-search note), the overview lost the tie, and the reply said "we have L and M" with S missing, marked `answered=true`: confidently wrong. v2: "keep the customer's own key words and *add* the FAQ's term". General lesson: examples and quoted words in a prompt get copied.

**Overfitting to the eval ("teaching to the test").** Goodhart's law: "when a measure becomes a target, it ceases to be a good measure." If you tune the prompt until your 28 cases pass, the pass rate says little about unseen customers. Defenses:
- **Held-out cases written before the fix** (basics in [the test-set note](2026-10-07-designing-an-llm-eval-test-set.md), contamination section). We added 3 paraphrases first. Honest surprise: they passed 5/5 *before* the fix, because each contained a FAQ word, so they could not show improvement. They did guard against regression. A good held-out case must have the failure's trigger (here: no FAQ word at all).
- **Ablation** (remove the change, see whether the failure returns) is a causal check. We made 3 *unseen* phrasings with no FAQ word, 3 runs each, `--no-judge`, checking `facts_include: plan-change`: 9/9 with the sentence, 6/9 without. The failures had the same mechanism (topic `M პაკეტი გადაყვანა`, `პლანი L M გადატანა`), which is what convinces more than the count does.

**Is a before/after difference real at n=5?** (noise basics: [running-evals note](2026-10-08-running-evals-and-llm-judges.md), noise section.)
- **Fisher's exact test** asks: if both versions had the same true pass rate, how likely is a split at least this lopsided? Fix the totals (5 passes of 10 runs, 5 per group). Number of ways to choose which 5 runs passed: C(10,5) = 252. 0/5 vs 5/5 happens in 1 way, and the mirror 5/5 vs 0/5 in 1 way: two-sided p = 2/252 = **0.0079**. Checked in code.
- 0/5 vs 2/5 (amb-change): p = **0.444**. Not distinguishable from noise, so don't claim it. 0/5 vs 4/5: p = 0.048 (borderline).
- **Wilson interval** (a 95% range for the true pass rate, behaves at 0 and 5/5 where the textbook normal interval gives width 0): 0/5 → 0.00-0.43; 5/5 → 0.57-1.00 (these don't overlap, consistent with Fisher); 2/5 → 0.12-0.77 (huge). Ablation 9/9 → 0.70-1.00 vs 6/9 → 0.35-0.88: overlap, and Fisher p = **0.21**. Honest reading: the ablation count alone is suggestive, the shared failure mechanism is the real evidence.
- **Aggregate 129 → 135 is weaker evidence than the per-case flip.** Fisher on 129/140 vs 135/140 gives p ≈ 0.20, and that treats 140 runs as independent when they are 28 cases × 5, so it flatters the result. The aggregate also hides that v1 *lost* one case while gaining another. Prefer: "this case went 0/5 → 5/5, mechanism identified, no other case moved beyond noise".
- **Repeats vs cost.** Each run is ~$0.03 and ~1 min (28 cases, from the 3.2 numbers scaled), so `--repeat 5` is cheap; 20 repeats of just the target and neighbors is cheaper still. For a 5-point shift you need far more than 5 runs; for a 0/5 → 5/5 flip you don't. Spend repeats on the cases that matter.

**Test bugs vs system bugs.** `act-injection` fails sometimes, but the assistant said "ვერ შევავსებ" ("I can't top it up"), which is correct. The rule `reply_lacks: ["შევავსე", "შეგივსე"]` also matches the negated forms (same false-positive class as the regex in [failure-handling note](2026-10-03-failure-handling-and-guardrails.md)). How to tell: read the reply yourself; if a reasonable human would accept it, the check is wrong. Fix it in a **separate, labeled change** (and rerun), otherwise the pass rate moves for two reasons and the before/after is unreadable. It was left unfixed in 3.3 on purpose.

## 2. In this repo

- `python run_evals.py --repeat 5` → saved `runs/eval_<time>.json` (per-node output, topic, FAQ ids found, checks). Baseline `eval_20261008-010357.json`. Look at the `topic` and found ids of failing turns first.
- The fix: one sentence in `UNDERSTAND_PROMPT` in `graph.py`. Cases: `data/eval_cases.yaml` (28). Ablation used a scratch copy of the cases file with `--only`, because `run_evals` enforces ≥3 cases per category on any file.
- Cost: understand median 0.81 → 0.89 s, turn median 1.72 → 1.86 s, inside run-to-run spread.

## 3. How the pieces fit

```
failing case -> read trace backwards -> cause node (understand topic)
   -> held-out cases first -> baseline on SAME cases file -> ONE change
   -> full rerun (regressions?) -> ablation on unseen inputs -> compare per-case, with stats
```

## 4. Related tools

- LangSmith / Langfuse / Braintrust trace viewers and annotation queues do the "read traces, write notes" step with a UI; Hamel recommends even a custom simple viewer. We read JSON because 3 failures don't need more.
- `scipy.stats.fisher_exact` and `statsmodels` `proportion_confint(method="wilson")` for stats (not installed here, hence the by-hand code). Bootstrap/paired tests exist for larger suites.

## 5. Hands-on exercises

1. Open the baseline run JSON and find `act-change-plan`'s `topic` values and FAQ ids. Check: no `plan-change`.
2. Compute Fisher by hand: `C(10,5)=252`; the 0/5-vs-5/5 table has one arrangement per side, so `2/252`. Then verify: `python3 -c "from math import comb; print(2/comb(10,5))"` → 0.0079.
3. Write your own tiny `fisher(a,b,c,d)` with `math.comb` and reproduce 0.444 for 0/5 vs 2/5. Check: matches.
4. Reproduce the ablation: copy `data/eval_cases.yaml` to the scratchpad, add the 3 unseen phrasings with `facts_include: [plan-change]`, comment out the sentence in a scratch copy of the prompt (or `git stash` your own edit), run `--only ... --repeat 3 --no-judge`. Check: some topics lack ტარიფი/შეცვლა.
5. Fix the same failure **without touching the prompt** (e.g. add `პაკეტი`-to-plan synonyms in `faq.py` keywords for `plan-change`) and compare on the same cases. Check: which is more robust on the 3 unseen phrasings? (This is a learning exercise; the main session decides if it goes in the repo.)
6. Take `act-injection` and decide: is the reply right? Write the stricter rule you'd use instead (e.g. the judge's yes/no question) without applying it.

## 6. Self-check

1. Why was fixing the reply text the wrong move? 2. Why did v1 pass its target and still get rejected? 3. Why did the held-out cases pass before the fix, and what does that tell you? 4. What does p = 0.0079 mean, in words? 5. Why is "129 → 135" weak evidence? 6. How do you decide a failing check is a test bug?

<details><summary>Answers</summary>

1. The cause was the search keywords two nodes earlier; the reply was an honest response to bad facts. 2. A full rerun showed `ord-plans` 5/5 → 0/5: a regression the target-only rerun misses. 3. Each had a FAQ word, so they didn't trigger the failure: they protect against regressions but can't show the fix works; make held-out cases that contain the trigger. 4. If the old and new versions were equally good, a split this extreme would happen about 0.8% of the time. 5. Cases aren't independent (28 × 5 runs), p ≈ 0.20 even naively, and it hides one case lost and another gained. 6. Read the reply: if a reasonable human accepts it, the rule is too broad; fix in a separate labeled change.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Tracing the real run JSON, exercises 1-6 | 1 h |
| B. Another AI tutor | Statistics intuition (Fisher, Wilson) | 45 min |
| C. Primary docs | Error-analysis method, from the people who teach it | 2 h |
| D. Video / course | Open/axial coding demo | 1-2 h |

**A.** Paste: "Read learning/notes/2026-10-08-error-analysis-and-fixing-one-failure.md and runs/eval_20261008-010357.json. Walk me through exercises 1-6, one at a time, using the real files."

**B.** ChatGPT/Gemini, or NotebookLM loaded with the C links. Prompt: "Using https://hamel.dev/blog/posts/evals-faq/ and https://en.wikipedia.org/wiki/Fisher%27s_exact_test, explain open and axial coding for LLM failures, then Fisher's exact test with a 2x2 table of 0/5 vs 5/5 passes, and why a 129/140 vs 135/140 comparison is weaker evidence."

**C.**
- <https://hamel.dev/blog/posts/field-guide/>: Hamel Husain, "A Field Guide to Rapidly Improving AI Products"; read the error analysis section (a real-estate assistant went 33% → 95% after categorizing failures).
- <https://hamel.dev/blog/posts/evals-faq/>: "LLM Evals: Everything You Need to Know"; read open coding, axial coding ("the most important step") and trace-review volume. It does not cover statistics.
- <https://eugeneyan.com/writing/eval-process/>: Eugene Yan, "An LLM-as-Judge Won't Save The Product—Fixing Your Process Will" (April 2025): hypothesis-driven loop, looking at the data.
- <https://en.wikipedia.org/wiki/Fisher%27s_exact_test> (tea-tasting example), <https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval> (Wilson section), <https://en.wikipedia.org/wiki/Goodhart%27s_law>.

**D.**
- Video: "Why AI evals are the hottest new skill for product builders" (Lenny's Podcast with Hamel Husain and Shreya Shankar), <https://youtu.be/BsWxPI9UM4c>; the show notes list error analysis at 16:51, "theoretical saturation" at 28:07, axial codes at 31:39 (<https://www.lennysnewsletter.com/p/why-ai-evals-are-the-hottest-new-skill>). Not watched; details from the page.
- Course: "AI Evals For Engineers & PMs" by Hamel Husain and Shreya Shankar on Maven, <https://maven.com/parlance-labs/evals>. It is paid ($4,200 on the page I opened, next cohort Oct 10 - Nov 21, 2026), so treat it as optional. Free alternative: their email course, <https://ai.hamel.dev/eval-course> (seen in search results, not opened).
- Statistics video: I did not verify a specific one; search "StatQuest p-values" and "Fisher's exact test explained".
