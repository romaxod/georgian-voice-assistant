# YAML data files and validating them with Pydantic

*(short note)* Step 3.1, `data/eval_cases.yaml` + `eval_cases.py`. Checked 2026-10-07 against PyYAML 6.0.3 (run locally) and the docs below. Pydantic basics (`BaseModel`, `Field`, `Literal`) are in [LangChain chat models and structured output](2026-10-03-langchain-chat-models-structured-output.md). What the cases mean: [Designing an LLM eval test set](2026-10-07-designing-an-llm-eval-test-set.md).

## 1. What and why

**Problem:** hand-written test data needs comments, multi-line text and readable Georgian, and a typo in it must not silently weaken the tests. So: write it in YAML, then validate it with Pydantic before anything uses it.

**YAML syntax used in this file** (all verified with `yaml.safe_load`):
- List of maps: `- id: x` starts an item; indentation nests (spaces only).
- Flow style (JSON-like, one line): `outcome: [answer, clarify]`, `setup: {tool: fail_once}`.
- `>-` **folded block scalar**: following indented lines join into one string with spaces (blank line = newline); `-` strips the final newline. Used for long `why:` and `judge:` text. (`|` keeps newlines.)
- `#` starts a comment. JSON has none; this is the main reason for YAML here.
- **Quotes are needed when a plain value would be misparsed.** `a: has: colon` is a ScannerError (`: ` inside a plain value), `a: "hi" there` a ParserError (starts with `"` but continues), `@` or `%` at the start is an error. So `why: '"I want to change [it]": ...'` is wrapped in single quotes. Also `reply_has: ["15"]` quotes numbers: unquoted `15` would load as an int, `"1-3"` is a string anyway, and `yes`/`no` load as booleans in YAML 1.1 (PyYAML) - quote them.
- Georgian is plain UTF-8; read with `read_text(encoding="utf-8")`.

**`yaml.safe_load` vs `yaml.load`.** YAML tags can name Python objects. PyYAML's docs: `yaml.load` "is as powerful as `pickle.load` and so may call any Python function". Test: `yaml.safe_load('a: !!python/object/apply:os.getcwd []')` raises `ConstructorError`; the unsafe loader runs `os.getcwd()` and returns its result. `safe_load` builds only dicts, lists, strings, numbers, booleans, null. Use it always, even for your own files (habit, and files get shared).

**YAML vs JSON.** Hand-written, commented, multi-line: YAML. Machine-written output (`runs/`, API payloads): JSON (stricter, faster, no surprises like `no` -> `False`). The FAQ data stays JSON for the same reason.

**Pydantic validation of a data file:**
- `ConfigDict(extra="forbid")`: unknown keys raise an error. Default is `ignore`, so `reply_hass:` (typo) would be dropped, the check would never run, and the case would pass forever.
- `Literal[...]` limits a value to listed options; `Category.__args__` returns the tuple so code can loop over every category (we use it to count cases per category).
- `Field(min_length=1)`, `Field(ge=1)`, `Field(pattern=r"^[a-z0-9-]+$")`: length, minimum, regex constraints without code.
- `@field_validator("outcome")`: checks one field after parsing; raise `ValueError` with a helpful message (ours lists the allowed outcomes).
- `@model_validator(mode="after")`: checks the whole object once fields are valid (ours: "the case checks nothing" / "last turn is a setup turn"). Must return `self`.
- `CaseFile.model_validate(raw)` takes the loaded dict; on failure raises `ValidationError` collecting *all* problems, not just the first.
- Rules that need outside data (FAQ ids exist in `data/faq.json`, duplicate ids, minimum per category) can't be field rules, so `load_cases` checks them in plain Python and reports them together.

**Reading an error location.** `cases.1.turns.0.expect.reply_hass` = key `cases`, item **1** (second case; 0-based), `turns` item 0, `expect`, field `reply_hass`; type `extra_forbidden` ("Extra inputs are not permitted"). Verified: `e.errors()[0]['loc']` gives `('cases', 1, 'turns', 0, 'expect', 'reply_hass')`.

## 2. In this repo

Break test (copy of the file): `reply_hass` typo, outcome `handoff:gave_up`, FAQ id `port-number`, 2 off_topic cases. Output: `extra_forbidden` at the location above, `unknown outcome ['handoff:gave_up']`, then our own `facts_include has ids not in data/faq.json: ['port-number']` and `category 'off_topic' has 2 cases, needs at least 3`; exit 1. A missing file gives `[Errno 2] No such file or directory`, exit 1. PyYAML 6.0.3 was already in `requirements.txt` (a LangChain dependency), so YAML added no dependency.

## 3. How it fits

`yaml.safe_load` (text -> plain dicts) then `model_validate` (dicts -> typed objects, or errors) then the runner in 3.2 gets objects it can trust. Validate at the boundary, once.

## 4. Related tools

- **JSON Schema** can validate YAML/JSON files too (editor support); Pydantic keeps the rules next to Python code.
- **`ruamel.yaml`** (YAML 1.2, keeps comments on write) and **StrictYAML** (no implicit typing) fix the `no` -> `False` surprises (named in [Real Python's YAML tutorial](https://realpython.com/python-yaml/)); we only read, so PyYAML is enough.
- **TOML** (`tomllib`, stdlib) suits config; deeply nested lists of cases are clumsier.

## Copying a validated object: `model_copy(update=...)` vs `model_validate` *(added 2026-10-08)*

**Problem:** `voice_evals.py` needs the same eval case with only its first `user` turn replaced by an STT transcript. Build it again from scratch, or copy and patch?

- `case.model_copy(update={"user": text})` returns a copy with those fields replaced. It is **shallow**: nested lists and objects are shared with the original unless you pass `deep=True`. We replace `turns` with a new list, so nothing shared gets mutated.
- **`update` skips validation.** The Pydantic page doesn't spell this out, so I checked locally: with `user: str = Field(min_length=1)`, `model_copy(update={"user": ""})` gives `user == ''` with no error, while `Model.model_validate({**obj.model_dump(), "user": ""})` raises `ValidationError`. A copy can therefore break the rules the file loader enforced.
- In `voice_evals.py` that is safe because an empty transcript is handled before the copy (reported as `not_heard`, graph not run). Remember that guard if you reuse the pattern.
- Use `model_validate` on a modified `model_dump()` when the new value comes from outside and the rules must hold. Use `model_copy` when you control the value and want a cheap copy.
- Source (opened 2026-10-08): [Pydantic Models, model copy section](https://pydantic.dev/docs/validation/latest/concepts/models/) confirms `update=` and shallow vs `deep=True`; the no-validation behaviour is from the run above.

## Sources (opened 2026-10-07)

- [PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation): the `yaml.load` warning and `safe_load`.
- [YAML 1.2.2 spec](https://yaml.org/spec/1.2.2/): chapter 7 flow collections, 8.1 block scalars (folded `>`, chomping `-`); dense, read only when stuck.
- [Real Python: YAML, the Missing Battery in Python](https://realpython.com/python-yaml/): readable intro with PyYAML.
- [Pydantic: Configuration `extra`](https://pydantic.dev/docs/validation/latest/api/pydantic/config/): `'ignore'`, `'forbid'`, `'allow'`.
- [Pydantic: Validators](https://pydantic.dev/docs/validation/latest/concepts/validators/): field vs model validators, modes, raising `ValueError`.
