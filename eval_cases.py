"""Step 3.1: load and validate the eval test set (data/eval_cases.yaml).

The test set is data, not code: each case is a short conversation plus the behavior each turn must
show (see the comment at the top of the YAML file). This module turns the YAML into Pydantic
objects and rejects anything the runner (step 3.2) would misread: an unknown field (a typo like
"reply_hass" would otherwise be silently ignored, and the check would never run), an unknown
category, outcome or FAQ id, duplicate case ids, or a category with fewer than MIN_PER_CATEGORY cases.

Run:  python eval_cases.py                              validate and print the cases per category
      python eval_cases.py --file other_cases.yaml      validate another file
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CASES_FILE = Path("data/eval_cases.yaml")
FAQ_FILE = Path("data/faq.json")
MIN_PER_CATEGORY = 3

Category = Literal["ordinary", "ambiguous", "missing_info", "multi_turn", "tool_failure",
                   "false_action", "code_switched", "off_topic"]
Intent = Literal["faq", "action", "ambiguous", "human", "other"]
# graph.py's HANDOFF_REPLIES keys. Copied, not imported: importing graph.py loads LangChain and
# OpenAI (~19 s on /mnt/c), too slow for a file check. The runner imports graph anyway and checks
# that the two lists still match.
HANDOFF_REASONS = ("asked_for_human", "still_unclear", "no_facts", "tool_error", "false_action_claim",
                   "not_answered")
OUTCOMES = ("answer", "clarify", *(f"handoff:{reason}" for reason in HANDOFF_REASONS))


class Strict(BaseModel):
    # extra="forbid": an unknown key is an error, not silently dropped (that's how typos hide).
    model_config = ConfigDict(extra="forbid")


class Expect(Strict):
    """What one turn must show. Every field is optional; a missing one isn't checked."""
    outcome: list[str] | None = Field(None, min_length=1)
    intent: list[Intent] | None = Field(None, min_length=1)
    tool_called: bool | None = None
    facts_include: list[str] = []
    lookup_attempts: int | None = Field(None, ge=1)
    reply_has: list[str] = []    # "a|b" = either one
    reply_lacks: list[str] = []
    judge: str | None = None

    @field_validator("outcome")
    @classmethod
    def known_outcomes(cls, outcomes: list[str] | None) -> list[str] | None:
        unknown = [o for o in outcomes or [] if o not in OUTCOMES]
        if unknown:
            raise ValueError(f"unknown outcome {unknown}; use one of {list(OUTCOMES)}")
        return outcomes


class Turn(Strict):
    user: str = Field(min_length=1)
    expect: Expect | None = None  # None: a setup turn, nothing checked


class Setup(Strict):
    tool: Literal["ok", "fail_once", "fail_always", "down"] = "ok"


class Case(Strict):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    category: Category
    why: str = Field(min_length=1)
    setup: Setup = Setup()
    turns: list[Turn] = Field(min_length=1)

    @model_validator(mode="after")
    def something_checked(self) -> "Case":
        if not any(turn.expect for turn in self.turns):
            raise ValueError("no turn has an expect block, so the case checks nothing")
        if self.turns[-1].expect is None:
            raise ValueError("the last turn has no expect block (a setup turn at the end does nothing)")
        return self


class CaseFile(Strict):
    cases: list[Case]


def load_cases(path: Path = CASES_FILE) -> list[Case]:
    """Read and validate a cases file. Raises ValueError with every problem found."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))  # safe_load: plain data, no Python objects
    except yaml.YAMLError as e:
        raise ValueError(f"{path} isn't valid YAML: {e}") from e
    try:
        cases = CaseFile.model_validate(raw).cases
    except ValidationError as e:
        raise ValueError(f"{path}: {e}") from e

    problems = []
    faq_ids = {entry["id"] for entry in json.loads(FAQ_FILE.read_text(encoding="utf-8"))}
    for case in cases:
        for n, turn in enumerate(case.turns, 1):
            unknown = [i for i in (turn.expect.facts_include if turn.expect else []) if i not in faq_ids]
            if unknown:
                problems.append(f"{case.id} turn {n}: facts_include has ids not in {FAQ_FILE}: {unknown}")
    duplicates = [i for i, count in Counter(c.id for c in cases).items() if count > 1]
    if duplicates:
        problems.append(f"duplicate case ids: {duplicates}")
    per_category = Counter(c.category for c in cases)
    for category in Category.__args__:
        if per_category[category] < MIN_PER_CATEGORY:
            problems.append(f"category {category!r} has {per_category[category]} cases, "
                            f"needs at least {MIN_PER_CATEGORY}")
    if problems:
        raise ValueError(f"{path}:\n  " + "\n  ".join(problems))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the eval test set and list it per category.")
    parser.add_argument("--file", type=Path, default=CASES_FILE, help=f"cases file (default {CASES_FILE})")
    args = parser.parse_args()
    try:
        cases = load_cases(args.file)
    except (ValueError, OSError) as e:
        sys.exit(f"Error: {e}")

    for category in Category.__args__:
        in_category = [c for c in cases if c.category == category]
        print(f"{category:<14} {len(in_category)}  {', '.join(c.id for c in in_category)}")
    turns = sum(len(c.turns) for c in cases)
    checked = sum(1 for c in cases for t in c.turns if t.expect)
    judged = sum(1 for c in cases for t in c.turns if t.expect and t.expect.judge)
    print(f"\n{len(cases)} cases, {turns} turns ({checked} with checks, {judged} with an LLM-judge question). OK")


if __name__ == "__main__":
    main()
