"""Step 1.5: Georgian speech smoke test with Azure Speech (speech-to-text and text-to-speech) from WSL.

Record a question, transcribe it, synthesize a spoken reply to a WAV file, and play it.
Audio goes through files on purpose: on Linux the Speech SDK opens the microphone and speakers
through ALSA, which WSL doesn't connect to Windows. WSLg does run a PulseAudio server, so recording
and playback go through it with pasimple (a small wrapper around libpulse-simple, no sudo needed).

Run:  python speech_smoke.py record q1 [--seconds 5]   record the mic to audio/q1.wav (16 kHz, 16-bit, mono)
      python speech_smoke.py stt audio/q1.wav           transcribe a WAV file as Georgian (ka-GE)
      python speech_smoke.py tts ["text"] [--voice eka] [--out audio/reply.wav] [--no-play]
      python speech_smoke.py play audio/reply.wav       play any WAV file
"""
import argparse
import os
import sys
import threading
import time
import wave
from array import array
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
import pasimple
from dotenv import load_dotenv

AUDIO_DIR = Path(__file__).parent / "audio"  # gitignored: recordings of a voice are personal data
LANGUAGE = "ka-GE"
VOICES = {"giorgi": "ka-GE-GiorgiNeural", "eka": "ka-GE-EkaNeural"}  # Giorgi rated higher (SETUP.md §2)

# Azure STT's default input format. The SDK reads the WAV header, but other formats risk worse results.
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # bytes per sample = 16-bit
CHANNELS = 1

# Mtavruli capitals U+1C90-U+1CBF sit exactly 0xBC0 above the Mkhedruli letters U+10D0-U+10FF
MTAVRULI_TO_MKHEDRULI = {cp: cp - 0xBC0 for cp in range(0x1C90, 0x1CC0) if cp not in (0x1CBB, 0x1CBC)}

DEFAULT_REPLY = "eSIM-ის გასააქტიურებლად გახსენით ჯიხვის აპლიკაცია და დაასკანერეთ QR კოდი."


def speech_config() -> speechsdk.SpeechConfig:
    load_dotenv()
    key, region = os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        sys.exit("Error: AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set in .env.")
    return speechsdk.SpeechConfig(subscription=key, region=region)


def explain_cancel(details, what: str) -> str:
    """Turn an SDK cancellation into one readable line instead of an object dump."""
    hints = {
        speechsdk.CancellationErrorCode.AuthenticationFailure: "the key was rejected; check AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in .env",
        speechsdk.CancellationErrorCode.ConnectionFailure: "couldn't reach Azure; check the internet connection and the region",
        speechsdk.CancellationErrorCode.TooManyRequests: "F0 limit hit (1 concurrent STT request, 20 TTS requests per minute); wait and retry",
        speechsdk.CancellationErrorCode.BadRequest: "Azure rejected the request; check the language, voice name or text",
    }
    # The SDK names the same field differently: `code` on recognition, `error_code` on synthesis
    code = details.code if hasattr(details, "code") else details.error_code
    hint = hints.get(code, "see the details below")
    return f"Error: {what} failed: {hint}.\n  ({code.name}: {details.error_details})"


def describe_wav(path: Path, for_stt: bool = False) -> float:
    """Print the WAV format (and, before STT, warn if it isn't what Azure expects); return the duration in seconds."""
    with wave.open(str(path), "rb") as wav:
        rate, width, channels, frames = wav.getframerate(), wav.getsampwidth(), wav.getnchannels(), wav.getnframes()
    seconds = frames / rate
    print(f"{path.name}: {rate} Hz, {width * 8}-bit, {channels} channel(s), {seconds:.1f} s")
    if for_stt and (rate, width, channels) != (SAMPLE_RATE, SAMPLE_WIDTH, CHANNELS):
        print(f"  warning: Azure STT expects {SAMPLE_RATE} Hz, 16-bit, mono; results may be worse")
    return seconds


def record(name: str, seconds: int) -> Path:
    AUDIO_DIR.mkdir(exist_ok=True)
    path = AUDIO_DIR / f"{name}.wav"
    print(f"Recording {seconds} s to {path.relative_to(Path(__file__).parent)} ... speak now")
    try:
        # Blocks for the whole duration; the file is only written after all audio has been read
        pasimple.record_wav(str(path), seconds, format=pasimple.PA_SAMPLE_S16LE,
                            channels=CHANNELS, sample_rate=SAMPLE_RATE)
    except KeyboardInterrupt:
        sys.exit("\nRecording cancelled; nothing was saved.")
    with wave.open(str(path), "rb") as wav:
        samples = array("h", wav.readframes(wav.getnframes()))  # "h" = signed 16-bit, like S16LE
    peak = max(map(abs, samples), default=0) / 32768  # loudest sample as a fraction of full scale
    print(f"Done. Peak level {peak:.0%}")
    if peak < 0.02:
        print("  warning: almost silent. Check Windows Settings > Privacy > Microphone (allow desktop apps)")
    return path


def to_mkhedruli(text: str) -> str:
    """Azure capitalizes the first letter of each sentence, and for Georgian that gives a Mtavruli
    capital (e.g. "Გ", U+1C92) instead of the normal letter ("გ", U+10D2). Georgian text doesn't use
    capitals, and "Გამარჯობა" != "გამარჯობა" would break keyword search and eval comparisons.
    Only Georgian letters are mapped back, so English words like "QR" keep their case."""
    return text.translate(MTAVRULI_TO_MKHEDRULI)


def transcribe(path: Path) -> str:
    seconds = describe_wav(path, for_stt=True)
    config = speech_config()
    config.speech_recognition_language = LANGUAGE  # no auto-detect: it can't switch mid-sentence anyway
    audio = speechsdk.audio.AudioConfig(filename=str(path))
    recognizer = speechsdk.SpeechRecognizer(speech_config=config, audio_config=audio)

    # Continuous recognition: the SDK splits the audio at pauses and fires `recognized` once per
    # utterance, on its own thread. recognize_once() would stop after the first sentence.
    # Careful: an exception inside these callbacks is swallowed by the SDK's thread, not shown.
    parts, failure = [], []
    done = threading.Event()

    def on_recognized(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            parts.append(evt.result.text)

    def on_canceled(evt):
        # `canceled` also fires with reason EndOfStream when the file simply ends; only Error is a failure
        if evt.cancellation_details.reason == speechsdk.CancellationReason.Error:
            failure.append(evt.cancellation_details)

    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(lambda evt: done.set())

    start = time.perf_counter()
    recognizer.start_continuous_recognition()
    finished = done.wait(timeout=seconds + 30)  # a safety net so a stuck session can't hang the script
    recognizer.stop_continuous_recognition()
    elapsed = time.perf_counter() - start

    if failure:
        sys.exit(explain_cancel(failure[0], "speech-to-text"))
    if not finished:
        sys.exit("Error: speech-to-text didn't finish in time.")
    if not parts:
        sys.exit(f"No speech recognized. Is the recording silent? Listen to it: python speech_smoke.py play {path}")
    print(f"STT took {elapsed:.2f} s for {seconds:.1f} s of audio ({len(parts)} utterance(s))")
    return to_mkhedruli(" ".join(parts))


def synthesize(text: str, voice: str, out: Path) -> Path:
    config = speech_config()
    config.speech_synthesis_voice_name = VOICES[voice]
    # A RIFF format includes the WAV header, so the bytes can be written straight to a .wav file
    config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    # audio_config=None: keep the audio in result.audio_data instead of the SDK opening a speaker (ALSA)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)

    start = time.perf_counter()
    result = synthesizer.speak_text_async(text).get()
    elapsed = time.perf_counter() - start

    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        sys.exit(explain_cancel(result.cancellation_details, "text-to-speech"))
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(result.audio_data)
    print(f"TTS ({VOICES[voice]}) took {elapsed:.2f} s, {len(result.audio_data):,} bytes -> {out.name}")
    return out


def play(path: Path) -> None:
    describe_wav(path)
    try:
        pasimple.play_wav(str(path))
    except pasimple.PaSimpleError as e:
        sys.exit(f"Error: couldn't play through PulseAudio ({e}). Is WSLg running? (echo $PULSE_SERVER)")


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

    if args.command == "record":
        record(args.name, args.seconds)
    elif args.command == "stt":
        print(f"transcript: {transcribe(args.wav)}")
    elif args.command == "tts":
        print(f"text: {args.text}")
        out = synthesize(args.text, args.voice, args.out)
        if not args.no_play:
            play(out)
    elif args.command == "play":
        play(args.wav)


if __name__ == "__main__":
    main()
