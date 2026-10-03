# OpenAI Responses API: your first LLM call

Checked 2026-10-02 against openai-python 3.23.0 (installed source in `.venv`), OpenAI's docs (migrate-to-responses, conversation-state, reasoning, error codes, text) and the SDK README. Tokens, prices and keys are in [api-tokens-and-pricing](2026-10-02-api-tokens-and-pricing.md); the tool-calling loop this grows into is in [agent-loops](2026-10-02-agent-loops.md). `.env` loading is in [env-vars-and-dotenv](2026-10-02-env-vars-and-dotenv.md).

## 1. What you're learning, and why it matters

**Problem:** your Python program must send text to a hosted model over HTTPS and get text back, know what it cost, and fail cleanly when something is wrong. Every later step (LangGraph nodes, evals, voice) is built on this one call.

- `client = OpenAI()` creates an HTTP client that reads `OPENAI_API_KEY` from the environment. `client.responses.create(model=..., instructions=..., input=...)` sends one request and returns a **`Response`** object.
- **`instructions`** = the rules for the model (persona, language). **`input`** = what the user said (a string, or a list of messages). Docs: `instructions` apply to *this request only* and don't carry over in multi-turn use ([text guide](https://developers.openai.com/api/docs/guides/text)).
- **`response.output_text`** is a helper that joins all text pieces. The real data is `response.output`, a **list of typed items** (message, reasoning, tool call...). OpenAI warns not to assume text is at `output[0].content[0].text`.
- **`response.usage`** has `input_tokens`, `output_tokens`, `total_tokens`, plus `input_tokens_details` and `output_tokens_details`. Cost = `input/1e6 * PRICE_IN + output/1e6 * PRICE_OUT`. Example: 100 in, 150 out at $0.75 / $4.50 per 1M = $0.000075 + $0.000675 = $0.00075.
- **Reasoning models** "think" first. Those hidden **reasoning tokens** are billed as output tokens and counted in `usage.output_tokens_details.reasoning_tokens`, even though you never see them ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)). So a one-line answer can cost more than its length suggests. `reasoning={"effort": "low"}` asks for less thinking (documented values include `none`, `minimal`, `low`, `medium`, `high`; which ones `gpt-5.4-mini` accepts I did not check). `max_output_tokens` caps visible plus reasoning tokens; if hit, `response.status == "incomplete"` and you may pay for reasoning with no visible text.
- **Responses vs Chat Completions.** Chat Completions takes a `messages` list (`system`/`user`/`assistant` roles) and returns `choices[0].message.content`. Responses takes `input` (+ `instructions`), returns typed `output` items, and can chain state server-side. OpenAI says Chat Completions is **not deprecated**, but Responses is "recommended for all new projects" ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)). That is why we use it. Roles in Responses messages: `developer` (your rules, highest priority), `user`, `assistant`. Many other tools and providers (and LangChain wrappers) still speak the `messages` format, so you'll see both.
- **Stateless by default.** The model remembers nothing between calls. Two ways to continue a chat: resend the history yourself (a list of `user`/`assistant` messages), or pass `previous_response_id` and let OpenAI keep it (`store` defaults to true, kept 30 days). Even with `previous_response_id`, all earlier tokens are billed again as input ([conversation state](https://developers.openai.com/api/docs/guides/conversation-state)). **Step 1.2 resends history ourselves** on purpose: you see exactly what is in the context, what costs money, and how to trim it, and LangGraph state works the same way. It also keeps us independent of one vendor's storage.
- **Errors** (SDK maps HTTP status to classes; verified in the README and by a live call below): `APIConnectionError` (network, no status) and `APITimeoutError`; `APIStatusError` is the parent of everything with a status: `BadRequestError` 400, `AuthenticationError` 401, `PermissionDeniedError` 403, `NotFoundError` 404, `UnprocessableEntityError` 422, `RateLimitError` 429, `InternalServerError` 5xx. All inherit `OpenAIError`. Catch narrow classes you can act on; let unexpected ones crash so you see the traceback ([reading tracebacks](2026-10-02-reading-python-tracebacks.md)).
- **429 means two things:** rate limit (too fast; wait) and out of credit/spend limit (`error.code` is `insufficient_quota`; waiting won't help). Check `e.code` ([error codes](https://developers.openai.com/api/docs/guides/error-codes)). `first_call.py` prints `e.code` for that reason.
- **Built-in retries and timeouts:** the client retries 2 times by default (connection errors, 408, 409, 429, 5xx) with exponential backoff (0.5 s growing to a cap of 8 s in the SDK constants). Default timeout is 10 minutes read/write with a 5 s connect timeout (SDK constants `DEFAULT_TIMEOUT`). Change with `OpenAI(max_retries=0, timeout=30)`. So your `except RateLimitError` only runs *after* two silent retries. Whether the SDK retries an `insufficient_quota` 429 I did not verify.

- *(added 2026-10-03)* **`input` as a list of role messages.** `input` can be a list like `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, {"role": "user", "content": "..."}]`. The conversation-state guide says alternating `user` and `assistant` messages "capture the previous state of a conversation in one request". You include earlier *assistant* answers yourself. **`store=False`** tells OpenAI not to save the response object; by default "response objects are saved for 30 days" (same guide; confirms the 30 days above). Step 1.2 passes `store=False` because it keeps the history itself, so server storage adds nothing. Concepts of prompts and memory: [system-prompts-and-memory](2026-10-03-system-prompts-and-memory.md).

## 2. In this repo

`first_call.py` (step 1.1): load `.env`, build the client, send a Georgian question with `instructions="... Always answer in Georgian."`, catch `AuthenticationError` / `RateLimitError` / `APIConnectionError` and `sys.exit` with a friendly message, then print `response.output_text`, token counts and the computed cost. Prices (`0.75` / `4.50` USD per 1M tokens for `gpt-5.4-mini`) are hard-coded constants checked 2026-10-02; they can go stale.

I confirmed in the installed SDK that `responses.create` accepts `instructions, input, max_output_tokens, previous_response_id, conversation, store, reasoning, temperature, stream` and that `Response.output_text` exists. I also made one call with the key `sk-wrong` and `max_retries=0`: it raised `AuthenticationError` (status 401, `code == "invalid_api_key"`, parents `APIStatusError` > `APIError` > `OpenAIError`). That is exactly the first break test. The second break test, `MODEL = "gpt-nonexistent"`, needs a *valid* key to get past authentication, so I did not run it. Expected: a `NotFoundError` (404, code `model_not_found`) per many community reports, but this is **unverified**; the uncaught traceback will tell you, and the last line is the answer.

*(added 2026-10-03)* **Step 1.2, `chat.py`:** calls `client.responses.create(model="gpt-5.4-mini", instructions=SYSTEM_PROMPT, input=history, store=False)`, where `history` is the list of all user and assistant messages so far. Measured on a three-turn piped chat, input tokens grew **455 -> 516 -> 570** (the rules and facts in `SYSTEM_PROMPT` are already about 440 tokens of the first call; each later turn adds the previous question and answer, about 55-60 tokens here). With `--no-memory` the third-turn-style follow-up sent 441 input tokens and lost its context. The `except` blocks catch `AuthenticationError` (exit) and `RateLimitError`/`APIConnectionError`/`APIStatusError` (pop the unanswered question, continue).

## 3. How the pieces fit together

```
.env -> load_dotenv -> OPENAI_API_KEY -> OpenAI() -> responses.create(model, instructions, input)
   -> HTTPS (auto-retries) -> Response{output[], usage, status} -> output_text + cost math
   errors: 401/404/429/... -> subclass of APIStatusError; no connection -> APIConnectionError
```

## 4. Related tools

- Chat Completions API: older, `messages` list, still supported. Anthropic's Messages API and `langchain-openai` use similar shapes. We'll go through LangChain/LangGraph later.
- Conversations API and `previous_response_id`: server-side state, convenient but hidden. Not used here.
- Streaming (`stream=True`) sends tokens as they are generated; it matters for voice latency later.

## 5. Hands-on exercises

Free ones need no real key. Run from the project folder with `.venv/bin/python`.

1. **Missing key (free).** `env -u OPENAI_API_KEY .venv/bin/python -c "from openai import OpenAI; OpenAI()"`. Check: `OpenAIError: Missing credentials...` before any network call.
2. **Wrong key (free).** `OPENAI_API_KEY=sk-wrong python first_call.py`. Check: your friendly "API key was rejected" message. Then remove the `except AuthenticationError` temporarily and read the traceback: the last line is `openai.AuthenticationError: Error code: 401`.
3. **Read the signature (free).** `.venv/bin/python -c "import inspect, openai; print(inspect.signature(openai.OpenAI(api_key='x').responses.create))"` (a dummy key; nothing is sent). Check: find `instructions`, `max_output_tokens`, `previous_response_id`, `reasoning`.
4. **Real call, under $0.01.** Run `first_call.py`, then add `print(response.output)` and `print(usage.output_tokens_details)`. Check: `output` is a list with a message item (maybe a reasoning item too); note `reasoning_tokens`, and recompute the cost by hand against the script's number.
5. **Reasoning and caps, under $0.01.** Add `reasoning={"effort": "low"}`, then `max_output_tokens=16`. Check: `response.status` and `response.incomplete_details`; whether `output_text` is empty. Remove the cap after.
6. **Statelessness, under $0.01.** Make two separate calls: "My name is Roman." then "What is my name?". Check: the model can't answer. Then pass `previous_response_id=first.id` to the second and compare the `input_tokens`: it includes the first turn.
7. **Bad model name (needs your key, about $0).** Set `MODEL = "gpt-nonexistent"`, remove no except blocks, run. Check: which exception class the last line names; write it here and update this note.
8. **Retries.** Set `OpenAI(max_retries=0)` and turn off your network (or set `base_url="http://localhost:9"`). Check: `APIConnectionError` appears immediately; with the default it takes noticeably longer.

## 6. Self-check: can you answer these without looking?

1. What are `instructions` vs `input`, and which does not persist across calls?
2. Why can `output_text` be short while the bill is large?
3. Name the exception for a wrong key, a missing model, no internet, and "out of credit". Which two share HTTP 429, and how do you tell them apart?
4. Why does your `except RateLimitError` fire later than you'd expect?
5. What does `previous_response_id` save you, and what does it not save you?
6. Why do we resend history ourselves in step 1.2?

<details><summary>Answers</summary>

1. `instructions` = developer rules for this request only; `input` = the user content or message list. `instructions` don't carry over to the next call.
2. Hidden reasoning tokens are billed as output tokens (`output_tokens_details.reasoning_tokens`).
3. `AuthenticationError` (401); `NotFoundError` (404, expected, unverified for a bad model); `APIConnectionError`; `RateLimitError` (429). Rate limit and out-of-credit are both `RateLimitError`; check `e.code` (`insufficient_quota` means billing).
4. The SDK silently retries 429s (and others) twice with backoff first.
5. You don't write the history code, but earlier tokens are still billed as input every time.
6. Visibility and control of what's in context and what it costs; it mirrors how LangGraph state works; no dependence on server-side storage.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Exercises 1-8 with your own output | ~1 hr |
| B. Another AI tutor | Explaining roles/state/usage differently | ~45 min |
| C. Primary docs | Accurate parameters and error behaviour | ~1 hr |
| D. Video/course | Seeing the API used live before you try | 1-1.7 hr |

**A. Prompt for a main session in this repo:**
> Walk me through learning/notes/2026-10-02-openai-responses-api.md. Do hands-on exercises 1-8 one at a time. Run each, show me the output, and ask me to predict the exception or token numbers before running. Never read or print .env. Then quiz me on the self-check questions.

**B. Tool:** NotebookLM with the C links as sources, or ChatGPT/Gemini. Prompt:
> I'm a CS student learning the OpenAI Responses API with Python. Using only these sources, explain `instructions` vs `input`, the Response object, usage and reasoning tokens, state (`previous_response_id` vs resending history), and the SDK error classes and retries. Then give me 5 quiz questions with answers. Sources: https://developers.openai.com/api/docs/quickstart, https://developers.openai.com/api/docs/guides/text, https://developers.openai.com/api/docs/guides/migrate-to-responses, https://developers.openai.com/api/docs/guides/conversation-state, https://developers.openai.com/api/docs/guides/reasoning, https://developers.openai.com/api/docs/guides/error-codes, https://github.com/openai/openai-python

**C. Reading list (all opened):**
- OpenAI quickstart: <https://developers.openai.com/api/docs/quickstart>. The minimal Python call and how the key is read from the environment. (Its example model name changes; use `gpt-5.4-mini` for cost.)
- Text generation guide: <https://developers.openai.com/api/docs/guides/text>. Roles, `instructions`, the `output` array, `output_text`.
- Migrate to Responses: <https://developers.openai.com/api/docs/guides/migrate-to-responses>. Responses vs Chat Completions, and why Responses is recommended.
- Conversation state: <https://developers.openai.com/api/docs/guides/conversation-state>. Manual history vs `previous_response_id` vs Conversations; billing caveat.
- Reasoning guide: <https://developers.openai.com/api/docs/guides/reasoning>. Effort levels, reasoning tokens, `max_output_tokens`.
- Error codes: <https://developers.openai.com/api/docs/guides/error-codes>. 401 vs 429 vs quota, retry advice.
- openai-python README: <https://github.com/openai/openai-python>. Error classes, retries, timeouts.
- DataCamp, "OpenAI Responses API: The Ultimate Developer Guide" (Bex Tuychiev, April 2025): <https://www.datacamp.com/tutorial/openai-responses-api>. A written walkthrough with Python; the guide is older than the SDK we use, so trust the docs above if they differ.

**D. Video / course:**
- "Build Hour: Responses API", OpenAI (hosts Christine and Steve, an API engineer): <https://goldcast.ondemand.goldcast.io/on-demand/602d7993-a489-4a74-8f42-b4b1c5a6533a> (the page I opened; its transcript says the sessions are also on the OpenAI YouTube channel, but I did not find a confirmed YouTube link). Covers migration from Chat Completions, tools and reasoning.
- "ChatGPT Prompt Engineering for Developers", DeepLearning.AI with Isa Fulford (OpenAI) and Andrew Ng: <https://deeplearning.ai/short-courses/chatgpt-prompt-engineering-for-developers/>. About 1.5 hours, 9 lessons, free per the page when I fetched it. It teaches prompting with "the OpenAI API"; I could not confirm whether its notebooks use Chat Completions or Responses, so expect the older `messages` style.

Whatever you choose, finish with the exercises and the self-check.
