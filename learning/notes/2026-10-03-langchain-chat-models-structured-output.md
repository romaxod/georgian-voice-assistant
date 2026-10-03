# LangChain chat models and structured output

Date: 2026-10-03. Checked against the LangChain docs (Models, Messages, ChatOpenAI integration, Structured output pages; all opened), the Pydantic "Fields" page, the installed packages (langchain-core 1.6.6, langchain-openai 1.6.7) and by running snippets offline. No API call was made for this note; the real outputs come from the 2.1 run. The code using it is `graph.py` (`understand` and `answer`); see `docs/code/graph.py.md`.

## 1. What you're learning, and why it matters

**Problem:** the `understand` node must return *data* the graph can branch on (`intent`, `topic`), not prose. And LangGraph's `add_messages` reducer needs message objects with ids. LangChain's chat-model layer provides both.

- **Messages** (`langchain_core.messages`): `SystemMessage`, `HumanMessage`, `AIMessage` (the model's reply), `ToolMessage` (tool result). **`AnyMessage`** is the union type used in `State`. Each has `content` and an **`id`** (auto-generated or given by you; we pass our own `uuid4` so we can `RemoveMessage` it later). `AIMessage.usage_metadata` is `{"input_tokens", "output_tokens", "total_tokens"}`: the same numbers as the OpenAI `usage` field ([tokens note](2026-10-02-api-tokens-and-pricing.md)), under LangChain names. That is where our `cost()` reads.
- **`ChatOpenAI(model=...)`**: a LangChain wrapper around the OpenAI SDK. It reads `OPENAI_API_KEY` itself (constructing it without one raises "Missing credentials"). It is a **Runnable**: all Runnables share `.invoke(input)`, `.stream(input)` and `.batch(list)`. `llm.invoke([SystemMessage(...), HumanMessage(...)])` returns an `AIMessage`. It also retries by itself (`max_retries` default 6 per the Models page).
- **Structured output**: `llm.with_structured_output(Schema)` returns a *new Runnable* whose `.invoke` returns a `Schema` object instead of an `AIMessage`. How it works (installed signature: `method="json_schema"` default, plus `include_raw=False`, `strict=None`):
  - `json_schema`: OpenAI's native structured outputs; the schema is sent as `response_format` and the API constrains decoding to it.
  - `function_calling`: the schema is sent as a tool and the model "calls" it; the arguments are parsed. `json_mode`: only "valid JSON", schema described in your prompt.
  - Note: the ChatOpenAI docs page I opened calls `function_calling` the default, but the installed 1.6.7 signature says `json_schema`. Defaults changed across versions; check `inspect.signature`.
- **`include_raw=True`**: returns `{"raw": AIMessage, "parsed": Schema | None, "parsing_error": Exception | None}`. Without it a bad output raises. With it you get an error *as data*, plus the raw message (needed here for `usage_metadata`). Our fallback: `parsed is None` becomes intent faq with the raw question.
- **Pydantic as the schema.** `class Understanding(BaseModel)` with `intent: Literal["faq","other"]` and `topic: str`. `Literal` becomes a JSON Schema `enum`, so the model can only pick those values. `Field(description=...)` becomes the `description` of that property in the schema the model sees. I printed `Understanding.model_json_schema()` and our Georgian descriptions are in it, plus the class docstring as the schema description. **So descriptions are prompt text**: write them as instructions, and the field name matters too.

## 2. In this repo

`graph.py`: `understander = llm.with_structured_output(Understanding, include_raw=True)`; in `understand`: `result["parsed"]`, `result["raw"].usage_metadata`. `answer` calls plain `llm.invoke(...)` and returns the `AIMessage` straight into `state["messages"]`. Real result: "რა ღირს როუმინგი ევროპაში?" gave `intent=faq topic='როუმინგი ევროპა ფასი'`.

Not guaranteed: schema-valid does not mean *correct*. The model can still pick `other` for a real question or return a bad `topic`. Only evals ([BUILD_PLAN](../../BUILD_PLAN.md) phase 3) tell you how often. Same lesson as `strict` in the [function-calling note](2026-10-03-function-calling-responses-api.md).

## 3. How the pieces fit together

```
[SystemMessage, *state["messages"]] -> ChatOpenAI.with_structured_output(Understanding)
   -> OpenAI API (schema in response_format) -> {"raw": AIMessage, "parsed": Understanding}
   -> node returns {"intent", "topic", "cost"} -> graph branches on intent
```

Structured output vs function calling: both constrain the model to a JSON Schema. Function calling lets the model *choose whether and which* tool to call and you run something; structured output forces one shape for the reply and you read it. In 1.4 the model decided to call `lookup_faq`; here the model fills a form and our code decides.

## 4. Related tools

- **Raw OpenAI SDK** (what `chat.py` uses): fewer layers, you see exact requests, `client.responses.parse(text_format=Model)` also does Pydantic structured output. Cost of LangChain: another abstraction, more dependencies (installed: langchain-core, langchain-openai, langsmith). Benefit: messages that fit `add_messages`, one interface across providers (swap in Anthropic by changing the class), `with_structured_output` handling `strict`/fallbacks. Anthropic's advice (in the [agentic note](2026-10-02-agentic-architectures.md)): frameworks can hide prompts; check what is sent when debugging.
- **`create_agent(..., response_format=...)`** in `langchain` (the Structured output page): the agent-level version, with provider vs tool strategy and retry on validation errors. Not installed here.
- **TypedDict or dataclass schemas** work too (return plain dicts); Pydantic gives validation and instances.
- **Instructor, Outlines**: other structured-output libraries; not needed.

## 5. Hands-on exercises

1. Offline: `.venv/bin/python -c "from graph import Understanding; import json; print(json.dumps(Understanding.model_json_schema(), ensure_ascii=False, indent=1))"`. Check: `enum: ["faq","other"]` and both descriptions appear.
2. `.venv/bin/python -c "import inspect; from langchain_openai import ChatOpenAI as C; print(inspect.signature(C.with_structured_output))"`. Check: the default `method`.
3. Offline: `from langchain_core.messages import AIMessage; AIMessage('x', usage_metadata={'input_tokens':3,'output_tokens':2,'total_tokens':5})`. Check: `.usage_metadata`, and `.id` is `None` until a reducer (`add_messages`) assigns one.
4. Pydantic validation: `Understanding(intent="maybe", topic="")`. Check: `ValidationError` naming the allowed values. This is the failure `parsing_error` would hold.
5. (Needs key, costs a fraction of a cent) Call `understander.invoke([HumanMessage("გამარჯობა")])` in a REPL. Check: `result["parsed"].intent == "other"`; print `result["raw"].usage_metadata`.
6. Edit the `intent` description to something vague and rerun exercise 5 with a SIM question. Check: whether the label changes; this is why descriptions need eval cases.

## 6. Self-check

1. Why does `understand` use `include_raw=True`? 2. How does a `Field(description=...)` reach the model? 3. What does `Literal["faq","other"]` do to the request? 4. Structured output vs function calling: who decides what happens next? 5. Name two costs and two benefits of `ChatOpenAI` over the raw SDK. 6. Does a schema-valid answer mean a correct one?

<details><summary>Answers</summary>

1. To get token usage from the raw `AIMessage` and to receive a parse failure as `parsed=None` instead of an exception. 2. It is written into the JSON Schema sent with the request (`response_format` or a tool). 3. It becomes an enum, restricting values. 4. Structured output: your code reads the filled form and decides; function calling: the model chooses a tool and your code executes it. 5. Costs: extra layer hiding the request, more dependencies; benefits: message objects compatible with LangGraph reducers, provider-swappable interface, built-in structured output. 6. No; the shape is guaranteed, the content is not.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-6, reading `understand` | 30 min |
| B. Another AI tutor | Comparing providers' structured-output modes | 30 min |
| C. Primary docs | Exact parameters and defaults | 1 h |
| D. Video/course | Seeing it demoed | 1 h |

**A.** Paste: "Read learning/notes/2026-10-03-langchain-chat-models-structured-output.md and graph.py (the `understand` node). Walk me through exercises 1-6; for 5 and 6 tell me the cost first."

**B.** NotebookLM with the C links. Prompt: "Using https://docs.langchain.com/oss/python/langchain/models, https://docs.langchain.com/oss/python/langchain/messages and https://docs.langchain.com/oss/python/langchain/structured-output, explain messages, the Runnable interface and structured output (provider vs tool strategy), with a Pydantic example, then quiz me."

**C.**
- LangChain, Models: <https://docs.langchain.com/oss/python/langchain/models>. invoke/stream/batch, `with_structured_output`, retries, usage metadata. *(opened)*
- LangChain, Messages: <https://docs.langchain.com/oss/python/langchain/messages>. Message types, `id`, `usage_metadata`, `AnyMessage`. *(opened)*
- ChatOpenAI integration: <https://docs.langchain.com/oss/python/integrations/chat/openai>. The three structured-output methods, `strict`. *(opened)*
- LangChain, Structured output: <https://docs.langchain.com/oss/python/langchain/structured-output>. Provider vs tool strategy, supported schema types. *(opened)*
- Pydantic, Fields: <https://pydantic.dev/docs/validation/latest/concepts/fields/>. `description` and other JSON-schema parameters; it links to "Customizing JSON Schema". *(opened)*

**D.** I could not confirm a specific video with creator and title for `with_structured_output` (search results were blog posts, a Medium article and an unverified video of unclear creator). Search YouTube for "LangChain with_structured_output Pydantic" and prefer the LangChain channel. For the broader picture, the LangChain Academy course in the [LangGraph note](2026-10-03-langgraph-in-practice.md) uses chat models and structured output in Module 1 (routers).
