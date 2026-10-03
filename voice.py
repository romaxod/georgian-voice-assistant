"""Step 2.5: push-to-talk voice loop for the ჯიხვი assistant.

    Enter → record → Enter → STT (Azure) → graph (LangGraph + MCP) → speech-text → TTS (Azure) → play

Each turn prints the transcript, the graph's trace (including the lookup_faq tool call), the reply,
the text the voice reads if the speech-text step changed it, and the time each stage took. The
number that matters to the caller is how long the silence lasts after they stop talking: STT +
graph + speech-text + TTS, printed as "until the reply starts".

The text pipeline is graph.py's, unchanged: run_turn() is the same function the text chat uses, so
the graph and its evals don't know whether a question was typed or spoken.

Blocking calls (the microphone, Azure, playback) run directly in the main thread, not in
asyncio.to_thread: nothing else needs the event loop while they run, and this way Ctrl-C stops them
right away (see graph.read_line for why asyncio otherwise delays it).

Run:  python voice.py                         push-to-talk: Enter starts recording, Enter stops it.
                                              Typing a question instead also works (skips STT).
      python voice.py --wav audio/q1.wav ...  use recorded files as the questions, one turn each
      python voice.py --no-play               don't play the reply (it's still synthesized and saved)
      python voice.py --voice eka             the other Georgian voice
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
from speech import (AUDIO_DIR, SAMPLE_RATE, SAMPLE_WIDTH, VOICES, Recorder, SpeechError, peak_level, play,
                    speech_config, synthesize, transcribe, wav_info, write_wav)
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


def speak(text: str, args: argparse.Namespace, times: dict) -> None:
    """speech-text → TTS → playback, adding each stage's time to `times`."""
    start = time.perf_counter()
    spoken = speakable(text)
    times["speech-text"] = time.perf_counter() - start
    if spoken != text:
        print(f"  [speech-text] {spoken}")
    if leftover_latin(spoken):
        print(f"  [speech-text] still in Latin letters, the voice will mangle: {leftover_latin(spoken)}")

    start = time.perf_counter()
    try:
        audio = synthesize(spoken, args.voice)
    except SpeechError as e:
        print(f"  [tts] {e}  (the reply is only on screen this turn)")
        return
    times["tts"] = time.perf_counter() - start
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
                     args: argparse.Namespace) -> None:
    """One turn: a recorded question (wav) or a typed one, through the graph, spoken back."""
    times: dict[str, float] = {}
    question = typed
    if wav is not None:
        start = time.perf_counter()
        try:
            with ctrl_c_interrupts():
                question = transcribe(wav)
        except SpeechError as e:
            print(f"  [stt] {e}")
            return
        times["stt"] = time.perf_counter() - start
        print(f"თქვენ (STT, {wav_info(wav)[3]:.1f} s of audio): {question or '(nothing recognized)'}")
        if not question:
            print(f"ჯიხვი: {NOT_HEARD_REPLY}")
            with ctrl_c_interrupts():
                speak(NOT_HEARD_REPLY, args, times)
            print_times(times)
            return

    await ensure_faq_server(faq)
    start = time.perf_counter()
    reply = await run_turn(graph, config, question)
    times["graph"] = time.perf_counter() - start
    print(f"ჯიხვი: {reply}")
    with ctrl_c_interrupts():
        speak(reply, args, times)
    print_times(times)


async def voice_chat(args: argparse.Namespace) -> None:
    load_dotenv()
    speech_config()  # fail now, not after the first recording, if the Azure key is missing
    started = time.perf_counter()
    async with FaqClient() as faq:
        graph = chat_graph(faq, args.simulate_tool_error, started)
        config = new_config(args.max_steps)

        if args.wav:  # scripted: each file is one turn of the same conversation
            for wav in args.wav:
                print(f"\n[{wav}]")
                await voice_turn(wav, "", graph, config, faq, args)
            return

        print(f"ჯიხვი voice assistant ({VOICES[args.voice]}). Press Enter, ask in Georgian, press Enter "
              'again. You can also type a question. "/reset" starts a new conversation, "exit" quits.')
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
                await voice_turn(wav, line, graph, config, faq, args)
            except SpeechError as e:  # the microphone couldn't be opened or failed mid-recording
                print(f"Error: {e}")
            except (EOFError, KeyboardInterrupt):
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="Push-to-talk voice chat with the ჯიხვი assistant.")
    parser.add_argument("--wav", type=Path, nargs="+", help="use these recordings as the questions")
    parser.add_argument("--voice", choices=VOICES, default="giorgi")
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
