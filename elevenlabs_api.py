"""Step 2.6a: ElevenLabs text-to-speech and speech-to-text (Scribe v2), called over its HTTP API.

The functions mirror speech.py's Azure ones: synthesize() returns a complete WAV file as bytes and
transcribe() returns Georgian text, and both raise SpeechError with a message meant for the user.
That's what lets providers.py swap one for the other. stream() (step 2.6b) yields the same audio
chunk by chunk as it's generated, so the voice loop can start playing before the reply is complete.

Two voices (step 2.6b): "ready" is the premade voice in ELEVENLABS_VOICE_ID (Brian, picked in 2.6a)
and "clone" is Roman's Instant Voice Clone in ELEVENLABS_CLONE_VOICE_ID. Both IDs stay in .env, so
switching is a config change and the comparison can use both in one run.

Plain HTTP with httpx (already installed: langchain-core and langgraph-sdk need it) instead of the `elevenlabs`
SDK: it's two endpoints, and calling them directly shows exactly what goes over the wire, keeps
control of timeouts and error messages, and lets synthesize() time the first audio chunk.

Models (checked 2026-10-04 on elevenlabs.io/docs/overview/models): `eleven_v4`, `eleven_v4_turbo`
and `eleven_v3` list Georgian; `eleven_multilingual_v2` (the API's default model_id, so it's always
sent) and `eleven_flash_v2_5` don't. Turbo is the default: ~100 ms latency and half the price of v4.

Run:  python elevenlabs_api.py tts "გამარჯობა" [--out audio/el.wav]   synthesize one text
      python elevenlabs_api.py tts "გამარჯობა" --voice clone           the same in Roman's cloned voice
      python elevenlabs_api.py stt audio/q1.wav [--keyterms]          transcribe one file
"""
import argparse
import io
import os
import sys
import time
import wave
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx
from dotenv import load_dotenv

from speech import AUDIO_DIR, SpeechError, to_mkhedruli

API = "https://api.elevenlabs.io/v1"
TTS_MODEL = "eleven_v4_turbo"  # ELEVENLABS_MODEL in .env overrides it (e.g. eleven_v4)
STT_MODEL = "scribe_v2"
STT_LANGUAGE = "kat"  # ISO 639-3 Georgian, as the Scribe docs list it; stops short clips being taken for another language
# pcm_24000 = raw 16-bit mono samples at 24 kHz with no header, the same audio format as Azure's output.
# Raw PCM (not mp3) because PulseAudio plays it as-is, and its chunks can be timed as they arrive.
TTS_FORMAT, TTS_RATE = "pcm_24000", 24_000
# connect: how long to wait for the server to answer at all; the first number: for each read
TTS_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
STT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
VOICE_SETTINGS = {"ready": "ELEVENLABS_VOICE_ID", "clone": "ELEVENLABS_CLONE_VOICE_ID"}  # voice → .env name

HINTS = {
    401: "the key was rejected or the credit is used up; check ELEVENLABS_API_KEY and the account's usage",
    402: "this needs a paid plan (or more credit)",
    404: "not found; check the voice ID in .env (ELEVENLABS_VOICE_ID / ELEVENLABS_CLONE_VOICE_ID)",
    422: "ElevenLabs rejected the request's fields",
    429: "too many requests at once for this plan; wait and retry",
}


def setting(name: str) -> str:
    """A required ElevenLabs value from .env. Missing → a non-retryable error, so the fallback takes over."""
    load_dotenv()
    value = os.getenv(name)
    if not value:
        raise SpeechError(f"{name} is not set in .env (SETUP.md §4)", retryable=False)
    return value


def http_error(response: httpx.Response, what: str) -> SpeechError:
    """Turn an error response into one readable line. ElevenLabs sends {"detail": {"status", "message"}},
    or for a 422 a list of {"loc", "msg"} per bad field."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = response.text[:200]
    if isinstance(detail, dict):
        detail = f"{detail.get('status') or detail.get('code', '')}: {detail.get('message', '')}"
    elif isinstance(detail, list):
        detail = "; ".join(f"{'.'.join(map(str, d.get('loc', [])))}: {d.get('msg')}" for d in detail)
    code = response.status_code
    hint = HINTS.get(code, "ElevenLabs is having problems" if code >= 500 else "see the details below")
    # Only overload and server errors can succeed on a second try; a bad key or field won't
    return SpeechError(f"{what} failed: {hint}.\n  (HTTP {code}: {detail})", retryable=code == 429 or code >= 500)


def network_error(e: httpx.HTTPError, what: str) -> SpeechError:
    if isinstance(e, httpx.TimeoutException):
        return SpeechError(f"{what} timed out ({type(e).__name__})")
    return SpeechError(f"{what} failed: couldn't reach ElevenLabs ({type(e).__name__}: {e})")


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    """Put a WAV header in front of raw 16-bit mono samples."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def stream(text: str, voice: str = "ready") -> Iterator[bytes]:
    """Georgian text-to-speech, yielded as raw 16-bit mono samples at 24 kHz while ElevenLabs generates them.
    `voice` is "ready" or "clone" (VOICE_SETTINGS). Nothing is sent until the first chunk is asked for,
    so a caller that never iterates makes no request."""
    key, voice_id = setting("ELEVENLABS_API_KEY"), setting(VOICE_SETTINGS[voice])
    body = {"text": text, "model_id": os.getenv("ELEVENLABS_MODEL") or TTS_MODEL}
    try:
        # The /stream endpoint sends audio while it's still being generated, so the first chunk
        # arrives long before the last. That gap is the "time to first audio" a streaming player saves.
        with httpx.stream("POST", f"{API}/text-to-speech/{voice_id}/stream", params={"output_format": TTS_FORMAT},
                          headers={"xi-api-key": key}, json=body, timeout=TTS_TIMEOUT) as response:
            if response.status_code != 200:
                response.read()  # a streamed response's body isn't loaded until asked for
                raise http_error(response, "ElevenLabs text-to-speech")
            yield from response.iter_bytes()
    except httpx.HTTPError as e:
        raise network_error(e, "ElevenLabs text-to-speech") from e


def synthesize(text: str, timing: dict | None = None, voice: str = "ready") -> bytes:
    """The whole of stream()'s audio as a WAV file (24 kHz, 16-bit, mono).
    If `timing` is given, timing["first_audio"] is set to the seconds until the first audio arrived."""
    start = time.perf_counter()
    chunks: list[bytes] = []
    for chunk in stream(text, voice):
        if timing is not None and not chunks:
            timing["first_audio"] = time.perf_counter() - start
        chunks.append(chunk)
    pcm = b"".join(chunks)
    if not pcm:
        raise SpeechError("ElevenLabs text-to-speech returned no audio")
    return pcm_to_wav(pcm[: len(pcm) // 2 * 2], TTS_RATE)  # whole 2-byte samples only


def transcribe(path: Path, keyterms: Iterable[str] = (), language: str | None = STT_LANGUAGE) -> str:
    """Speech-to-text of a WAV file with Scribe v2. `keyterms` bias it toward words it should expect
    (up to 1000 per request, each under 50 characters; they cost extra). Returns "" if nothing was said."""
    key = setting("ELEVENLABS_API_KEY")
    # Multipart form fields are strings; a list value is sent as the same field repeated, once per term
    data: dict[str, str | list[str]] = {"model_id": STT_MODEL, "tag_audio_events": "false"}  # no "(laughter)" tags
    if language:
        data["language_code"] = language
    if keyterms := list(keyterms):
        data["keyterms"] = keyterms
    try:
        with path.open("rb") as audio:
            response = httpx.post(f"{API}/speech-to-text", headers={"xi-api-key": key}, data=data,
                                  files={"file": (path.name, audio, "audio/wav")}, timeout=STT_TIMEOUT)
    except httpx.HTTPError as e:
        raise network_error(e, "ElevenLabs speech-to-text") from e
    if response.status_code != 200:
        raise http_error(response, "ElevenLabs speech-to-text")
    return to_mkhedruli(response.json().get("text", "")).strip()


def main() -> None:
    from providers import KEYTERMS  # here, not at the top: providers.py imports this module

    parser = argparse.ArgumentParser(description="Try ElevenLabs TTS or Scribe v2 STT on its own.")
    sub = parser.add_subparsers(dest="command", required=True)
    tts = sub.add_parser("tts", help="synthesize one text to a WAV file")
    tts.add_argument("text")
    tts.add_argument("--out", type=Path, default=AUDIO_DIR / "elevenlabs.wav")
    tts.add_argument("--voice", choices=VOICE_SETTINGS, default="ready", help="premade voice or Roman's clone")
    stt = sub.add_parser("stt", help="transcribe one WAV file")
    stt.add_argument("wav", type=Path)
    stt.add_argument("--keyterms", action="store_true", help=f"send the {len(KEYTERMS)} domain keyterms")
    args = parser.parse_args()
    try:
        start = time.perf_counter()
        if args.command == "tts":
            timing: dict = {}
            args.out.parent.mkdir(exist_ok=True)
            args.out.write_bytes(synthesize(args.text, timing, args.voice))
            print(f"{args.out}: first audio {timing['first_audio']:.2f} s, done {time.perf_counter() - start:.2f} s")
        else:
            text = transcribe(args.wav, KEYTERMS if args.keyterms else ())
            print(f"{text or '(nothing recognized)'}  ({time.perf_counter() - start:.2f} s)")
    except SpeechError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
