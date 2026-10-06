"""Step 2.5: push-to-talk voice loop for the ჯიხვი assistant.

    Enter → record → Enter → STT → graph (LangGraph + MCP) → speech-text → TTS → play

Each turn prints the transcript, the graph's trace (including the lookup_faq tool call), the reply,
the text the voice reads if the speech-text step changed it, and the time each stage took. The
number that matters to the caller is how long the silence lasts after they stop talking: STT +
graph + speech-text + TTS, printed as "until the reply starts".

The text pipeline is graph.py's, unchanged: run_turn() is the same function the text chat uses, so
the graph and its evals don't know whether a question was typed or spoken.

Blocking calls (the microphone, Azure, playback) run directly in the main thread, not in
asyncio.to_thread: nothing else needs the event loop while they run, and this way Ctrl-C stops them
right away (see graph.read_line for why asyncio otherwise delays it).

Since step 2.6a, STT and TTS come from providers.py: Azure by default, or ElevenLabs (Scribe v2 and
an ElevenLabs voice) with Azure as the automatic fallback, chosen by TTS_PROVIDER / STT_PROVIDER in
.env or --tts / --stt here. The loop prints which provider served each turn.

Run:  python voice.py                         push-to-talk: Enter starts recording, Enter stops it.
                                              Typing a question instead also works (skips STT).
      python voice.py --wav audio/q1.wav ...  use recorded files as the questions, one turn each
      python voice.py --no-play               don't play the reply (it's still synthesized and saved)
      python voice.py --voice eka             the other Georgian voice (Azure)
      python voice.py --tts elevenlabs --stt elevenlabs   ElevenLabs, falling back to Azure
      python voice.py --stt elevenlabs --no-keyterms      Scribe v2 without the domain keyterms
      python voice.py --simulate-tool-error always   same break tests as graph.py
"""
import argparse
import asyncio
import signal
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

from faq_client import FaqClient
from graph import MAX_STEPS, chat_graph, ensure_faq_server, new_config, read_line, run_turn
from providers import PROVIDERS, Provider, make_stt, make_tts
from speech import (AUDIO_DIR, SAMPLE_RATE, SAMPLE_WIDTH, VOICES, Recorder, SpeechError, peak_level, play,
                    speech_config, wav_info, write_wav)
from speech_text import leftover_latin, speakable

QUESTION_WAV = AUDIO_DIR / "last_question.wav"  # overwritten every turn; play it to hear what STT heard
REPLY_WAV = AUDIO_DIR / "last_reply.wav"
MIN_SECONDS = 0.5   # shorter recordings are an accidental double Enter, not a question
MIN_PEAK = 0.02     # quieter than this is silence (the mic is muted or blocked by Windows)
# Said without the graph when STT heard nothing: the turn isn't a question, so it isn't kept in the history.
NOT_HEARD_REPLY = "ბოდიში, ვერ გავიგე. გთხოვთ, გაიმეოროთ."


@contextmanager
def ctrl_c_interrupts() -> Iterator[None]:
    """Make Ctrl-C raise KeyboardInterrupt right away during a blocking call (as in graph.read_line)."""
    asyncio_handler = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, asyncio_handler)


def record_question() -> Path | None:
    """Push-to-talk: record from now until Enter. Returns the WAV path, or None if it was too short or silent."""
    recorder = Recorder()
    recorder.start()
    try:
        read_line("  ● recording... press Enter to stop ")
    finally:
        pcm = recorder.stop()  # also on Ctrl-C, so the microphone is released
    seconds = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
    peak = peak_level(pcm)
    print(f"  [mic] {seconds:.1f} s, peak level {peak:.0%}")
    if seconds < MIN_SECONDS:
        print("  (too short; press Enter, speak, then press Enter again)")
        return None
    if peak < MIN_PEAK:
        print("  (almost silent. Check Windows Settings > Privacy > Microphone, allow desktop apps)")
        return None
    return write_wav(QUESTION_WAV, pcm)


def speak(text: str, tts: Provider, args: argparse.Namespace, times: dict) -> None:
    """speech-text → TTS → playback, adding each stage's time to `times`."""
    start = time.perf_counter()
    spoken = speakable(text)
    times["speech-text"] = time.perf_counter() - start
    if spoken != text:
        print(f"  [speech-text] {spoken}")
    if leftover_latin(spoken):
        print(f"  [speech-text] still in Latin letters, the voice will mangle: {leftover_latin(spoken)}")

    start = time.perf_counter()
    timing: dict[str, float] = {}
    try:
        audio = tts.synthesize(spoken, timing)
    except SpeechError as e:
        print(f"  [tts] {e}  (the reply is only on screen this turn)")
        return
    times["tts"] = time.perf_counter() - start
    if "first_audio" in timing:
        print(f"  [tts] {tts.used}: first audio after {timing['first_audio']:.2f} s, all of it after {times['tts']:.2f} s")
    REPLY_WAV.write_bytes(audio)
    if args.no_play:
        return
    start = time.perf_counter()
    try:
        play(REPLY_WAV)
    except SpeechError as e:
        print(f"  [play] {e}")
        return
    times["playback"] = time.perf_counter() - start


def print_times(times: dict) -> None:
    """One line: each stage's time, and the silence the caller hears after they stop talking."""
    waiting = [stage for stage in ("stt", "graph", "speech-text", "tts") if stage in times]
    parts = [f"{stage} {times[stage]:.2f} s" for stage in waiting]
    line = " + ".join(parts) + f" = {sum(times[s] for s in waiting):.1f} s until the reply starts"
    if "playback" in times:
        line += f"; playback {times['playback']:.1f} s"
    print(f"  [time] {line}")


async def voice_turn(wav: Path | None, typed: str, graph, config: dict, faq: FaqClient,
                     stt: Provider, tts: Provider, args: argparse.Namespace) -> None:
    """One turn: a recorded question (wav) or a typed one, through the graph, spoken back."""
    times: dict[str, float] = {}
    question = typed
    if wav is not None:
        start = time.perf_counter()
        try:
            with ctrl_c_interrupts():
                question = stt.transcribe(wav)
        except SpeechError as e:
            print(f"  [stt] {e}")
            return
        times["stt"] = time.perf_counter() - start
        print(f"თქვენ (STT {stt.used}, {wav_info(wav)[3]:.1f} s of audio): {question or '(nothing recognized)'}")
        if not question:
            print(f"ჯიხვი: {NOT_HEARD_REPLY}")
            with ctrl_c_interrupts():
                speak(NOT_HEARD_REPLY, tts, args, times)
            print_times(times)
            return

    await ensure_faq_server(faq)
    start = time.perf_counter()
    reply = await run_turn(graph, config, question)
    times["graph"] = time.perf_counter() - start
    print(f"ჯიხვი: {reply}")
    with ctrl_c_interrupts():
        speak(reply, tts, args, times)
    print_times(times)


async def voice_chat(args: argparse.Namespace) -> None:
    load_dotenv()
    speech_config()  # fail now, not after the first recording, if the Azure key (also the fallback) is missing
    stt, tts = make_stt(args.stt, keyterms=not args.no_keyterms), make_tts(args.tts, args.voice)
    started = time.perf_counter()
    async with FaqClient() as faq:
        graph = chat_graph(faq, args.simulate_tool_error, started)
        config = new_config(args.max_steps)

        if args.wav:  # scripted: each file is one turn of the same conversation
            print(f"STT: {stt.name}; TTS: {tts.name}")
            for wav in args.wav:
                print(f"\n[{wav}]")
                await voice_turn(wav, "", graph, config, faq, stt, tts, args)
            return

        print(f"ჯიხვი voice assistant (STT: {stt.name}; TTS: {tts.name}). Press Enter, ask in Georgian, "
              'press Enter again. You can also type a question. "/reset" starts a new conversation, "exit" quits.')
        while True:
            try:
                line = read_line("\n[Enter = speak] > ").strip()
                if line.lower() in ("exit", "quit"):
                    break
                if line == "/reset":
                    config = new_config(args.max_steps)
                    print("(new conversation)")
                    continue
                wav = None if line else record_question()
                if not line and wav is None:
                    continue
                await voice_turn(wav, line, graph, config, faq, stt, tts, args)
            except SpeechError as e:  # the microphone couldn't be opened or failed mid-recording
                print(f"Error: {e}")
            except (EOFError, KeyboardInterrupt):
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="Push-to-talk voice chat with the ჯიხვი assistant.")
    parser.add_argument("--wav", type=Path, nargs="+", help="use these recordings as the questions")
    parser.add_argument("--voice", choices=VOICES, default="giorgi", help="Azure voice (also the fallback's)")
    parser.add_argument("--tts", choices=PROVIDERS, help="TTS provider (default: TTS_PROVIDER in .env, else azure)")
    parser.add_argument("--stt", choices=PROVIDERS, help="STT provider (default: STT_PROVIDER in .env, else azure)")
    parser.add_argument("--no-keyterms", action="store_true", help="don't send Scribe the domain keyterms")
    parser.add_argument("--no-play", action="store_true", help="don't play the reply")
    parser.add_argument("--simulate-tool-error", choices=["once", "always"],
                        help="make the FAQ lookup fail, to test the error path")
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS,
                        help=f"LangGraph step limit per turn (default {MAX_STEPS})")
    args = parser.parse_args()
    for wav in args.wav or []:
        if not wav.is_file():
            sys.exit(f"Error: {wav} not found.")
    try:
        asyncio.run(voice_chat(args))
    except SpeechError as e:
        sys.exit(f"Error: {e}")
    except KeyboardInterrupt:
        print("\n(stopped)")


if __name__ == "__main__":
    main()
