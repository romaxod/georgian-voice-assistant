# Audio on Linux and WSL: ALSA, PulseAudio, WSLg, pasimple

Checked 2026-10-03 on WSL2 Ubuntu 24.04 (commands run here), the WSLg README, the ALSA project page, the Python `ctypes` docs and the installed `pasimple` source. The ArchWiki and freedesktop PulseAudio pages refused my fetches (access denied / 403), so the ALSA vs PulseAudio description below comes from the ALSA project page plus search results, not those pages.

## 1. What you're learning, and why it matters

**Problem.** The Azure Speech SDK's default microphone and speaker don't work in WSL, and the machine has no `arecord`, `aplay`, `paplay` or `ffmpeg`, no `libportaudio`, and no sudo without a password. Step 1.5 still needs to record the mic and play audio. To choose a fix you need to know the Linux audio layers.

**The layers**
- **ALSA** (Advanced Linux Sound Architecture): "kernel drivers and a user-space library (alsa-lib)" per the project page. Programs call `libasound.so.2`, which talks to kernel drivers for real sound cards. The SDK on Linux opens mic and speaker through ALSA.
- **PulseAudio**: a **sound server**, a background process that sits between apps and the sound hardware. It mixes several apps, handles volume and device choice, and can be reached over a socket (even from another machine). Apps connect with `libpulse.so.0` or the simpler `libpulse-simple.so.0`.
- **PipeWire**: the newer sound server on many desktops; it also speaks the PulseAudio protocol, so PulseAudio clients keep working.
- A **sink** is an output (speaker), a **source** is an input (microphone).

**How WSL gets sound** ([WSLg README](https://github.com/microsoft/wslg))
- WSL has no sound card. **WSLg** runs a PulseAudio server inside its system distro: "WSLg uses a sink plugin for audio out, and a source plugin for audio in", which move samples between the PulseAudio server and an RDP server, and so to Windows.
- The socket is projected into your distro and `PULSE_SERVER` points at it. Here: `PULSE_SERVER=unix:/mnt/wslg/PulseServer`; `/mnt/wslg` also holds `PulseAudioRDPSink` and `PulseAudioRDPSource`. (A **unix socket** is a file that two processes on the same machine talk through.)
- So PulseAudio clients work; ALSA clients find no card. Bridge: install `libasound2-plugins` (ALSA's `pulse` plugin) and put in `~/.asoundrc`:
```
pcm.default pulse
ctl.default pulse
```
  That sends ALSA apps to PulseAudio. It needs `sudo apt install`, which we didn't have, and I did not test it here (a search result describes it).

## 2. In this repo

Options compared in step 1.5:
| Option | Needs | Verdict |
|---|---|---|
| Azure SDK default mic/speaker | ALSA bridge above | needs sudo |
| `sounddevice` / `PyAudio` | PortAudio (`sudo apt install libportaudio2`) | not installed |
| shell out to `parecord` / `paplay` | `pulseaudio-utils` | not installed |
| `powershell.exe` calling Windows audio | Windows-side script | clumsy |
| **`pasimple`** | `libpulse-simple.so.0` (installed per `ldconfig -p`) | **chosen**, no sudo |

- `pasimple` is a small wrapper over `libpulse-simple`. Its `pa_simple.py` starts with `import ctypes` and calls `ctypes.CDLL('libpulse-simple.so.0')`. **`ctypes`** (standard library) loads a compiled shared library (`.so`, "dlopen" in C terms) and calls its C functions from Python; you declare argument and return types (`argtypes`, `restype`). The ctypes docs warn that mistakes can crash the process, which is why people use a ready-made wrapper.
- Calls used: `pasimple.record_wav(path, seconds, format=pasimple.PA_SAMPLE_S16LE, channels=1, sample_rate=16000)` and `pasimple.play_wav(path)` (it plays, then `drain()`s so the end isn't cut off). `record_wav`'s defaults are **S24LE and 41000 Hz** (checked with `inspect.signature`), so we pass 16-bit and 16 kHz, which is what Azure STT expects ([speech note](2026-10-02-how-speech-services-work.md)). `S16LE` = signed 16-bit little-endian.
- **Peak level check** in `record()`: read the frames into `array("h", frames)` (`"h"` = signed 16-bit), take `max(abs(s))` and divide by 32768 (full scale). dBFS = 20 x log10(peak): 1% is -40 dBFS, 100% is 0. Under 2% prints a warning.
- Silent recording? The usual cause is **Windows Settings > Privacy & security > Microphone**, with "Let desktop apps access your microphone" off. WSLg's source then delivers silence, with no error. Our 2 s mic check gave peak 1% with nobody speaking: inconclusive (silence and a blocked mic look the same).
- Forward: step 2.5 (push-to-talk) will use the same library but read chunks until Enter is pressed, instead of a fixed `seconds`. `pasimple.PaSimple` (the class) has `read(num_bytes)` for that (seen in its source; not tried yet).

## 3. How the pieces fit
```
Python script -> pasimple (ctypes) -> libpulse-simple.so -> PulseServer (unix socket)
   -> WSLg RDP source/sink -> Windows mic / speakers
Azure SDK default -> libasound (ALSA) -> no card in WSL   (needs the pulse plugin bridge)
```

## 4. Related tools
- `sounddevice` (PortAudio): the usual cross-platform choice on a normal Linux/macOS/Windows machine; the better pick if you later move off WSL.
- `ffmpeg` / `sox`: convert formats and record from devices.
- `pulseaudio-utils` (`pactl list sources short`, `parecord`, `paplay`): CLI tools to inspect the same server.

## 5. Hands-on exercises
1. `echo $PULSE_SERVER; ls /mnt/wslg`. Check: `unix:/mnt/wslg/PulseServer` and the socket/sink/source files.
2. `ldconfig -p | grep -E "libasound|libpulse|portaudio"`. Check: asound and pulse present, portaudio absent.
3. `python speech_smoke.py record t --seconds 3` once silent, once speaking. Check: peak around 1% vs a clearly higher number. Then `python speech_smoke.py play audio/t.wav`.
4. `python -c "import pasimple,inspect;print(inspect.signature(pasimple.record_wav))"`, then open `.venv/lib/python3.14/site-packages/pasimple/pa_simple.py` and find the `CDLL` line. Check: you can say what each does.
5. In a REPL: `import ctypes; libc=ctypes.CDLL("libc.so.6"); print(libc.abs(-5))`. Check: 5.
6. Turn off Windows' desktop-app microphone access, record again. Check: warning "almost silent"; turn it back on.

## 6. Self-check
1. What is the difference between ALSA and PulseAudio?
2. Why does the Azure SDK's default mic fail in WSL while pasimple works?
3. What does `ctypes.CDLL("libpulse-simple.so.0")` do?
4. Why pass `sample_rate=16000` and `PA_SAMPLE_S16LE` to `record_wav`?
5. How is "peak 1%" computed, and what does it suggest?

<details><summary>Answers</summary>

1. ALSA: kernel drivers plus a user-space library, close to hardware. PulseAudio: a server process above it that mixes apps and can be reached over a socket.
2. The SDK uses ALSA, and WSL has no ALSA card; WSLg only exposes a PulseAudio server, which pasimple talks to.
3. Loads the shared library into the process so its C functions can be called from Python.
4. Its defaults are 41000 Hz and 24-bit; Azure STT expects 16 kHz 16-bit mono.
5. Largest absolute sample / 32768. About -40 dBFS: nearly silent, so either nobody spoke or the mic is blocked.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-6 | 45 min |
| B. Another AI tutor | Layers and WSLg concept | 30 min |
| C. Primary docs | WSLg audio, ALSA, ctypes | 1 hr |
| D. Video | Linux audio stack overview | unverified |

- **A. Prompt:** > Walk me through learning/notes/2026-10-03-audio-on-linux-and-wsl.md. Do exercises 1-6 one at a time, then quiz me on the self-check.
- **B. Prompt** (ChatGPT/Gemini, or NotebookLM with the C links): > Using only these sources, explain ALSA vs PulseAudio, how WSLg gives Linux apps microphone and speaker access, and what Python ctypes does. Quiz me with 5 questions. Sources: https://github.com/microsoft/wslg, https://www.alsa-project.org/wiki/Main_Page, https://docs.python.org/3/library/ctypes.html, https://github.com/henrikschnor/pasimple
- **C. Docs (opened 2026-10-03):**
  - [WSLg README](https://github.com/microsoft/wslg): audio section (PulseAudio server, RDP sink/source, `PULSE_SERVER`).
  - [ALSA project](https://www.alsa-project.org/wiki/Main_Page): intro to drivers + alsa-lib.
  - [pasimple on GitHub](https://github.com/henrikschnor/pasimple): quick `record_wav`/`play_wav` examples and the `PaSimple` class (PyPI page wouldn't load for me).
  - [Python ctypes](https://docs.python.org/3/library/ctypes.html): "Loading shared libraries", "Specifying prototypes".
  - Not opened (blocked): ArchWiki "Advanced Linux Sound Architecture" and "PulseAudio" pages; usually good, try them in a browser.
- **D. Video:** a search surfaced a video titled "Linux Audio Explained (ALSA vs PulseAudio vs JACK vs Pipewire Explained)" (covers hardware, ALSA/OSS, PulseAudio/JACK, PipeWire) but only on a mirror site, and I couldn't confirm the creator or an official link. Search that title on YouTube. A text alternative from search results: ["The Linux audio stack demystified"](https://unixism.net/2024/07/the-linux-audio-stack-demystified/) (not read).
