"""Step 2.6a: swappable speech providers. The voice loop talks to "a TTS" and "an STT", and a config
switch decides which company is behind each one, with Azure as the automatic fallback.

    TTS_PROVIDER=elevenlabs   STT_PROVIDER=elevenlabs   in .env (or --tts / --stt on voice.py)
    ELEVENLABS_VOICE=clone    Roman's cloned voice instead of the premade one (or --el-voice on voice.py)

Every provider has the same small interface: TTS.synthesize(text, timing) -> WAV bytes,
TTS.stream(text) -> raw 24 kHz samples chunk by chunk (step 2.6b, for playing while the reply is
still being generated), and STT.transcribe(path) -> text. All of them raise SpeechError. voice.py never imports speech.py's or
elevenlabs_api.py's functions directly, so adding a third provider means one new class here.

WithFallback wraps a primary provider and a backup with the same interface. If the primary fails,
the same call goes to the backup, so the caller still gets an answer, just in the other voice.
If the failure can't fix itself (no key, rejected key, no credit: SpeechError.retryable is False),
the primary is switched off for the rest of the session instead of failing, slowly, on every turn.

Why Azure is the backup and not the other way round: it's the provider the whole pipeline was built
and tested on (1.5, 2.5), and its F0 tier is free, so it can't run out of credit mid-demo.
"""
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

import elevenlabs_api
import speech
from speech import VOICES, SpeechError, wav_pcm

ELEVENLABS_VOICES = tuple(elevenlabs_api.VOICE_SETTINGS)  # "ready" (premade, Brian) / "clone" (Roman's voice)

PROVIDERS = ("azure", "elevenlabs")
FAQ_JSON = Path(__file__).parent / "data" / "faq.json"
# Words a caller of a mobile operator says that a general model may not expect. Kept to the domain on
# purpose: "API" and "key" (in Roman's recordings c1/c2) are NOT here, because keyterms copied from the
# test recordings would make Scribe look better on them than it would be on new questions.
DOMAIN_TERMS = ["ჯიხვი", "როუმინგი", "აპლიკაცია", "ტარიფი", "iPhone", "Android", "SMS", "WiFi", "email"]


def faq_terms() -> list[str]:
    """The Latin-letter terms in the FAQ (SIM, eSIM, GB, QR, 5G, ...): the vocabulary answers are built from."""
    entries = json.loads(FAQ_JSON.read_text(encoding="utf-8"))
    # Not the "id" field: ids are English slugs ("esim-activation"), not words a caller says
    text = json.dumps([[e["topic"], e["question"], e["answer"], e["keywords"]] for e in entries], ensure_ascii=False)
    return sorted(set(re.findall(r"\b(?:[A-Za-z]{2,}|\dG)\b", text)))


KEYTERMS = sorted(set(faq_terms()) | set(DOMAIN_TERMS))


class Provider:
    name = ""

    @property
    def used(self) -> str:
        """The provider that served the last call (differs from `name` only for WithFallback)."""
        return self.name


class AzureTTS(Provider):
    def __init__(self, voice: str = "giorgi"):
        self.voice, self.name = voice, f"azure {VOICES[voice]}"

    def synthesize(self, text: str, timing: dict) -> bytes:
        return speech.synthesize(text, self.voice, timing)

    def stream(self, text: str) -> Iterator[bytes]:
        # One chunk: Azure finishes a reply in ~1.2 s (2.6a), so streaming it would save little.
        # The rate check keeps the promise that every TTS streams 24 kHz, so the player can rely on it.
        pcm, rate = wav_pcm(speech.synthesize(text, self.voice))
        if rate != elevenlabs_api.TTS_RATE:
            raise SpeechError(f"Azure sent {rate} Hz audio, expected {elevenlabs_api.TTS_RATE}")
        yield pcm


class ElevenLabsTTS(Provider):
    def __init__(self, voice: str = "ready"):
        self.voice = voice
        self.name = f"elevenlabs {os.getenv('ELEVENLABS_MODEL') or elevenlabs_api.TTS_MODEL} {voice}"

    def synthesize(self, text: str, timing: dict) -> bytes:
        return elevenlabs_api.synthesize(text, timing, self.voice)

    def stream(self, text: str) -> Iterator[bytes]:
        return elevenlabs_api.stream(text, self.voice)


class AzureSTT(Provider):
    name = "azure"

    def transcribe(self, path: Path) -> str:
        return speech.transcribe(path)


class ScribeSTT(Provider):
    def __init__(self, keyterms: list[str] = KEYTERMS):
        self.keyterms = keyterms
        self.name = f"scribe_v2 + {len(keyterms)} keyterms" if keyterms else "scribe_v2"

    def transcribe(self, path: Path) -> str:
        return elevenlabs_api.transcribe(path, self.keyterms)


class WithFallback(Provider):
    """Try `primary`; if it raises SpeechError, report it and run the same call on `backup`."""

    def __init__(self, primary: Provider, backup: Provider, kind: str):
        self.primary, self.backup, self.kind = primary, backup, kind
        self.name = f"{primary.name} (fallback: {backup.name})"
        self.primary_off = False
        self._used = primary.name

    @property
    def used(self) -> str:
        return self._used

    def _call(self, method: str, *args):
        if not self.primary_off:
            try:
                result = getattr(self.primary, method)(*args)
                self._used = self.primary.name
                return result
            except SpeechError as e:
                self.primary_off = not e.retryable
                then = "for the rest of the session" if self.primary_off else "for this turn"
                print(f"  [{self.kind}] {self.primary.name}: {e}\n  [{self.kind}] using {self.backup.name} {then}")
        self._used = self.backup.name
        return getattr(self.backup, method)(*args)  # if the backup fails too, the caller sees its error

    def synthesize(self, text: str, timing: dict) -> bytes:
        timing.clear()  # don't keep a first-audio time from a primary that failed mid-stream
        return self._call("synthesize", text, timing)

    def transcribe(self, path: Path) -> str:
        return self._call("transcribe", path)

    def stream(self, text: str) -> Iterator[bytes]:
        """Like _call, but the reply is played while it arrives: the backup takes over only if the primary
        fails before its first chunk. After that the caller has already heard part of the reply, and
        starting again from the top in the other voice would be worse than stopping where it broke."""
        if not self.primary_off:
            started = False
            try:
                for chunk in self.primary.stream(text):
                    started, self._used = True, self.primary.name
                    yield chunk
                return
            except SpeechError as e:
                self.primary_off = not e.retryable
                if started:
                    raise
                then = "for the rest of the session" if self.primary_off else "for this turn"
                print(f"  [tts] {self.primary.name}: {e}\n  [tts] using {self.backup.name} {then}")
        self._used = self.backup.name
        yield from self.backup.stream(text)


def choose(kind: str, name: str | None) -> str:
    name = name or os.getenv(f"{kind.upper()}_PROVIDER") or "azure"
    if name not in PROVIDERS:
        raise SpeechError(f"unknown {kind.upper()}_PROVIDER {name!r}; use one of {', '.join(PROVIDERS)}", retryable=False)
    return name


def make_tts(name: str | None = None, azure_voice: str = "giorgi", elevenlabs_voice: str | None = None) -> Provider:
    """The TTS for `name` ("azure" / "elevenlabs"), or TTS_PROVIDER from .env, or Azure. The ElevenLabs
    voice is `elevenlabs_voice`, or ELEVENLABS_VOICE from .env, or the premade "ready" voice."""
    azure = AzureTTS(azure_voice)
    if choose("tts", name) == "azure":
        return azure
    voice = elevenlabs_voice or os.getenv("ELEVENLABS_VOICE") or "ready"
    if voice not in ELEVENLABS_VOICES:
        raise SpeechError(f"unknown ELEVENLABS_VOICE {voice!r}; use one of {', '.join(ELEVENLABS_VOICES)}",
                          retryable=False)
    return WithFallback(ElevenLabsTTS(voice), azure, "tts")


def make_stt(name: str | None = None, keyterms: bool = True) -> Provider:
    """The STT for `name`, or STT_PROVIDER from .env, or Azure. Scribe gets KEYTERMS unless keyterms=False."""
    if choose("stt", name) == "azure":
        return AzureSTT()
    return WithFallback(ScribeSTT(KEYTERMS if keyterms else []), AzureSTT(), "stt")
