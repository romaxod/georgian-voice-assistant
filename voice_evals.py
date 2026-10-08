"""Step 3.4: the voice check. Spoken versions of eval cases, through STT and then the same checks as
run_evals.py, side by side with the typed text, to see how STT errors propagate through the pipeline.

A recording is the spoken first turn of one case in data/eval_cases.yaml. Every recording runs three ways:
    typed    the case's own text (no STT): the baseline, what 3.2 measures
    azure    Azure STT (ka-GE) → transcript → graph
    scribe   ElevenLabs Scribe v2 with the domain keyterms (the voice loop's default) → graph
The transcript replaces the case's first turn; the case's later turns stay typed, and every check
(rules and judge) stays the same, because a spoken question should get the same behavior as a typed one.
So a spoken run that fails where the typed one passes is an STT error that got through to the reply.

The providers are called directly, without WithFallback (as in compare_speech.py): a failed STT call
has to show as a failure, not be quietly answered by the other provider. Recordings are processed one
at a time: Azure F0 allows a single concurrent STT request, and latency is measured per call.
The graph's reply isn't spoken: TTS doesn't change what's checked here, it was measured in 2.6a/2.6b,
and it would spend ElevenLabs credit. `python voice.py --wav <file>` runs the full loop with sound.

Recordings: the five from step 1.5 (q1, c1, c2, c3, c4; c2 is a second take of c1), plus any
audio/eval/<case-id>.wav made with `record`.

Run:  python voice_evals.py record [case-id ...]   record spoken versions (default: SUGGESTED)
      python voice_evals.py run                    every recording, typed + azure + scribe
      python voice_evals.py run --repeat 3         3 times (STT and the graph aren't deterministic)
      python voice_evals.py run --no-judge         rules only
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import AuthenticationError

import graph
from compare_speech import RECORDINGS, wer
from eval_cases import CASES_FILE, Case, load_cases
from faq_client import FaqClient
from providers import KEYTERMS, AzureSTT, Provider, ScribeSTT
from run_evals import JUDGE_MODEL, RUNS_DIR, Verdict, case_passed, first_failure, git_version, run_case, short_hash
from speech import AUDIO_DIR, SAMPLE_RATE, SAMPLE_WIDTH, Recorder, SpeechError, peak_level, play, wav_info, write_wav
from voice import MIN_PEAK, MIN_SECONDS, NOT_HEARD_REPLY

SPOKEN_DIR = AUDIO_DIR / "eval"  # audio/eval/<case-id>.wav; audio/ is gitignored (Roman's voice)
# The 1.5 recordings that say a case's first turn word for word (what was said: compare_speech.RECORDINGS)
OLD_RECORDINGS = {"q1.wav": "multi-roaming-followup", "c1.wav": "cs-api-key", "c2.wav": "cs-api-key",
                  "c3.wav": "cs-roaming-iphone", "c4.wav": "cs-esim-qr-email"}
# What `record` asks for by default: cases the 1.5 recordings don't cover. Plain Georgian (the 1.5 set
# is almost all code-switched), an English term inside a false-action request, and the 3.3 fix case,
# whose Latin "L" a Georgian STT may spell as "ელ".
SUGGESTED = ["ord-plans", "act-block-sim", "act-change-plan"]
SOURCES = ("typed", "azure", "scribe")


def find_recordings(cases: dict[str, Case]) -> list[tuple[Path, str]]:
    """(wav, case id) for every recording that exists, checked against the case's text."""
    found = []
    for name, case_id in OLD_RECORDINGS.items():
        wav = AUDIO_DIR / name
        if not wav.exists():
            continue
        said = RECORDINGS[name][0]
        if said != cases[case_id].turns[0].user:
            sys.exit(f"Error: {name} says {said!r}, but {case_id}'s first turn is {cases[case_id].turns[0].user!r}")
        found.append((wav, case_id))
    for wav in sorted(SPOKEN_DIR.glob("*.wav")):
        if wav.stem not in cases:
            print(f"(skipping {wav}: no case with id {wav.stem!r})")
            continue
        found.append((wav, wav.stem))
    return found


def with_first_turn(case: Case, text: str) -> Case:
    """The same case with its first message replaced by what STT heard; expectations unchanged."""
    first = case.turns[0].model_copy(update={"user": text})
    return case.model_copy(update={"turns": [first, *case.turns[1:]]})


async def run_source(case: Case, wav: Path | None, stt: Provider | None, faq: FaqClient, judge) -> dict:
    """One run of one recording through one source (stt=None: the typed text)."""
    said = case.turns[0].user
    row = {"case": case.id, "category": case.category, "file": wav.name if wav else None,
           "source": stt.name if stt else "typed", "said": said, "heard": said, "wer": 0.0, "stt_seconds": 0.0}
    if stt is not None:
        start = time.perf_counter()
        try:
            # In a thread: STT blocks for 1-2 s, and the MCP client's tasks share this event loop
            row["heard"] = await asyncio.to_thread(stt.transcribe, wav)
        except SpeechError as e:
            row.update(heard=None, wer=None, error=str(e), passed=False, turns=[])
            return row
        row["stt_seconds"] = round(time.perf_counter() - start, 2)
        row["wer"] = round(wer(said, row["heard"]), 2)
    if not row["heard"]:
        # The voice loop says NOT_HEARD_REPLY without running the graph (voice.py); same here.
        row.update(passed=False, turns=[], outcome="not_heard", reply=NOT_HEARD_REPLY)
        return row
    await graph.ensure_faq_server(faq)
    turns = await run_case(with_first_turn(case, row["heard"]), faq, judge)
    first = turns[0]
    row.update(passed=case_passed(case, turns), outcome=first.outcome, intent=first.intent, topic=first.topic,
               facts=first.facts, reply=first.reply, graph_seconds=first.seconds,
               failure=first_failure(turns), turns=[asdict(t) for t in turns])
    return row


def effect(row: dict, typed: dict) -> str:
    """What STT did to this run, compared with the typed run of the same case in the same repeat."""
    if row["source"] == "typed":
        return ""
    if row["heard"] is None:
        return "STT error"
    if row["passed"]:
        return "same" if typed["passed"] else "passed (typed failed)"
    if not typed["passed"]:
        return "fails typed too"
    return "STT broke it" if row["heard"] != row["said"] else "graph (exact transcript)"


async def run_all(recordings: list[tuple[Path, str]], cases: dict[str, Case], args) -> list[dict]:
    judge = None if args.no_judge else ChatOpenAI(model=JUDGE_MODEL).with_structured_output(Verdict, include_raw=True)
    stts = [AzureSTT(), ScribeSTT(KEYTERMS)]
    rows = []
    async with FaqClient() as faq:
        if not faq.connected:
            sys.exit(f"Error: couldn't start the FAQ server: {faq.last_error}")
        for repeat in range(1, args.repeat + 1):
            typed = {}  # case id → its typed run this repeat (c1 and c2 share one)
            for wav, case_id in recordings:
                case = cases[case_id]
                if case_id not in typed:
                    typed[case_id] = await run_source(case, None, None, faq, judge)
                    typed[case_id]["repeat"] = repeat
                    rows.append(typed[case_id])
                    print_row(typed[case_id], "")
                for stt in stts:
                    row = await run_source(case, wav, stt, faq, judge)
                    row["repeat"] = repeat
                    row["effect"] = effect(row, typed[case_id])
                    rows.append(row)
                    print_row(row, row["effect"])
    return rows


def short_source(name: str) -> str:
    """"scribe_v2 + 18 keyterms" → "scribe", for the table columns."""
    return name.split("_")[0]


def print_row(row: dict, note: str) -> None:
    label = row["file"] or "(typed)"
    mark = "pass" if row["passed"] else "FAIL"
    heard = row["heard"] if row["heard"] is not None else f"ERROR {row.get('error')}"
    wer_text = f"{row['wer']:.0%}" if row["wer"] is not None else "-"
    print(f"{row['case']:<24}{label:<20}{short_source(row['source']):<7}{mark}  "
          f"{row.get('outcome', '-'):<26}WER {wer_text:>4}  {heard}" + (f"   [{note}]" if note else ""))
    if not row["passed"] and row.get("failure"):
        print(f"{'':<24}  {row['failure']}")


def summarize(rows: list[dict]) -> dict:
    out = {}
    for source in {r["source"] for r in rows}:
        mine = [r for r in rows if r["source"] == source]
        heard = [r for r in mine if r["heard"] is not None]
        stt = [r["stt_seconds"] for r in heard if r["stt_seconds"]]
        graph_s = [r["graph_seconds"] for r in mine if "graph_seconds" in r]
        out[short_source(source)] = {
            "provider": source,
            "passed": sum(r["passed"] for r in mine), "runs": len(mine),
            "mean_wer": round(statistics.mean(r["wer"] for r in heard), 2) if heard else None,
            "exact_transcripts": sum(r["heard"] == r["said"] for r in heard),
            "stt_errors": len(mine) - len(heard),
            "stt_median_s": round(statistics.median(stt), 2) if stt else 0.0,
            "graph_median_s": round(statistics.median(graph_s), 2) if graph_s else 0.0,
            "effects": {e: sum(r.get("effect") == e for r in mine) for e in {r.get("effect") for r in mine} if e},
        }
    return out


def print_summary(summary: dict) -> None:
    print(f"\n{'source':<8}{'cases passed':>14}{'mean WER':>10}{'exact':>8}{'STT s':>8}{'graph s':>9}  effect of STT")
    for name in SOURCES:
        s = summary.get(name)
        if not s:
            continue
        wer_text = f"{s['mean_wer']:.0%}" if s["mean_wer"] is not None else "-"
        effects = ", ".join(f"{k} {v}" for k, v in sorted(s["effects"].items()))
        print(f"{name:<8}{s['passed']:>8}/{s['runs']:<5}{wer_text:>10}{s['exact_transcripts']:>5}/{s['runs']:<2}"
              f"{s['stt_median_s']:>8}{s['graph_median_s']:>9}  {effects}")


def record(case_ids: list[str], cases: dict[str, Case]) -> None:
    """Push-to-talk recording of each case's first turn into audio/eval/<case-id>.wav."""
    SPOKEN_DIR.mkdir(parents=True, exist_ok=True)
    print("For each sentence: press Enter, read it aloud as you'd ask it, press Enter again.\n")
    for case_id in case_ids:
        text = cases[case_id].turns[0].user
        while True:
            input(f"{case_id}:  {text}\n  press Enter to start ")
            recorder = Recorder()
            try:
                recorder.start()
            except SpeechError as e:
                sys.exit(f"Error: {e}")
            try:
                input("  ● recording... press Enter to stop ")
            finally:
                pcm = recorder.stop()  # also on Ctrl-C, so the microphone is released
            seconds, peak = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH), peak_level(pcm)
            print(f"  {seconds:.1f} s, peak level {peak:.0%}")
            if seconds < MIN_SECONDS or peak < MIN_PEAK:
                print("  (too short or almost silent; once more)")
                continue
            wav = write_wav(SPOKEN_DIR / f"{case_id}.wav", pcm)
            play(wav)
            if input("  Enter = keep it, r = record again: ").strip().lower() != "r":
                print(f"  saved {wav}\n")
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="Run spoken versions of eval cases through STT and the graph.")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="record spoken versions of cases into audio/eval/")
    rec.add_argument("case_ids", nargs="*", default=SUGGESTED, help=f"case ids (default {' '.join(SUGGESTED)})")
    run = sub.add_parser("run", help="run every recording through typed / Azure / Scribe and the checks")
    run.add_argument("--repeat", type=int, default=1, help="run everything N times (default 1)")
    run.add_argument("--no-judge", action="store_true", help="skip the LLM judge (rules only)")
    args = parser.parse_args()

    load_dotenv()
    cases = {c.id: c for c in load_cases()}
    if args.command == "record":
        unknown = [i for i in args.case_ids if i not in cases]
        if unknown:
            sys.exit(f"Error: no case with id {unknown}")
        record(args.case_ids, cases)
        return

    recordings = find_recordings(cases)
    if not recordings or args.repeat < 1:
        sys.exit("Error: no recordings found (or --repeat < 1)")
    for wav, case_id in recordings:
        print(f"{wav} ({wav_info(wav)[3]:.1f} s) → {case_id}")
    print(f"\nkeyterms for Scribe ({len(KEYTERMS)}): {', '.join(KEYTERMS)}")
    print(f"graph {graph.MODEL}; judge: {'off' if args.no_judge else JUDGE_MODEL}\n")
    started = datetime.now()
    try:
        rows = asyncio.run(run_all(recordings, cases, args))
    except AuthenticationError:
        sys.exit("Error: the OpenAI key was rejected. Check OPENAI_API_KEY in .env.")
    summary = summarize(rows)
    print_summary(summary)

    RUNS_DIR.mkdir(exist_ok=True)
    out = RUNS_DIR / f"voice_eval_{started:%Y%m%d-%H%M%S}.json"
    meta = {"started": started.isoformat(timespec="seconds"), "git": git_version(), "model": graph.MODEL,
            "judge_model": None if args.no_judge else JUDGE_MODEL, "keyterms": KEYTERMS,
            "cases_sha": short_hash(CASES_FILE.read_text(encoding="utf-8")),
            "recordings": {str(w): c for w, c in recordings}, "args": vars(args)}
    out.write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
