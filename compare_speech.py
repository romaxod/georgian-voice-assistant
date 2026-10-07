"""Step 2.6a: compare speech providers on the same inputs, changing one thing at a time.

    stt   Roman's recordings (1.5) through Azure → Scribe v2 → Scribe v2 + keyterms. Prints word error
          rate (WER) and whether each English term came through, and saves runs/stt_compare_<time>.json.
    tts   The same 10 Georgian sentences through Azure Giorgi, the premade ElevenLabs voice and (step 2.6b)
          Roman's ElevenLabs clone. Saves the clips to audio/tts_compare/ and the timings (first audio,
          total) to runs/tts_compare_<time>.json. --no-clone leaves the clone out (2.6a's two columns).
    rate  Blind rating of the latest tts run: plays the clips in random order without saying which
          provider made each, asks pronunciation and naturalness (1–5), then reveals the averages.

The providers are called directly here, without WithFallback: in a comparison a failure has to show
as a failure, not be quietly answered by Azure. Both TTS providers get the same speakable() text the
voice loop sends, so the comparison is "what the caller would hear" from each.

Run:  python compare_speech.py stt [--wav audio/q1.wav ...]
      python compare_speech.py tts [--no-clone]
      python compare_speech.py rate
"""
import argparse
import json
import random
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from providers import KEYTERMS, AzureSTT, AzureTTS, ElevenLabsTTS, Provider, ScribeSTT
from speech import AUDIO_DIR, SpeechError, play, wav_info
from speech_text import speakable

RUNS = Path(__file__).parent / "runs"  # gitignored, like audio/
CLIPS = AUDIO_DIR / "tts_compare"

# Roman's recordings from step 1.5 (SETUP.md §2): what he said, and the English (or loan) terms in it
# with the spellings that count as "came through". A Georgian-script spelling counts: a transcript
# saying "იმეილზე" is as useful to the graph as "email-ზე". Matched at the start of a word, since
# Georgian suffixes are glued on ("eSIM-ის", "აიფონზე").
RECORDINGS = {
    "q1.wav": ("რა ღირს როუმინგი ევროპაში?", {"როუმინგი": ["როუმინგ"]}),
    "c1.wav": ("API-ს key როგორ შევცვალო?", {"API": ["api", "ეიპიაი", "ეი პი აი"], "key": ["key", "ქი "]}),
    "c2.wav": ("API-ს key როგორ შევცვალო?", {"API": ["api", "ეიპიაი", "ეი პი აი"], "key": ["key", "ქი "]}),
    "c3.wav": ("როუმინგი როგორ ჩავრთო iPhone-ზე?", {"როუმინგი": ["როუმინგ"], "iPhone": ["iphone", "აიფონ"]}),
    "c4.wav": ("eSIM-ის QR კოდი email-ზე მომივა?",
               {"eSIM": ["esim", "ისიმ", "ი-სიმ", "ი სიმ"], "QR": ["qr", "ქიუარ", "ქიუ არ"],
                "email": ["email", "e-mail", "იმეილ", "მეილ"]}),
}

# FAQ answers that cover what the voice must say: prices (₾, tetri), plan names with a Latin letter,
# times, 24/7, SIM/eSIM/QR, GB, 4G/5G, a menu path, and plain Georgian.
TTS_SENTENCES = ["plans-overview", "plan-m", "plan-change", "roaming-europe", "international-calls",
                 "esim-activation", "sim-lost", "branch-hours", "app-chat", "coverage-5g"]


def words(text: str) -> list[str]:
    """Lowercase words without punctuation ("API-ს" → ["api", "ს"]), for WER on both sides alike."""
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate: (substitutions + deletions + insertions) / words in the reference,
    the edit distance between the two word lists (Levenshtein, one row at a time)."""
    ref, hyp = words(reference), words(hypothesis)
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1] / len(ref)


def terms_found(transcript: str, terms: dict[str, list[str]]) -> list[str]:
    text = " " + transcript.lower() + " "
    return [term for term, forms in terms.items()
            if any(re.search(r"(?<!\w)" + re.escape(form), text) for form in forms)]


def save(name: str, data: dict) -> Path:
    RUNS.mkdir(exist_ok=True)
    path = RUNS / f"{name}_{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compare_stt(wavs: list[Path]) -> None:
    # One change per column: Azure → Scribe (another model) → Scribe + keyterms (same model, biased)
    providers: list[Provider] = [AzureSTT(), ScribeSTT([]), ScribeSTT(KEYTERMS)]
    print(f"keyterms ({len(KEYTERMS)}): {', '.join(KEYTERMS)}\n")
    results, off = [], set()
    for wav in wavs:  # one request at a time: Azure F0 allows a single concurrent STT request
        said, terms = RECORDINGS.get(wav.name, ("", {}))
        print(f"{wav.name} ({wav_info(wav)[3]:.1f} s)  said: {said or '(unknown)'}")
        for provider in providers:
            row = {"file": wav.name, "said": said, "provider": provider.name}
            if provider.name in off:
                continue
            start = time.perf_counter()
            try:
                row["transcript"] = provider.transcribe(wav)
            except SpeechError as e:
                row["error"] = str(e)
                print(f"  {provider.name:<24} ERROR {e}")
                if not e.retryable:
                    off.add(provider.name)
                    print(f"  {'':<24} (skipping {provider.name} for the other files)")
                results.append(row)
                continue
            row["seconds"] = round(time.perf_counter() - start, 2)
            if said:
                row["wer"] = round(wer(said, row["transcript"]), 2)
                row["terms_found"] = terms_found(row["transcript"], terms)
                row["terms_total"] = len(terms)
            score = (f"WER {row['wer']:.0%}, terms {len(row['terms_found'])}/{len(terms)}" if said else "")
            print(f"  {provider.name:<24} {row['transcript']}   [{score}, {row['seconds']:.1f} s]")
            results.append(row)
        print()

    print("Summary (mean over files with a known text):")
    for provider in providers:
        rows = [r for r in results if r["provider"] == provider.name and "wer" in r]
        if rows:
            found = sum(len(r["terms_found"]) for r in rows)
            total = sum(r["terms_total"] for r in rows)
            print(f"  {provider.name:<24} WER {statistics.mean(r['wer'] for r in rows):.0%}, terms {found}/{total}, "
                  f"{statistics.mean(r['seconds'] for r in rows):.1f} s per file")
    print(f"\nsaved {save('stt_compare', {'keyterms': KEYTERMS, 'results': results}).relative_to(Path.cwd())}")


def compare_tts(clone: bool = True) -> None:
    answers = {e["id"]: e["answer"] for e in json.loads((Path(__file__).parent / "data/faq.json").read_text("utf-8"))}
    # All voices are synthesized fresh in every run, even the ones rated before: the rating has to
    # compare them in one sitting on one scale, and the clips of an older run may come from older models.
    voices: dict[str, Provider] = {"azure": AzureTTS("giorgi"), "elevenlabs": ElevenLabsTTS("ready")}
    if clone:
        voices["clone"] = ElevenLabsTTS("clone")
    providers = list(voices.values())
    CLIPS.mkdir(parents=True, exist_ok=True)
    clips = []
    for n, faq_id in enumerate(TTS_SENTENCES, 1):
        text = answers[faq_id]
        spoken = speakable(text)
        print(f"s{n:02} {text}")
        for key, provider in voices.items():
            timing: dict[str, float] = {}
            start = time.perf_counter()
            try:
                audio = provider.synthesize(spoken, timing)
            except SpeechError as e:
                sys.exit(f"  {provider.name}: {e}")  # a rating with one side missing isn't a comparison
            total = time.perf_counter() - start
            path = CLIPS / f"s{n:02}_{key}.wav"
            path.write_bytes(audio)
            clips.append({"sentence": n, "text": text, "spoken": spoken, "provider": provider.name,
                          "path": str(path), "first_audio": round(timing["first_audio"], 2),
                          "total": round(total, 2), "audio_seconds": round(wav_info(path)[3], 1)})
            print(f"  {provider.name:<36} first audio {timing['first_audio']:.2f} s, total {total:.2f} s, "
                  f"{clips[-1]['audio_seconds']:.1f} s of speech")

    print("\nMedians:")
    for provider in providers:
        rows = [c for c in clips if c["provider"] == provider.name]
        print(f"  {provider.name:<36} first audio {statistics.median(c['first_audio'] for c in rows):.2f} s, "
              f"total {statistics.median(c['total'] for c in rows):.2f} s")
    chars = sum(len(speakable(answers[i])) for i in TTS_SENTENCES)
    path = save("tts_compare", {"characters_per_provider": chars, "clips": clips})
    print(f"\n{chars} characters per provider. Saved {path.relative_to(Path.cwd())}. "
          "Now rate them blind: python compare_speech.py rate")


def ask_score(prompt: str, clip_path: Path) -> int:
    while True:
        answer = input(prompt).strip().lower()
        if answer == "r":
            play(clip_path)
        elif answer in {"1", "2", "3", "4", "5"}:
            return int(answer)
        else:
            print("  type 1-5, or r to hear it again")


def rate() -> None:
    runs = sorted(RUNS.glob("tts_compare_*.json"))
    if not runs:
        sys.exit("No tts run yet. Run: python compare_speech.py tts")
    path = runs[-1]
    data = json.loads(path.read_text("utf-8"))
    clips = data["clips"]
    order = list(range(len(clips)))
    random.shuffle(order)  # so neither provider always comes first and the clip order can't give it away
    print(f"{len(clips)} clips from {path.name}, in random order. For each: listen, then score\n"
          "  pronunciation (are the words and numbers said right?) and naturalness (does it sound human?),\n"
          "  1 = bad ... 5 = like a native speaker. Type r to hear a clip again.\n")
    for k, i in enumerate(order, 1):
        clip = clips[i]
        print(f"clip {k}/{len(clips)}: {clip['text']}")
        play(Path(clip["path"]))
        clip["pronunciation"] = ask_score("  pronunciation 1-5: ", Path(clip["path"]))
        clip["naturalness"] = ask_score("  naturalness 1-5: ", Path(clip["path"]))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")  # keep partial ratings

    print("\n| Provider | Pronunciation | Naturalness | First audio (median) | Total (median) |\n|---|---|---|---|---|")
    for name in dict.fromkeys(c["provider"] for c in clips):
        rows = [c for c in clips if c["provider"] == name]
        print(f"| {name} | {statistics.mean(c['pronunciation'] for c in rows):.1f} | "
              f"{statistics.mean(c['naturalness'] for c in rows):.1f} | "
              f"{statistics.median(c['first_audio'] for c in rows):.2f} s | "
              f"{statistics.median(c['total'] for c in rows):.2f} s |")
    print(f"\nratings saved in {path.relative_to(Path.cwd())}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Azure and ElevenLabs speech on the same inputs.")
    sub = parser.add_subparsers(dest="command", required=True)
    stt = sub.add_parser("stt", help="STT on Roman's recordings: Azure, Scribe v2, Scribe v2 + keyterms")
    stt.add_argument("--wav", type=Path, nargs="+", default=[AUDIO_DIR / name for name in RECORDINGS])
    tts = sub.add_parser("tts", help="synthesize the 10 test sentences with every voice")
    tts.add_argument("--no-clone", action="store_true", help="only Azure and the premade ElevenLabs voice")
    sub.add_parser("rate", help="blind-rate the latest tts run")
    args = parser.parse_args()
    load_dotenv()
    try:
        if args.command == "stt":
            missing = [str(w) for w in args.wav if not w.is_file()]
            if missing:
                sys.exit(f"Error: not found: {', '.join(missing)}")
            compare_stt(args.wav)
        elif args.command == "tts":
            compare_tts(clone=not args.no_clone)
        else:
            rate()
    except SpeechError as e:
        sys.exit(f"Error: {e}")
    except KeyboardInterrupt:
        print("\n(stopped)")


if __name__ == "__main__":
    main()
