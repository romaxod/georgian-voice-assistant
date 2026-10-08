"""Step 1.5: Georgian speech smoke test with Azure Speech (speech-to-text and text-to-speech) from WSL.

Record a question, transcribe it, synthesize a spoken reply to a WAV file, and play it, one command
at a time. The speech functions themselves live in speech.py (since step 2.5, which reuses them in
the voice loop); this file is the command line around them.

Run:  python speech_smoke.py record q1 [--seconds 5]   record the mic to audio/q1.wav (16 kHz, 16-bit, mono)
      python speech_smoke.py stt audio/q1.wav           transcribe a WAV file as Georgian (ka-GE)
      python speech_smoke.py tts ["text"] [--voice eka] [--out audio/reply.wav] [--no-play]
      python speech_smoke.py play audio/reply.wav       play any WAV file
"""
import argparse
import sys
import time
from pathlib import Path

from speech import (AUDIO_DIR, CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH, VOICES, SpeechError, peak_level, play,
                    record_seconds, synthesize, transcribe, wav_info)

DEFAULT_REPLY = "გერგეტის სამებამდე ასვლა-ჩამოსვლა დაახლოებით 6 კმ-ია, ხოლო საგანგებო შემთხვევაში დარეკეთ 112-ზე."


def describe_wav(path: Path, for_stt: bool = False) -> None:
    """Print the WAV format and, before STT, warn if it isn't what Azure expects."""
    rate, width, channels, seconds = wav_info(path)
    print(f"{path.name}: {rate} Hz, {width * 8}-bit, {channels} channel(s), {seconds:.1f} s")
    if for_stt and (rate, width, channels) != (SAMPLE_RATE, SAMPLE_WIDTH, CHANNELS):
        print(f"  warning: Azure STT expects {SAMPLE_RATE} Hz, 16-bit, mono; results may be worse")


def run(args: argparse.Namespace) -> None:
    if args.command == "record":
        AUDIO_DIR.mkdir(exist_ok=True)
        path = AUDIO_DIR / f"{args.name}.wav"
        print(f"Recording {args.seconds} s to {path.relative_to(Path(__file__).parent)} ... speak now")
        peak = peak_level(record_seconds(path, args.seconds))
        print(f"Done. Peak level {peak:.0%}")
        if peak < 0.02:
            print("  warning: almost silent. Check Windows Settings > Privacy > Microphone (allow desktop apps)")
    elif args.command == "stt":
        describe_wav(args.wav, for_stt=True)
        start = time.perf_counter()
        text = transcribe(args.wav)
        print(f"STT took {time.perf_counter() - start:.2f} s for {wav_info(args.wav)[3]:.1f} s of audio")
        if not text:
            sys.exit(f"No speech recognized. Is the recording silent? Listen to it: python speech_smoke.py play {args.wav}")
        print(f"transcript: {text}")
    elif args.command == "tts":
        print(f"text: {args.text}")
        start = time.perf_counter()
        audio = synthesize(args.text, args.voice)
        args.out.parent.mkdir(exist_ok=True)
        args.out.write_bytes(audio)
        print(f"TTS ({VOICES[args.voice]}) took {time.perf_counter() - start:.2f} s, {len(audio):,} bytes -> {args.out.name}")
        if not args.no_play:
            describe_wav(args.out)
            play(args.out)
    elif args.command == "play":
        describe_wav(args.wav)
        play(args.wav)


def main() -> None:
    parser = argparse.ArgumentParser(description="Azure Speech smoke test for Georgian (ka-GE).")
    commands = parser.add_subparsers(dest="command", required=True)

    rec = commands.add_parser("record", help="record the microphone to audio/<name>.wav")
    rec.add_argument("name")
    rec.add_argument("--seconds", type=int, default=5)

    stt = commands.add_parser("stt", help="transcribe a WAV file")
    stt.add_argument("wav", type=Path)

    tts = commands.add_parser("tts", help="synthesize text to a WAV file and play it")
    tts.add_argument("text", nargs="?", default=DEFAULT_REPLY)
    tts.add_argument("--voice", choices=VOICES, default="giorgi")
    tts.add_argument("--out", type=Path, default=AUDIO_DIR / "reply.wav")
    tts.add_argument("--no-play", action="store_true", help="only write the file")

    ply = commands.add_parser("play", help="play a WAV file")
    ply.add_argument("wav", type=Path)

    args = parser.parse_args()
    if getattr(args, "wav", None) and not args.wav.is_file():
        sys.exit(f"Error: {args.wav} not found.")
    try:
        run(args)
    except SpeechError as e:
        sys.exit(f"Error: {e}")
    except KeyboardInterrupt:
        sys.exit("\nCancelled; nothing was saved." if args.command == "record" else "\nCancelled.")


if __name__ == "__main__":
    main()
