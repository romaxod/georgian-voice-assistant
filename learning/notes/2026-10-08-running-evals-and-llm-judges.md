# Running evals: rules, LLM judges, noise and latency

Step 3.2, `run_evals.py`. Sources opened 2026-10-08. Builds on [Designing an LLM eval test set](2026-10-07-designing-an-llm-eval-test-set.md) (the cases themselves). Line-by-line explanation of the runner is in `docs/code/run_evals.md`, not here.

## 1. What you're learning, and why it matters

**Problem: you have 25 cases and need one trustworthy number after every change, from a system that answers differently each time.** Four ideas make that work.

**A. Two kinds of check.**
- **Rule check**: plain code (`outcome == "answer"`, FAQ id in the results, `"15"` in the reply, ≥50% Georgian letters). Free, instant, same verdict every time. Use it wherever the answer is decidable.
- **LLM judge** ("LLM-as-a-judge"): a second model call that reads the conversation and answers a yes/no question such as "does the reply avoid inventing steps that are not in the FAQ?". Use it only where wording varies too much for code (paraphrased false claims, invented facts). Costs tokens, takes seconds, and is itself a model that can be wrong.
- **Offline eval = regression test**: you run a fixed set before shipping, not on live traffic. It catches "this used to work". It does not find problems you did not write a case for.
- **Comparable runs**: a score means nothing without knowing what produced it. Each results file in `runs/` stores git commit (+`changes` if dirty), model names, a short sha256 of the cases file and of all prompts, and the arguments. Two files with different `prompts_sha` differ by a prompt; same hashes means any difference is noise. Step 3.3 needs this for before/after.

**B. Judge reliability.** A judge has known biases (from Zheng et al. 2023 and Eugene Yan's summary):
- **Self-preference** (self-enhancement): a model rates its own style higher. Mitigation: judge with a *different, stronger* model than the one graded (`gpt-5.5` judges `gpt-5.4-mini`).
- **Position bias**: in pairwise "A or B?" the first answer wins too often. Mitigation: randomize order, or avoid pairs. We grade one reply, so it does not arise.
- **Verbosity bias**: longer replies look better. Mitigation: pass/fail on a specific behavior, not "how good is it?". Voice replies are short anyway.
- **Leniency**: judges tend to say yes. Mitigation: ask a question whose "yes" is checkable against data (the FAQ text is given to the judge), and *test* the judge on known-bad replies.
- Other mitigations we used: a **pinned dated snapshot** (`gpt-5.5-2026-04-23`) so an alias update cannot change verdicts silently; one behavior per question; **reasoning before verdict** (`Verdict{reasoning, passed}`, field order matters because the model writes in order); **reference data in the prompt** (the FAQ entries the assistant had); the transcript labeled as **data, not instructions** (case `act-injection` contains "forget your rules"); unparseable verdict = FAIL.
- **Validate the judge** like any classifier: hand-label replies, compare. Report **true-positive rate** (bad replies it catches) and **true-negative rate** (good replies it passes) separately, because plain agreement hides a judge that passes everything when failures are rare (Hamel Husain).

**C. Nondeterminism.** The same case can pass, fail, pass. Causes: sampling randomness, reasoning models (no temperature control to pin), and search variation (the model writes a different `topic`, so the lookup returns different entries). So run each case N times (`--repeat 3`) and report a pass rate. Two ways to summarize k runs of one case:
- **pass@k**: at least one of k succeeded. Right for "can it ever do this" (coding with retries).
- **pass^k** (tau-bench, Yao et al.): *all* k succeeded. Right for customer service: the customer gets one try, so consistency is the product. If a case passes with chance 2/3 per run, pass^3 is (2/3)³ ≈ 0.30 while pass@3 is ≈ 0.96.
- **Noise vs improvement**: with 25 cases one flipped case moves a single-run score 4 points; with 75 runs, one run moves it 1.3 points. A 92% to 94% change is inside the noise. Trust differences that are larger than run-to-run spread (repeat the *baseline* too), or that are the same cases flipping the same way every time.

**D. Latency.** Report **median** (p50, the typical turn) and a **tail** percentile (**p90/p95/p99**: the value 90/95/99% of turns beat). The mean is dragged by a few slow turns and describes nobody. Google's SRE book makes this point: 1% of requests can take 5 s while the average looks fine. In voice, one 6 s silence is what the caller remembers. **Per-node timing** (we record seconds per graph node from the stream) tells you where time goes: here understand ≈ 0.95 s, answer ≈ 1.03 s, lookup 0.02 s, so only LLM calls matter. **Why sequential**: parallel cases share the network, rate limits and the one MCP connection, so each turn gets slower and the numbers measure contention, not the graph.

## 2. In this repo

Real runs (2026-10-08):
- `python run_evals.py`: 24/25 cases, 137/140 checks, about 1 min, $0.03 graph cost.
- `python run_evals.py --repeat 3` (`runs/eval_20261008-004750.json`): 69/75 runs (92%). Turn latency median 1.96 s, p90 2.42 s, max 2.65 s. Judge: 24 calls, 9685 input + 2175 output tokens.
- Failures, all informative:
  - `amb-change` ("შეცვლა მინდა", "I want to change [it]") failed 3/3: the understand step labels it `intent=action` and never asks which thing. A real bug in the prompt, deterministic. Once the topic came back empty, the lookup rejected it and the result was `handoff:no_facts`.
  - `act-change-plan` failed 2/3: the model's keyword topics ("L პაკეტი გადაყვანა") did not retrieve the plan-change entry, so the answer said "not answered" and the graph handed off. A search-recall problem that is only sometimes triggered.
  - `cs-roaming-iphone` failed 1/3 *only on the judge*: the reply invented iPhone steps (Settings → Cellular → Data Roaming) not in the FAQ. Every rule passed it. This is why the judge exists, and why one run is not enough (it passed 2 of 3).
  - By the two summaries: pass@3 = 24/25 cases (only `amb-change` never passed), pass^3 = 22/25 (88%).
- Break tests: (a) the judge on a hand-written passive false claim "თქვენი SIM ბარათი უკვე დაბლოკილია" ("your SIM is already blocked"): the `FALSE_ACTION_CLAIM` regex returned `None`, the judge returned `passed=False`; an honest reply ("მე თავად ვერ დავბლოკავ…") got `passed=True`. That is a 2-sample judge validation. (b) `OPENAI_API_KEY=sk-wrong` printed "Error: the API key was rejected…" and exited 1: `AuthenticationError` stops the whole run (every case would fail identically), while rate-limit/connection errors fail only that turn.

## 3. How the pieces fit together

```
eval_cases.yaml -> per case: fresh graph + thread id (real MCP server)
   -> stream "updates": path, per-node seconds, reply, outcome
   -> rule checks (every turn) -> judge (only 8 turns with judge:)
   -> summary: score, failures, latency, cost -> runs/eval_<time>.json (+ git/prompt hashes)
```
Repeat N times, then compare two files whose meta differs only in what you changed.

## 4. Related tools

Checked 2026-10-08. All do "dataset + evaluators + report" and we used plain Python (no account, local JSON, every line explainable, and it can read graph internals like route and retry count):
- **LangSmith `evaluate()`**: takes a dataset (by name or id) and a list of evaluator functions, stores experiments you can compare in a UI. Closest upgrade path.
- **promptfoo**: open-source CLI/library for evals and red-teaming, declarative YAML.
- **pytest-style** (DeepEval and plain pytest): each case a test in CI; fails the build below a threshold.
- **OpenAI Evals**: open-source framework/registry; now centered on the OpenAI dashboard.
Anthropic's guide also lists three grader types: code-based (fast, brittle), model-based (flexible, needs calibration, costs more), human (gold standard, slow). Ours is the first two plus Roman reading failures.

## 5. Python pieces *(short)*

- `@dataclass` generates `__init__`/`__repr__` from annotated fields. A mutable default must be `field(default_factory=list)`, otherwise every instance would share one list (Python refuses `= []`). `dataclasses.asdict(obj)` converts to nested dicts for `json.dump`. A `@property` on a dataclass is a computed attribute (called without parentheses), not stored or serialized by `asdict`.
- `defaultdict(factory)`: reading a missing key creates it from `factory()` (e.g. `defaultdict(list)` for per-node seconds; a `lambda` returning a dict of zeros for per-category counters). `Counter(items).most_common(n)` counts and sorts by frequency (used for the most-failed checks).
- `statistics.median(xs)`; `statistics.quantiles(xs, n=100, method="inclusive")` returns 99 cut points, so index `p-1` is percentile p. `inclusive` treats the data as the whole population, so p90 never exceeds the max; with few samples that is the sane choice. Checked: `[1.9,2.0,1.8,2.4,2.65,1.7,2.1]` gives median 2.0, p90 2.5.
- `hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]` is a **content fingerprint**: any edit changes it; 12 hex chars (48 bits) is plenty to tell two files apart, not for security.
- `subprocess.run([...], capture_output=True, text=True, check=True)` runs a command, captures stdout/stderr as str, and raises `CalledProcessError` on non-zero exit. Used read-only for `git rev-parse --short HEAD` and `git status --porcelain` (empty output = clean). A list of args (no `shell=True`) avoids shell-quoting problems.

## 6. Hands-on exercises

1. `python run_evals.py --only amb-change --repeat 5`. Check: 5 runs, same failure each time; open the newest `runs/eval_*.json` and find the `understand` output (intent) for each run.
2. Compare `meta` of two files in `runs/` with a few lines of Python (`json.load`, print `meta["git"]`, `prompts_sha`). Check: change one word in a prompt, rerun `--only amb-price`, and watch `prompts_sha` change while `cases_sha` stays.
3. Write a judge question for `amb-change` that fails a reply which guesses what to change (hint: yes/no, "yes" = pass, one behavior). Add it as `judge:` in a copy of the YAML or in a scratch script. Check: it fails a guessing reply and passes a clarifying one.
4. Validate the judge: write 5 replies (3 bad, 2 good) for `act-block-sim` or a similar case, label them by hand, run the judge on each (use the break-test snippet pattern from the 3.2 session), and count TP rate and TN rate. Check: you can state "caught x/3 bad, passed y/2 good".
5. Run `python run_evals.py --repeat 3 --no-judge` twice. Check: the rule-only score differs between runs? That spread is your noise level.
6. Compute pass^3 and pass@3 from a `--repeat 3` file: per case, count runs passed. Check: they match the 22/25 and 24/25 above for the 20261008 file.

## 7. Self-check

1. When do you use a rule and when a judge?
2. Name three judge biases and one mitigation for each.
3. Why is the reasoning field placed before `passed`?
4. Why does overall agreement say little about a judge?
5. A case passes 2 of 3 runs. What are its pass@3 and its likely pass^3? Which matters for a phone bot?
6. After a prompt change the score goes 23/25 to 24/25. Is it better?
7. Why p90 and not the mean, and why run cases sequentially?

<details><summary>Answers</summary>

1. Rule when the check is decidable in code (route, ids, substrings, script share); judge only for meaning that varies in wording (invented facts, implied false claims).
2. Self-preference: different/stronger judge. Position: randomize order or grade single replies. Verbosity: judge a specific behavior, not overall quality. Leniency: give reference data and test with known-bad replies.
3. The model generates text in order; reasoning first lets the verdict follow from it. Verdict first makes the reasoning a justification of an already-chosen answer.
4. If failures are rare, a judge that always says "pass" has high agreement. Measure TP and TN rates separately.
5. pass@3 is high (about 0.96 at p=2/3); pass^3 about 0.30. pass^k matters, because each caller gets one try.
6. Not known. One case is 4 points on a single run; repeat both versions and compare spread, and see which cases flipped.
7. The mean is pulled by rare slow turns and hides the tail users feel. Parallel runs compete for network and the MCP connection, inflating per-turn time.
</details>

## 8. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-6 on this repo | 1 h |
| B. Another AI tutor | Quizzing on biases and pass^k | 45 min |
| C. Primary docs | Definitions with citations | 2 h |
| D. Video / course | Judge building from scratch | 2-3 h |

**A.** Prompt: "Read learning/notes/2026-10-08-running-evals-and-llm-judges.md and run_evals.py. Walk me through exercises 1-6 one at a time: run them, show output, explain what each result says about rules vs judge, noise and latency."

**B.** NotebookLM loaded with the C links, or ChatGPT/Gemini. Prompt: "Using only these sources (https://arxiv.org/abs/2306.05685, https://hamel.dev/blog/posts/llm-judge/, https://eugeneyan.com/writing/llm-evaluators/, https://anthropic.com/engineering/demystifying-evals-for-ai-agents, https://arxiv.org/abs/2406.12045), explain LLM-judge biases and how to validate a judge, pass@k vs pass^k, and then quiz me with 6 questions. Critique this judge prompt: <paste>."

**C.**
- [Zheng et al. 2023, Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685): names position, verbosity and self-enhancement bias; strong judges reach over 80% agreement with humans.
- [Hamel Husain: Creating a LLM-as-a-Judge That Drives Business Results](https://hamel.dev/blog/posts/llm-judge/): binary judgments with critiques, treat the judge as a classifier, TP/TN rates.
- [Eugene Yan: Evaluating the Effectiveness of LLM-Evaluators](https://eugeneyan.com/writing/llm-evaluators/): bias numbers and mitigations (swap positions, ensembles).
- [Anthropic: Demystifying evals for AI agents](https://anthropic.com/engineering/demystifying-evals-for-ai-agents): code/model/human graders, pass@k vs pass^k, isolating trials.
- [tau-bench paper](https://arxiv.org/abs/2406.12045): where pass^k comes from; GPT-4o below 50% and pass^8 under 25% in retail.
- [OpenAI: Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices): pass/fail or pairwise, reasoning before scoring, validate against human annotators.
- [LangSmith: evaluate an LLM application](https://docs.langchain.com/langsmith/evaluate-llm-application), [promptfoo intro](https://www.promptfoo.dev/docs/intro): what the packaged version looks like.
- [Google SRE book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/): the "Latency" section on averages vs distribution.

**D.**
- DeepLearning.AI short course "Evaluating AI Agents" (Arize AI; John Gilhuly, Aman Khan; about 2 h 16 min), https://deeplearning.ai/short-courses/evaluating-ai-agents : code vs LLM evaluators, includes a lesson "Improving your LLM-as-a-judge".
- "Evals, Error Analysis, and Better Prompts", Hamel Husain with Claire Vo, https://youtu.be/PgzOBNse2EA (link taken from Lenny's Newsletter; already listed in the test-set note). Binary evals and error analysis.
- I could not verify a standalone YouTube video on judge validation in search. Search terms: "LLM as a judge bias position verbosity self-preference" and "validate LLM judge true positive rate".
