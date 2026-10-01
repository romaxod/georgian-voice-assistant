# LLM API tokens, pricing and keys

Date: 2026-10-02. Prices checked on this date (sources in section 7C). Prices change; recheck before you pay.

## 1. What you're learning, and why it matters

**Problem: the assistant will make hundreds of model calls and you pay per call.** To budget $5-10 and not be surprised, you need to know what you are billed for.

- **Token:** the unit a model reads and writes. Text is split into pieces (whole short words, word fragments, punctuation, single bytes). English averages roughly 4 characters or 0.75 words per token (Anthropic's pricing FAQ says the same). Each model family has its own **tokenizer**, so counts differ between providers.
- **Input tokens** (the **prompt**): everything you send: system prompt, the whole chat history, tool definitions, your new message. **Output tokens:** what the model generates. Both are billed, per **1M tokens (MTok)**.
- **Why output costs more** (4-5x here): the model reads the whole input in one parallel pass, but writes output one token at a time, each needing another pass. (This is the usual explanation, not something the pricing pages state.)
- **The model is stateless.** It remembers nothing between calls. A "conversation" is your code resending the full history every turn, so **input cost grows with conversation length**. Output is billed once; old output re-enters later as input. (BUILD_PLAN step 1.2.)
- **The `usage` field:** every API response reports the token counts it billed (Anthropic: `usage.input_tokens` / `usage.output_tokens`; OpenAI's field names differ by endpoint, so check the SDK). Cost = `input_tokens x in_price/1e6 + output_tokens x out_price/1e6`. (BUILD_PLAN step 1.1 prints this.)
- **Georgian costs more tokens** (checked, section 2). Tokenizers are trained mostly on English text, so Georgian script gets split into many small pieces.
- **API vs subscription:** ChatGPT Plus / Claude Pro cover the chat apps. Code calls the **API**: a separate account, prepaid credit, and an **API key**, a secret string that identifies and bills you. Anyone with the key can spend your credit.
- **Keys:** go in `.env` (listed in `.gitignore`), loaded by `python-dotenv`; never in code, git or chat. A leaked key means delete it in the dashboard and create a new one.

## 2. In this repo

Decision (SETUP.md section 1, 2026-10-02): paid API with a $5-10 budget, OpenAI recommended. Both providers need a $5 minimum prepaid purchase. Set a **spend limit** in the dashboard.

| Model | Input / 1M | Output / 1M | Verified |
|---|---|---|---|
| OpenAI `gpt-5.4-mini` | $0.75 | $4.50 | Yes, OpenAI's official pricing page |
| Claude Haiku 4.5 `claude-haiku-4-5` | $1 | $5 | Yes, Anthropic's pricing page |
| Claude Sonnet 5.5 `claude-sonnet-5-5` | $2 | $10 | Yes, same page |

The secondary summary (morphllm.com) was **correct** for `gpt-5.4-mini`; SETUP.md needs no change.

**The estimate, with arithmetic.** 500 calls x (2,000 in + 300 out):
- Input: 500 x 2,000 = 1,000,000 tokens = 1 MTok. Output: 500 x 300 = 150,000 tokens = 0.15 MTok.
- `gpt-5.4-mini`: 1 x $0.75 + 0.15 x $4.50 = $0.75 + $0.675 = **$1.43**
- Haiku 4.5: 1 x $1 + 0.15 x $5 = $1 + $0.75 = **$1.75**
- Sonnet 5.5: 1 x $2 + 0.15 x $10 = $2 + $1.50 = **$3.50**

So "$1.50-2 on a cheap model" holds. Caveat: these are guesses at call size; section 5 exercise 3 shows why real chats cost more.

**Georgian vs English, measured** with `tiktoken` in a throwaway venv outside the repo (`tiktoken` is OpenAI's tokenizer library):

| Sentence | Chars | Words | `o200k_base` tokens | `cl100k_base` tokens |
|---|---|---|---|---|
| Georgian (the SETUP.md TTS test sentence) | 67 | 7 | **28** | **127** |
| English (similar meaning) | 65 | 12 | **14** | **14** |

- Georgian is **2x** the English tokens on the newer encoding (about 4 tokens per word vs 1.2) and about **9x** on the older one. Short, simple sentences, so treat it as a direction, not a constant.
- I assumed `o200k_base` is close to what `gpt-5.4-mini` uses; I did not verify which encoding it uses. I did **not** test Claude's tokenizer (not public through tiktoken); Anthropic's page only says Claude 4.7+ models produce about 30% more tokens than older ones for the same text.
- Effect on the budget: if most of your text is Georgian, expect token counts, and so the estimate, up to about 2x. Still within $5-10 on a cheap model.

## 3. How the pieces fit together

```
your code ---(system + history + new message = INPUT tokens)---> API
your code <---(answer = OUTPUT tokens, plus `usage` counts)------ API
.env --> python-dotenv --> API key in the request header (identifies and bills you)
```

Cost per turn = input (grows each turn) + output (roughly constant). A step limit and a spend limit stop runaway loops.

## 4. Related tools

- **Prompt caching** (both providers): repeated prompt prefixes billed at about 0.1x input price (Anthropic's page; OpenAI lists `gpt-5.4-mini` cached input at $0.075/MTok). Not needed at this scale.
- **Batch API:** 50% off for non-urgent jobs (Anthropic page). Might suit running an eval set; not needed now.
- **Gemini free tier:** rejected in the decision; free but limits and data terms differ.
- **Token counters:** OpenAI's tokenizer web page (blocked for my fetch tool, so unchecked), `tiktoken`, Anthropic's token-counting endpoint.

## 5. Hands-on exercises (no project code needed unless stated)

1. Recompute the three estimates above by hand. Check: you get $1.43, $1.75, $3.50.
2. Open the official pricing pages (7C). Check: the three prices in the table match; note the date you looked.
3. **History growth by hand.** System prompt 500 tokens; each turn adds 100 tokens from you and 300 from the model. Input at turn k = 500 + 400(k-1) + 100. Over 10 turns, add them up (answer: 24,000 input tokens, vs 6,000 if history were not resent). Check: total input is 4x, though the output is the same.
4. A conversation costs $0.01 at turn 5. Without computing, will turn 20 cost exactly 4x? Explain (input grows about linearly with turns, but output per turn stays constant, so the cost is between 1x and 4x, nearer 4x if input dominates).
5. Run `git check-ignore -v .env` in the repo. Check: it prints the `.gitignore` rule. Then explain why this matters before the first commit.
6. In the provider dashboard (when you buy the credit), find the spend limit setting and set it. Check: you can see the number.
7. After BUILD_PLAN step 1.1: send the same question in English and in Georgian and compare `usage.input_tokens`. Check: Georgian is higher.

## 6. Self-check: can you answer these without looking?

1. What are you billed for on one API call?
2. Why does a 20-turn chat cost more than 20 times a one-turn chat's input?
3. Why does the model need the history resent?
4. Where do you find the real token counts, and what would you do with them?
5. Why might the Georgian assistant cost more than an English one?
6. Why is a ChatGPT Plus subscription no use for this project, and where does the API key live?

<details>
<summary>Answers</summary>

1. Input tokens (system prompt, history, tools, new message) and output tokens, each at its own per-million price.
2. Each turn resends all earlier turns as input, so per-turn input grows with length and the total grows faster than linearly.
3. The model is stateless; it only sees what is in the current request.
4. The `usage` field in the response; multiply by the per-million prices to print a cost (step 1.1).
5. Georgian script is split into more tokens per word (28 vs 14 tokens on one sentence pair with `o200k_base`).
6. The subscription covers only the chat apps; the API is a separate prepaid account. The key goes in `.env`, which git ignores.

</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through** | Doing the arithmetic and tokenizer test yourself | About 30 min |
| B. Another AI tutor | A different explanation of tokens and pricing | About 30 min |
| C. Primary docs | Exact prices, limits, and billing rules | About 30 min |
| D. Video | Understanding what a tokenizer does | 15 min to 2 h 15 min |

**A. Prompt for a main session:**
> Walk me through `learning/notes/2026-10-02-api-tokens-and-pricing.md`. Do exercises 1-6 one at a time, ask me to explain each result before moving on, and then quiz me on the self-check questions. Do exercise 7 when we reach BUILD_PLAN step 1.1.

**B. Tool:** NotebookLM with the C links, or ChatGPT/Gemini. Prompt:
> Using only these sources, explain tokens, input vs output pricing, why chat history makes input cost grow, and how to read the usage field. Then quiz me with 5 questions. Sources: https://platform.claude.com/docs/en/about-claude/pricing, https://developers.openai.com/api/docs/pricing, https://help.openai.com/en/articles/8264644-how-can-i-set-up-prepaid-billing

**C. Primary docs** (opened 2026-10-02 unless noted):
- <https://developers.openai.com/api/docs/pricing>: OpenAI per-model prices (`platform.openai.com/docs/pricing` redirects here).
- <https://platform.claude.com/docs/en/about-claude/pricing>: Anthropic prices, caching, batch, the tokenizer note.
- <https://help.openai.com/en/articles/8264644-how-can-i-set-up-prepaid-billing>: prepaid billing. My fetch got a 403; the $5 minimum and one-year expiry come from a search result summarizing this page, so check it in a browser.
- Anthropic's $5 minimum is **unverified** by me; check it at the billing page when you sign up.

**D. Video:**
- "Let's build the GPT Tokenizer", Andrej Karpathy, 2 h 13 min (long; watch the first 20 min for the idea): <https://youtu.be/zduSFxRajkE>
- "Large Language Models explained briefly", 3Blue1Brown, short overview: <https://www.youtube.com/watch?v=LPZh9BOjkQs>
- Both titles and links were confirmed in a search result; I did not watch them.
