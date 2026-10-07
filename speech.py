"""Azure Speech (speech-to-text, text-to-speech) and microphone/speaker access through WSLg's PulseAudio.

Shared by speech_smoke.py (step 1.5, one command at a time) and voice.py (step 2.5, the voice loop).
Functions here raise SpeechError instead of exiting, so the voice loop can report a failed turn and
keep going; the command-line scripts turn it into an exit message.

Audio goes through PulseAudio on purpose: on Linux the Speech SDK opens the microphone and speakers
through ALSA, which WSL doesn't connect to Windows. WSLg runs a PulseAudio server, and pasimple (a
small wrapper around libpulse-simple) talks to it without sudo.
"""
import io
import os
import threading
import time
import wave
from array import array
from collections.abc import Iterable
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


class SpeechError(Exception):
    """A recording, recognition, synthesis or playback failure, with a message meant for the user.

    retryable=False means trying again won't help (a missing or rejected key, no credit left), so a
    fallback (providers.py) stops calling that provider for the rest of the session."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def speech_config() -> speechsdk.SpeechConfig:
    load_dotenv()
    key, region = os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        raise SpeechError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set in .env.", retryable=False)
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
    return f"{what} failed: {hint}.\n  ({code.name}: {details.error_details})"


def wav_info(path: Path) -> tuple[int, int, int, float]:
    """(sample rate, bytes per sample, channels, duration in seconds) of a WAV file."""
    with wave.open(str(path), "rb") as wav:
        rate, width, channels, frames = wav.getframerate(), wav.getsampwidth(), wav.getnchannels(), wav.getnframes()
    return rate, width, channels, frames / rate


def peak_level(pcm: bytes) -> float:
    """The loudest 16-bit sample as a fraction of full scale (0.0 = silence, 1.0 = clipping)."""
    samples = array("h", pcm)  # "h" = signed 16-bit, like S16LE
    return max(map(abs, samples), default=0) / 32768


def write_wav(path: Path, pcm: bytes) -> Path:
    """Save raw 16 kHz 16-bit mono samples (what Recorder returns) as a WAV file."""
    path.parent.mkdir(exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return path


def record_seconds(path: Path, seconds: int) -> bytes:
    """Record a fixed number of seconds to a WAV file and return the samples. Blocks for the whole duration."""
    try:
        pasimple.record_wav(str(path), seconds, format=pasimple.PA_SAMPLE_S16LE,
                            channels=CHANNELS, sample_rate=SAMPLE_RATE)
    except pasimple.PaSimpleError as e:
        raise SpeechError(f"couldn't record through PulseAudio ({e}). Is WSLg running? (echo $PULSE_SERVER)") from e
    with wave.open(str(path), "rb") as wav:
        return wav.readframes(wav.getnframes())


class Recorder:
    """Push-to-talk recording of unknown length: start() opens the microphone and a background thread
    keeps reading it until stop(), which returns the samples (16 kHz, 16-bit, mono).

    The thread is needed because reading the microphone blocks, and the main thread has to wait for
    the key press that ends the recording at the same time."""

    CHUNK = SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS // 10  # 100 ms of audio per read
    # Measured on WSLg: the first read returns ~0.5 s after the stream opens, with only 100 ms of
    # audio in it, so anything said in that first half second is lost. start() waits for it.
    START_TIMEOUT = 3.0

    def __init__(self):
        self._stream: pasimple.PaSimple | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._flowing = threading.Event()  # set once the first audio has arrived
        self._chunks: list[bytes] = []
        self._error: Exception | None = None

    def start(self) -> None:
        # Open the stream here, in the caller's thread, so a missing PulseAudio server raises right away.
        try:
            self._stream = pasimple.PaSimple(pasimple.PA_STREAM_RECORD, pasimple.PA_SAMPLE_S16LE,
                                             CHANNELS, SAMPLE_RATE, app_name="jikhvi-voice")
        except pasimple.PaSimpleError as e:
            raise SpeechError(f"couldn't open the microphone through PulseAudio ({e}). "
                              "Is WSLg running? (echo $PULSE_SERVER)") from e
        self._stop.clear()
        self._flowing.clear()
        self._chunks, self._error = [], None
        # daemon=True: if the program exits mid-recording, this thread doesn't keep it alive
        self._thread = threading.Thread(target=self._read_until_stopped, daemon=True)
        self._thread.start()
        # Return only once audio is really being captured, so "speak now" isn't shown too early
        if not self._flowing.wait(self.START_TIMEOUT):
            self.stop()
            raise SpeechError(f"the microphone sent no audio within {self.START_TIMEOUT:.0f} s")

    def _read_until_stopped(self) -> None:
        try:
            while not self._stop.is_set():
                self._chunks.append(self._stream.read(self.CHUNK))  # blocks until 100 ms are available
                self._flowing.set()
        except pasimple.PaSimpleError as e:
            self._error = e  # an exception in a thread isn't seen by the main thread; stop() re-raises it
            self._flowing.set()  # don't leave start() waiting; stop() reports the error

    def stop(self) -> bytes:
        """End the recording and return what was recorded (at most ~100 ms after the call)."""
        self._stop.set()
        self._thread.join()
        self._stream.close()
        if self._error:
            raise SpeechError(f"the microphone stream failed ({self._error})")
        return b"".join(self._chunks)


def to_mkhedruli(text: str) -> str:
    """Azure capitalizes the first letter of each sentence, and for Georgian that gives a Mtavruli
    capital (e.g. "Გ", U+1C92) instead of the normal letter ("გ", U+10D2). Georgian text doesn't use
    capitals, and "Გამარჯობა" != "გამარჯობა" would break keyword search and eval comparisons.
    Only Georgian letters are mapped back, so English words like "QR" keep their case."""
    return text.translate(MTAVRULI_TO_MKHEDRULI)


def transcribe(path: Path) -> str:
    """Georgian speech-to-text of a WAV file. Returns "" if no speech was recognized."""
    seconds = wav_info(path)[3]
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

    recognizer.start_continuous_recognition()
    finished = done.wait(timeout=seconds + 30)  # a safety net so a stuck session can't hang the program
    recognizer.stop_continuous_recognition()

    if failure:
        raise SpeechError(explain_cancel(failure[0], "speech-to-text"))
    if not finished:
        raise SpeechError("speech-to-text didn't finish in time.")
    return to_mkhedruli(" ".join(parts))


def synthesize(text: str, voice: str = "giorgi", timing: dict | None = None) -> bytes:
    """Georgian text-to-speech. Returns a complete WAV file (24 kHz, 16-bit, mono) as bytes.
    If `timing` is given, timing["first_audio"] is set to the seconds until the first audio arrived."""
    start = time.perf_counter()
    config = speech_config()
    config.speech_synthesis_voice_name = VOICES[voice]
    # A RIFF format includes the WAV header, so the bytes can be written straight to a .wav file
    config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    # audio_config=None: keep the audio in result.audio_data instead of the SDK opening a speaker (ALSA)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
    if timing is not None:
        # `synthesizing` fires on the SDK's thread for every chunk of audio as it arrives; keep the first
        synthesizer.synthesizing.connect(
            lambda evt: timing.setdefault("first_audio", time.perf_counter() - start))
    result = synthesizer.speak_text_async(text).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise SpeechError(explain_cancel(result.cancellation_details, "text-to-speech"))
    return result.audio_data


def wav_pcm(wav_bytes: bytes) -> tuple[bytes, int]:
    """The raw samples and sample rate inside a WAV file held in memory (e.g. synthesize()'s result)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        return wav.readframes(wav.getnframes()), wav.getframerate()


# Streaming playback (step 2.6b). PulseAudio's defaults hold ~2 s of audio and start playing only once
# that buffer is full, which would undo most of what streaming saves. A small target buffer starts
# the sound after PREBUFFER_SECONDS; if the network then falls behind, PulseAudio pauses (a gap) and
# resumes once it has PREBUFFER_SECONDS again.
PLAY_BUFFER_SECONDS = 0.5
PREBUFFER_SECONDS = 0.2


def play_stream(chunks: Iterable[bytes], rate: int) -> dict:
    """Play raw 16-bit mono samples while they're still arriving, and return when they've all been played.

    Returns {"pcm": all the samples, "first_audio": s from the call until the first audio went to the
    speaker, "gaps": estimated pauses (s) where the audio arrived slower than it plays}. There's no
    "all audio received" time: write() blocks while PulseAudio's buffer is full, so the stream is read
    only as fast as it plays, and the last chunk always "arrives" near the end of playback. A SpeechError from `chunks` (a failed TTS) passes through, after
    the part already received has been played as far as it got."""
    def nbytes(seconds: float) -> int:
        return int(seconds * rate) * SAMPLE_WIDTH

    start = time.perf_counter()
    try:
        player = pasimple.PaSimple(pasimple.PA_STREAM_PLAYBACK, pasimple.PA_SAMPLE_S16LE, CHANNELS, rate,
                                   app_name="jikhvi-voice", tlength=nbytes(PLAY_BUFFER_SECONDS),
                                   prebuf=nbytes(PREBUFFER_SECONDS))
    except pasimple.PaSimpleError as e:
        raise SpeechError(f"couldn't play through PulseAudio ({e}). Is WSLg running? (echo $PULSE_SERVER)") from e
    parts: list[bytes] = []
    stats: dict = {"gaps": []}
    leftover = b""  # an HTTP chunk can end in the middle of a 2-byte sample; PulseAudio wants whole samples
    played_from, written = 0.0, 0.0  # when the sound (re)started, and seconds of audio written since then
    try:
        for chunk in chunks:
            now = time.perf_counter()
            parts.append(chunk)
            data, leftover = leftover + chunk, b""
            if len(data) % SAMPLE_WIDTH:
                data, leftover = data[:-1], data[-1:]
            if not data:
                continue
            if "first_audio" not in stats:
                stats["first_audio"] = now - start
                played_from = now
            elif (behind := (now - played_from) - written) > 0.05:
                # The speaker ran out before this chunk came: the caller heard a pause of about `behind`
                stats["gaps"].append(round(behind, 2))
                played_from, written = now, 0.0
            player.write(data)
            written += len(data) / (rate * SAMPLE_WIDTH)
        player.drain()  # wait until the last sample has actually been played
    except pasimple.PaSimpleError as e:
        raise SpeechError(f"playback failed in PulseAudio ({e})") from e
    finally:
        player.close()
        stats["pcm"] = b"".join(parts)
    return stats


def play(path: Path) -> None:
    """Play a WAV file and return when it has finished playing."""
    try:
        pasimple.play_wav(str(path))
    except pasimple.PaSimpleError as e:
        raise SpeechError(f"couldn't play through PulseAudio ({e}). Is WSLg running? (echo $PULSE_SERVER)") from e
