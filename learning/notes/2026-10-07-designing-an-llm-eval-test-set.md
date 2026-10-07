# Designing an LLM eval test set

Step 3.1, `data/eval_cases.yaml` + `eval_cases.py`. Sources opened 2026-10-07. Related: [failure routes and per-route eval cases](2026-10-03-failure-handling-and-guardrails.md) (exercise 5), [WER, test sets and leakage for STT](2026-10-04-evaluating-speech-providers.md). The loader and YAML mechanics are in [YAML data files and Pydantic](2026-10-07-yaml-data-files-and-pydantic-validation.md). The runner, judge reliability, noise and latency are in [Running evals: rules, LLM judges, noise and latency](2026-10-08-running-evals-and-llm-judges.md).

## 1. What you're learning, and why it matters

**Problem: "it seems to work" is not evidence.** You change a prompt, try three questions, and ship. The next change breaks the TV-packages case and nobody notices. An **eval test set** (a fixed list of inputs, each with the behavior it must show) turns "seems fine" into a number you can re-measure after every change. It is also the answer to the question "How do you judge correctness and safety?"

**Behavior, not wording.** An LLM rephrases the same correct answer every run. Exact-reply matching fails on every rewording and tells you nothing. So each turn lists things a program can check:
- `outcome`: which route the turn ended on (`answer`, `clarify`, `handoff:<reason>`).
- `intent`, `tool_called`, `lookup_attempts`: what the graph did.
- `facts_include`: which FAQ ids the lookup returned. The tool's argument is free text (`topic`), so you can't compare it to an expected string; you judge it by **what it found**. That is how "wrong tool arguments" is covered without its own category.
- `reply_has` / `reply_lacks`: a few required or forbidden strings (`"15"`, `"a|b"` = either).

**What makes a good case:**
- It tests one behavior and says why (`why:` field), so a failing case tells you what broke.
- It is decidable without reading the reply, wherever possible.
- It targets a real risk: a tempting wrong answer ("I've blocked your SIM"), not just a happy path.
- It is stable: running it twice gives the same verdict unless the system changed.

**Categories and coverage.** Cases come in groups so no behavior is left out: ordinary, ambiguous, missing_info, multi_turn, tool_failure, false_action, code_switched, and `off_topic` (its own category because "other" is its own route in the graph: no lookup, no general-knowledge answer). The loader insists on **at least 3 per category**. One case is an anecdote, and with a stochastic model a single pass or fail proves little. 25 cases is small; Hamel's FAQ says repeatable sets "often grow to 100 or more", grown from real failures.

**Multi-turn cases.** `turns` is a list; each turn may have its own `expect`. A turn without `expect` is a **setup turn** (only builds the conversation). The loader rejects a case that checks nothing, or whose last turn is a setup turn.

**Allowed-outcome sets.** `outcome` is a *list of acceptable* results. For "block my SIM" both `answer` (says it can't, explains the app) and `handoff:false_action_claim` (the check caught a false claim) are safe; only a claim of success is wrong. Don't make a test fail on a safe behavior you'd accept in production.

**Fault injection.** To test "the tool fails" you must make it fail on purpose: `setup.tool: fail_once | fail_always | down` swaps in a lookup that fails like a database error (retryable) or a dead server (not retryable). Then `lookup_attempts: 2` vs `1` checks the retry policy.

**Contamination ("teaching to the test").** If you tune the prompt until your eval cases pass, the score measures how well you memorised them, not how well it generalises. Here `amb-price` ("how much does it cost?") is also an example in `UNDERSTAND_PROMPT`, so it only checks the prompt is followed; the other ambiguous wordings are new. The fix is a **held-out set**: cases you write but never look at while tuning, run rarely. (Same idea as the test-set leakage in the speech note.) Step 3.3's improvements should be judged on cases not used to design them.

**Rules first, a judge only where rules can't decide.** "Did the reply imply it blocked the SIM?" can't be a regex (paraphrases). 8 turns carry a `judge:` question for an LLM judge. Write it as a **yes/no question where "yes" = pass**, one behavior per question. Everything else stays plain code: cheaper, deterministic, no judge bias. (3.2 covers judge reliability; here just know a judge is itself a model that can be wrong.)

**Golden datasets and regression suites.** A **golden dataset** is the curated, trusted set of inputs with expected behavior; a **regression suite** is that set re-run after each change to catch things that used to work and stopped. Our YAML is both.

## 2. In this repo

- `data/eval_cases.yaml`: 25 cases, 28 turns; the header comment documents every `expect` field.
- `python eval_cases.py` prints one line per category with ids, then `25 cases, 28 turns (28 with checks, 8 with an LLM-judge question). OK`.
- Before writing cases, `faq.lookup_faq` was run on candidate topics: expected ids are reachable (`"როუმინგი ევროპა ფასი"` returns `roaming-europe` first), and missing-info questions return *unrelated* entries (`"ტელევიზია პაკეტები"` returns `roaming-no-package`, `extra-data`, `plans-overview`). So `miss-*` cases don't test "search finds nothing"; they test that `answered=false` plus `check` hand off instead of making up an answer. **Lesson: validate that your case tests what you think it tests.**
- The code-switched cases are the text of recordings c1, c3, c4, so step 3.4 can compare typed vs spoken.

## 3. How the pieces fit together

```
eval_cases.yaml --load_cases()--> validated Case objects --(3.2 runner)--> run graph per turn
                                                           -> rule checks + judge questions -> report
```
3.1 defines *what good looks like*; 3.2 measures it; 3.3 changes the system and re-measures.

## 4. Related tools

Same idea, different packaging (each description checked 2026-10-07):
- **LangSmith datasets**: a *dataset* is a collection of *examples* (inputs, optional reference outputs, metadata); evaluators are code (heuristic) or LLM-as-judge; offline evals on a dataset serve regression testing. Our `Case` = an example, `expect` = reference output plus checks.
- **promptfoo**: open-source CLI/library with declarative test cases, plus red-teaming. Closest to our YAML.
- **DeepEval**: open-source, pytest-style; "test cases", "goldens", `EvaluationDataset`.
- **OpenAI Evals**: open-source framework and registry of benchmarks; its README now points to running Evals in the OpenAI Dashboard.
Not used: the format is ~100 lines of our own code, it checks graph internals (route, retry count) those tools don't know about, and writing it yourself is the learning goal. Moving the cases into LangSmith later is a small export.

## 5. Hands-on exercises

1. Write two more cases for an uncovered behavior (e.g. a customer who gives a wrong number and corrects themselves; a question mixing two FAQ topics). Run `python eval_cases.py`. Check: the category count goes up and it still prints OK.
2. Run `python -c "from faq import lookup_faq; print([r['id'] for r in lookup_faq('<your topic>')])"` (check the real signature in `faq.py` first) for each new case's wording. Check: your `facts_include` ids really appear; if not, the case or the search is wrong.
3. Find a case whose expectation is too strict or wrong: read `cs-roaming-iphone` and ask whether `intent: [faq, action]` rejects an acceptable answer. Write down what you'd loosen and why.
4. Pick an `ambiguous` case and rewrite its wording three ways. Which would you keep in the held-out set, and why not in the prompt?
5. Break test: misspell a field, duplicate an id, delete a category's cases; read the errors.

## 6. Self-check

1. Why not compare the reply to an expected string?
2. How is a free-text tool argument checked without an exact match?
3. Why is `outcome` a list?
4. What's wrong with tuning the prompt until all 25 pass?
5. When do you use an LLM judge, and how should its question be written?
6. Why do `miss-*` cases not test an empty search?

<details><summary>Answers</summary>

1. The model rewords correct answers each run, so exact matching fails on correct replies. Check route, tool use, retrieved ids and key facts.
2. By its result: `facts_include` lists FAQ ids the lookup must return; a bad topic won't return them.
3. More than one behavior can be safe (answer-with-refusal or hand-off); the test should fail only on unsafe ones.
4. Overfitting/contamination: the score measures memorisation of those cases. Keep held-out cases.
5. Only where rules can't decide (paraphrased false claims, invented facts); a yes/no question, one behavior, "yes" = pass.
6. Search returns loosely related entries anyway; the risk is the model passing them off as an answer.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Doing exercises 1-5 on this repo | 45 min |
| B. Another AI tutor | Quizzing, brainstorming more cases | 45 min |
| C. Primary docs | Vocabulary, vendor-neutral practice | 1-2 h |
| D. Video / course | Seeing error analysis done on real data | 2-4 h |

**A.** Prompt: "Read learning/notes/2026-10-07-designing-an-llm-eval-test-set.md, data/eval_cases.yaml and eval_cases.py. Walk me through exercises 1-5 one at a time: do the work, show the output, explain what each result tells me about test-set design."

**B.** NotebookLM loaded with the C links, or ChatGPT/Gemini. Prompt: "Using only these sources (https://platform.claude.com/docs/en/test-and-evaluate/develop-tests, https://docs.langchain.com/langsmith/evaluation-concepts, https://hamel.dev/blog/posts/evals-faq/, https://hamel.dev/blog/posts/evals/), explain how to design an eval set for a customer-service chatbot: what a case contains, categories, held-out data, and when to use an LLM judge. Then quiz me with 6 questions and critique 3 cases I paste."

**C.**
- [Anthropic: Define success criteria and build evaluations](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests): edge cases to include, grading methods (code, LLM, human), "volume over quality".
- [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts): datasets, examples, reference outputs, code vs LLM evaluators, offline vs online, regression testing.
- [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/): unit-test level evals first, binary pass/fail judges.
- [Hamel Husain: Evals FAQ](https://hamel.dev/blog/posts/evals-faq/): how many test cases, synthetic data by dimensions, validating judges, keeping dev and test sets separate.
- Tool docs for comparison: [promptfoo intro](https://www.promptfoo.dev/docs/intro), [DeepEval getting started](https://deepeval.com/docs/getting-started), [OpenAI Evals repo](https://github.com/openai/evals).

**D.**
- "Evals, Error Analysis, and Better Prompts: A Systematic Approach to Improving Your AI Products", Hamel Husain with Claire Vo, ~105 min, https://youtu.be/PgzOBNse2EA (link from [Lenny's Newsletter page](https://www.lennysnewsletter.com/p/evals-error-analysis-and-better-prompts)). Binary evals, error analysis on a chatbot.
- DeepLearning.AI short course "Evaluating AI Agents" (Arize AI; free short course): https://www.deeplearning.ai/courses/evaluating-ai-agents (code vs LLM judge vs human evaluators per component).
- DeepLearning.AI "Automated Testing for LLMOps" (Rob Zuber, CircleCI, ~1 h): https://deeplearning.ai/short-courses/automated-testing-llmops (rules-based tests, model-graded evals, running them in CI).
- Paid, not needed: Hamel Husain and Shreya Shankar's Maven course "AI Evals for Engineers & PMs" (about $5,000 per search results).
