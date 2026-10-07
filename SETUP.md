# Setup: accounts, keys, and Python environments

**Written:** October 1, 2026. Prices and free tiers change; recheck anything marked as a price before relying on it.

| # | Item | Type | Status |
|---|---|---|---|
| 1 | LLM API key (paid OpenAI or Anthropic) | Done 2026-10-02 (OpenAI, monthly limit set) | ☑ |
| 2 | Azure Speech key | Done 2026-10-02 (F0, italynorth) | ☑ |
| 3 | pyenv and virtual environments | Learning | ☐ Choose how to learn it |
| 4 | ElevenLabs (optional, for your own voice) | To do (you), **not yet**: only at step 2.6 | ☐ |

> **Never paste an API key into a chat, including into Claude.** Keys go only in `.env`, which `.gitignore` keeps out of git. If a key leaks, delete it in the provider's dashboard and create a new one.

---

## 1. LLM API key (to do)

### Why a subscription doesn't work here

ChatGPT Plus, Claude Pro, and Gemini app subscriptions cover the chat apps only. Code calls the **API**, which has a separate account and separate billing. ([OpenAI help](https://help.openai.com/en/articles/8264644-chatgpt-plus), [Claude credits explained](https://www.ssdnodes.com/learn/claude-usage-credits-explained))

### Decision (2026-10-02): paid API, $5–10 budget

Roman chose a paid OpenAI or Anthropic API over the Gemini free tier. Both need a **$5 minimum prepaid** purchase with a card, and both can cap spending.

| | OpenAI | Anthropic (Claude) |
|---|---|---|
| Cheap model for building | `gpt-5.4-mini`: $0.75 in / $4.50 out per 1M tokens ([pricing summary](https://morphllm.com/openai-api-pricing); check the official page when you sign up) | `claude-haiku-4-5`: $1 in / $5 out per 1M tokens |
| Stronger model to compare in evals | larger GPT models | `claude-sonnet-5-5`: $2 in / $10 out per 1M tokens |
| Also sells speech (STT/TTS)? | **Yes.** A possible fallback if Azure's Georgian is poor (Georgian quality untested) | No |
| LangChain/LangGraph support | `langchain-openai` | `langchain-anthropic` |

**Rough cost for this project:** about 500 model calls at ~2,000 input + 300 output tokens each comes to roughly **$1.50–2 on a cheap model** and about $3.50 on Sonnet 5.5. $5 is enough, and $10 leaves room to compare two models during evaluation.

**Recommendation: OpenAI.** The prices are similar, but OpenAI also sells speech-to-text and text-to-speech. If Azure's Georgian speech disappoints in step 1.5, you'd have a backup without another account. (I'm Claude, so weigh that; Anthropic would work equally well for the text side.) If you have money left on day 3, adding $5 on the other provider and comparing both on your eval set makes a strong story.

### Steps

**OpenAI**
1. Go to <https://platform.openai.com> and sign in with a **personal** account (not a work one).
2. Settings → Billing: add a card and buy $5. Set a **monthly budget limit** (e.g. $10).
3. API keys → create a key, and copy it once.

**Anthropic**
1. Go to <https://platform.claude.com> and sign in with a **personal** account.
2. Settings → Billing: buy $5, and set a spend limit if offered.
3. API keys → create a key.

**Then, for either one:**
4. In the project folder, create `.env` with **one** line, `OPENAI_API_KEY=...` or `ANTHROPIC_API_KEY=...`.
5. Run `git status` and confirm `.env` is **not** listed.
---

## 2. Azure Speech key (to do)

### Why Azure

Azure documents Georgian (`ka-GE`) support for both speech-to-text and text-to-speech. It has two Georgian neural voices, **`ka-GE-EkaNeural`** (female) and **`ka-GE-GiorgiNeural`** (male). ([language support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts))

The **free (F0) tier** includes **5 audio hours of STT per month** and **0.5 million characters of neural TTS per month**, which is far more than this project needs. F0 limits that affect the build (checked 2026-10-02): real-time STT allows **1 concurrent request**, so eval runs must send audio one at a time; real-time TTS allows **20 requests per 60 s**; and **fast/batch transcription show "Not applicable" for F0**, so use real-time recognition. Details: [learning/notes/2026-10-02-azure-basics.md](learning/notes/2026-10-02-azure-basics.md). ([pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/))

### Steps

1. **Sign up for Azure for Students:** <https://azure.microsoft.com/free/students>. Use your **university email** (Free University). You must be 18+ and a student; it gives **$100 of credit with no card** for 12 months. If your university email doesn't verify, a regular free Azure account also works but asks for a card.
2. Go to <https://portal.azure.com>, choose **Create a resource**, and search for **Speech**. Pick the card named **"Speech" by Microsoft**, marked **Azure Service** with a **Create** button. That one resource covers **both STT and TTS** with one key. Don't pick the third-party marketplace cards ("Text-to-Speech API", "Speech-to-Text API", BitFractal, etc.): their **Subscribe** button starts a separate paid contract with another company.
3. Fill in the form:
   - **Resource group:** create a new one called `voice-assistant`. Deleting the group later removes everything inside it.
   - **Region:** **Italy North** (`italynorth`). Roman's Azure for Students subscription only allows `denmarkeast`, `switzerlandnorth`, `polandcentral`, `austriaeast`, and `italynorth` (policy error `RequestDisallowedByAzure` on anything else). Of those, only `italynorth` and `switzerlandnorth` support Speech ([regions](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions), checked 2026-10-02). Italy North also has fast transcription, which Georgian supports. To see your own allowed list: Portal → Policy → Assignments → "Allowed resource deployment regions" → Parameters.
   - **Name:** any name, for example `roma-voice-assistant`.
   - **Pricing tier:** **Free F0**. You can have only one F0 Speech resource per subscription.
4. After the resource is created, open it and go to **Keys and Endpoint**. Add **KEY 1** and the **Location/Region** to `.env`:
   ```
   AZURE_SPEECH_KEY=paste-key-1-here
   # must match your resource's region code (Keys and Endpoint)
   AZURE_SPEECH_REGION=italynorth
   ```
5. **No-code quality test (do this early):** open **Speech Studio** (<https://aka.ms/speechstudio/>). If asked, select your Azure for Students subscription and the `italynorth` resource. For **TTS**, use **Explore the Voice Gallery**: filter to Georgian (Georgia) and have Eka and Giorgi read a sentence the assistant might say, e.g. *„თქვენი ბარათის ლიმიტის შესაცვლელად გადადით აპლიკაციის პარამეტრებში.“* For **STT**, use **Try out Real-time speech to text**: set the language to Georgian (Georgia), not auto-detect, and record a question. Skip Personal Voice; its API is gated. Note how it did:
   - TTS (Eka / Giorgi), tested 2026-10-02: **Eka 3/5, Giorgi 3.5–4/5.** No mispronunciations; both sound understandable but not natural. → Giorgi is the default voice for now, and ElevenLabs (step 2.6) is worth trying.
   - STT accuracy on your voice, tested 2026-10-02: **mostly correct** for ordinary words; rarer or less common words get misrecognized. Not yet tested: Georgian sentences with English tech words mixed in (see the code-switching note below).

### Code-switching: Georgian with English words mixed in (checked 2026-10-02)

Georgian speakers, especially developers, mix in English words ("API-ს key როგორ შევცვალო?"). This is called **code-switching**, and Azure's support for it is weak:

- **STT:** Azure's language identification **can't switch languages mid-sentence**. English words in a Georgian sentence are decoded as Georgian ([language identification docs](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-identification)). **Phrase lists** (biasing toward specific words) aren't shown as enabled for `ka-GE`; confirm with the Phrase list toggle in Speech Studio ([language support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt)).
- **TTS:** nothing is documented about Eka/Giorgi reading English words, and Azure's multilingual voices don't list Georgian. Untested. Possible workarounds: SSML `<sub alias="…">` with a Georgian-script spelling, or rewriting English terms into Georgian script before TTS.
- **Alternatives to test:**
  - ElevenLabs **Scribe v2** puts Georgian in its "High Accuracy" tier (5–10% WER) and supports **keyterm prompting** (50 terms in realtime, 1,000 in batch) ([docs](https://elevenlabs.io/docs/capabilities/speech-to-text)). It's the same account as step 2.6.
  - OpenAI `gpt-transcribe` takes `languages`, `keywords`, and `prompt` hints ([docs](https://developers.openai.com/api/docs/guides/speech-to-text)), but Georgian isn't explicitly confirmed there.
  - None of the three documents mid-sentence code-switching, so **measure it** (BUILD_PLAN 1.5, 3.1, 3.4).

### Step 1.5 results (2026-10-03, `speech_smoke.py`)

**Synthetic round trip** (Giorgi reads the sentence with TTS, then Azure STT transcribes the file). This is a proxy that needs no microphone. It tests both directions at once, so it can't say which side broke a word:

| Sentence | Transcript |
|---|---|
| რა ღირს როუმინგი ევროპაში? | რა ღირს როუმინგი ევროპაში? (exact) |
| API-ს key როგორ შევცვალო? | **დეფის კი** როგორ შევცვალო? |
| როუმინგი როგორ ჩავრთო iPhone-ზე? | როუმინგი როგორ ჩავრთო **ეს ფონზე**? |
| eSIM-ის QR კოდი email-ზე მომივა? | **ისე მის კარგ** კოდი **მეილზე** მომივა. |
| eSIM-ის გასააქტიურებლად გახსენით ჯიხვის აპლიკაცია და დაასკანერეთ QR კოდი. | **იზი მის** გასააქტიურებლად გახსენით **ტალახის** აპლიკაცია და დაასკანირეთ კოდი. |

- Pure Georgian survives exactly. Every English word breaks, and `QR` disappeared twice.
- `API-ს` → `დეფის` suggests TTS **reads the hyphen aloud as "დეფისი"** (the Georgian word for hyphen). Confirm by ear: `python speech_smoke.py play audio/synth_2.wav`. If it's true, the speech-text step in 2.5 must at least drop the hyphen in "API-ს"-style suffixes.
- Azure STT capitalizes the first letter of a sentence with a **Mtavruli** capital (`Გ`, U+1C92) instead of `გ`. `speech_smoke.py` maps them back (`to_mkhedruli`), because a capital would break keyword search and eval string comparisons.
- `recognize_once()` stops after the first sentence. The script uses continuous recognition instead.
- Speed: TTS 0.8–1.8 s per sentence, STT 1.0–2.0 s for 5–6 s of audio (F0, italynorth).

**TTS by ear** (Roman, Giorgi reading `reply.wav`): Georgian is fine, but English words are "rough". Giorgi reads them **as if they were Georgian letters, run together**: "eSIM" ≈ "ისიმ", "QR" ≈ "ქრ" instead of "ქიუარ". So Azure's Georgian voices have no English pronunciation at all. The "დეფისი for the hyphen" guess wasn't confirmed by ear.

**STT of Roman's own voice** (16 kHz mono, peak level 7–16%):

| File | Said | Transcript |
|---|---|---|
| q1 | რა ღირს როუმინგი ევროპაში? | რა ღირს **რომ მინი** ევროპაში. |
| c1 | API-ს key როგორ შევცვალო? | **ვი პი აის ქე რო გორ.** შევცვალო. |
| c2 | (second take of c1) | **იფ იანის ქე** როგორ **შორს ხარ**? |
| c3 | როუმინგი როგორ ჩავრთო iPhone-ზე? | როუმინგი როგორ **ჩართა იფანსი**? |
| c4 | eSIM-ის QR კოდი email-ზე მომივა? | **ისინი სქი ვარკვევდი** მეილზე მომივა. |

**What this means for the build:**
- **STT:** every English word failed, even when a native speaker said it. Even the loanword "როუმინგი" failed once ("რომ მინი"), and that would make `lookup_faq` miss the roaming entries. Trying ElevenLabs Scribe v2 with keyterms (step 2.6a) is now clearly worth it, and Phase 3 needs code-switched eval cases.
- **TTS:** the speech-text step in 2.5 is required. It needs to spell English terms in Georgian script as they're pronounced (QR → ქიუარ, eSIM → ი-სიმ, API → ეი-პი-აი), either directly or with SSML `<sub>`.
- Synthetic round trips were kinder than real speech (q1 was exact when Giorgi said it). Test with real recordings, not only TTS output.

---

## 3. pyenv and virtual environments (learning material)

### Decision: stay on Python 3.14

On 2026-10-01 I checked PyPI. Every package we plan to use ships a pure-Python (`py3-none`) wheel and requires at least Python 3.10, so 3.14 works:

| Package | Version | 3.14 listed in classifiers? |
|---|---|---|
| langgraph | 1.2.12 | No (lists up to 3.13), but it's pure Python, so it should work. We'll confirm on install |
| langchain-core | 1.6.6 | Yes |
| mcp | 2.2.0 | Yes |
| openai / anthropic / google-genai | 3.22.1 / 1.11.0 / 2.26.0 | Yes |
| azure-cognitiveservices-speech | 1.52.0 | Not listed; it ships `py3-none` platform wheels |
| sounddevice | 0.5.6 | Not listed; pure Python |

WSLg's audio bridge is running (`PULSE_SERVER=unix:/mnt/wslg/PulseServer`), so the microphone and speakers should be reachable from WSL. We'll test that during the voice step.

### What you're learning, and why it matters

**Problem 1: several Pythons on one machine.** Your machine has the system Python, pyenv's 2.7.18, and pyenv's 3.14.0. When you type `python`, which one runs?

- Your shell searches the directories in `$PATH` in order and runs the first `python` it finds.
- pyenv puts a **shim** directory (`~/.pyenv/shims`) at the front of `PATH`. A shim is a tiny script that decides which real Python to run.
- The shim checks, in order: the `PYENV_VERSION` variable (set by `pyenv shell`), a `.python-version` file in the current folder or a parent (set by `pyenv local`), and then `~/.pyenv/version` (set by `pyenv global`). Your global version is currently 3.14.0.

**Problem 2: each project needs its own packages.** If every project installs into the same Python, two projects that need different versions of a library will break each other. Installing into the system Python can also break OS tools that depend on it.

- A **virtual environment** (`python -m venv .venv`) is a folder containing a link to a base Python, its own `site-packages` directory for installed packages, and a `pyvenv.cfg` file recording which Python it was made from.
- **Activating** it (`source .venv/bin/activate`) mostly just puts `.venv/bin` at the front of `PATH`. Nothing else about it is special.
- `pip install X` installs into whichever Python is running pip. That's why `python -m pip` is safer than plain `pip`.
- `requirements.txt` (or `pyproject.toml`) records what the project needs, so someone else can recreate the environment. `pip freeze` lists exactly what's installed.

**How the two fit together:** pyenv picks the Python version, and the venv isolates the project's packages on top of that version.

**Related tool:** `uv` is a newer, much faster tool that does both jobs. We're using plain pyenv + venv + pip first so you understand what tools like `uv` automate.

### Hands-on exercises (each has a check you can observe)

1. `which python` and `pyenv which python`. Why do they print different paths?
2. `cat ~/.pyenv/shims/python`. Read the shim and confirm it's a small script, not Python itself.
3. `pyenv version`. Which mechanism chose this version (shell, local, or global)?
4. In the project folder, run `python -m venv .venv`, then `ls .venv` and `cat .venv/pyvenv.cfg`.
5. Run `echo $PATH | tr ':' '\n' | head -3` and `which python`, activate the venv, and run both again. What changed?
6. In the venv, run `python -m pip install requests`, then `deactivate` and `python -c "import requests"`. Explain the result.
7. *(Optional, about 15 min, needs build packages; see the pyenv wiki's "Suggested build environment")* Run `pyenv install 3.12` and `pyenv local 3.12`. A `.python-version` file appears. Check `python --version` in this folder and in its parent folder. Then delete the file so the project goes back to 3.14.

### Self-check: can you answer these without looking?

- What is a shim, and why does pyenv need one?
- What does activating a venv actually change?
- Why is `python -m pip` safer than `pip`?
- Why is `.venv/` in `.gitignore` while `requirements.txt` is committed?
- If you `pip install` something and then `import` fails, what are the first two commands you run? (Answer: `which python` and `python -m pip show <package>`.)

### Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| **A. Claude walks you through the exercises in this repo** | Learning by doing, with questions answered as they come up; fits the project | About 45 min |
| B. Another AI tutor | A different explanation, with the exercises above as its script | About 45 min |
| C. Read primary docs | The most accurate source | About 1 hr |
| D. Video | Seeing someone else do it before trying | 15–30 min, then do the exercises anyway |

**A. Prompt to paste into a main session in this repo:**
> Walk me through SETUP.md section 3 (pyenv and virtual environments). Do the 7 hands-on exercises one at a time: run each command, show me the output, and ask me to explain it before moving on. Then quiz me on the self-check questions.

**B. Tool:** NotebookLM (load the C links as sources) or any chat AI. Prompt to paste:
> I'm a CS student. Using only these sources, teach me how pyenv shims pick a Python version and how `python -m venv` isolates packages, then give me a 5-question quiz with answers. Sources: https://docs.python.org/3/tutorial/venv.html, https://docs.python.org/3/library/venv.html, https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/, https://github.com/pyenv/pyenv#how-it-works, https://realpython.com/python-virtual-environments-a-primer/, https://realpython.com/intro-to-pyenv/

**C. Reading list (what to read in each):**
- Python tutorial on venvs: <https://docs.python.org/3/tutorial/venv.html>. Start here; creating, activating and freezing an environment.
- How venvs work (reference): <https://docs.python.org/3/library/venv.html>. What `pyvenv.cfg` and the activate scripts do.
- Packaging guide, pip + venv: <https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/>. The recommended workflow and `python -m pip`.
- pyenv README, "How It Works": <https://github.com/pyenv/pyenv#how-it-works>. Shims and how the version is chosen.
- Real Python, "Python Virtual Environments: A Primer": <https://realpython.com/python-virtual-environments-a-primer/>. The "why" with examples.
- Real Python, "Managing Multiple Python Versions With pyenv": <https://realpython.com/intro-to-pyenv/>. Install, global/local/shell versions.

**D. Video** (confirmed by search on 2026-10-02):
- "Python Tutorial: VENV (Mac & Linux) - How to Use Virtual Environments with the Built-In venv Module", Corey Schafer: <https://www.youtube.com/watch?v=Kg1Yvry_Ydk> (matches WSL).
- I couldn't verify a specific pyenv video; search YouTube for "pyenv tutorial".

Whatever you choose, finish with the exercises and the self-check.

---

## 4. ElevenLabs voice (optional, to do at step 2.6)

**Don't set this up yet.** Wait until the voice loop (BUILD_PLAN step 2.5) works with Azure. Until then, Azure's ready-made voices (Eka/Giorgi) are the assistant's voice.

### Three stages, one change at a time

| Stage | Voice | What it tells you |
|---|---|---|
| 1 (steps 1.5, 2.5) | Azure `ka-GE-EkaNeural` / `ka-GE-GiorgiNeural` | The baseline: does the pipeline work at all? |
| 2 (step 2.6a) | An ElevenLabs **ready-made** voice | Is ElevenLabs' Georgian better than Azure's? |
| 3 (step 2.6b) | An ElevenLabs **clone of your voice** | Does the clone keep that quality and sound like you? |

Changing one thing per stage means that when something sounds worse, you know which change caused it.

### Facts (checked 2026-10-02; models and prices re-checked 2026-10-04)

- Georgian is listed for `eleven_v4`, the low-latency `eleven_v4_turbo` and `eleven_v3` (re-checked 2026-10-04). It is **not** listed for `eleven_multilingual_v2` (the API's default model, so the code always sends `model_id`) or `eleven_flash_v2_5`. The code uses `eleven_v4_turbo` by default (~100 ms model latency, half v4's price); set `ELEVENLABS_MODEL=eleven_v4` to compare. ([models docs](https://elevenlabs.io/docs/overview/models))
- STT: `scribe_v2` lists Georgian (`kat`) in its 5–10% WER tier. Keyterms cost extra. API prices on 2026-10-04: v4 Turbo $0.011 and v4 $0.022 per 1K characters (72% off until October 12; regular $0.04 / $0.08), Scribe v2 $0.22 per hour ([API pricing](https://elevenlabs.io/pricing/api)). The page doesn't say how much free credit the Free plan includes; your account's usage page does.
- Instant Voice Cloning needs the **Starter** plan or higher, about $5–6/month by recent third-party summaries ([summary](https://magichour.ai/blog/elevenlabs-pricing)). Check the price on <https://elevenlabs.io/pricing> when you sign up. Professional cloning ($22+, 30+ minutes of studio audio) is overkill here.
- ElevenLabs recommends recording the clone **in the language you'll use it in**, so record in Georgian.
- The free plan may be enough for stage 2 (a ready-made voice). Check whether it includes API access to the Georgian-capable models before paying.

### Steps

**Stage 2: ready-made voice**
1. Sign up at <https://elevenlabs.io> with a personal account.
2. In the voice library, pick a voice and try a Georgian sentence with `eleven_v4` or `eleven_v4_turbo`. Use the same test sentence as SETUP.md §2. **Pick a male voice**: Azure's Giorgi is male, so a female voice would give the provider away in the blind rating.
3. Profile → API keys: create a key, then add `ELEVENLABS_API_KEY=...` and `ELEVENLABS_VOICE_ID=<the ready-made voice's ID>` to `.env`. Confirmed 2026-10-06: the Free plan can't use **library** voices over the API (`HTTP 402 payment_required: Free users cannot use library voices via the API`). Use one of the ~21 **premade** voices (Brian, Eric, Daniel, Chris, ...). They speak Georgian through `eleven_v4*` even though none is a Georgian native voice; the voice library has no Georgian-native voices at all.
4. Optional lines in `.env` (step 2.6a code): `TTS_PROVIDER=elevenlabs` and/or `STT_PROVIDER=elevenlabs` make the voice loop use ElevenLabs by default (Azure is the fallback either way), and `ELEVENLABS_MODEL=eleven_v4` switches the TTS model.

**Stage 3: your voice**
5. Upgrade to Starter if the free plan doesn't include cloning.
6. **Record about 2 minutes** of natural Georgian. Read [data/clone_script.md](data/clone_script.md) (written for this; not the rating sentences). Record on **Windows or a phone** (Sound Recorder, Audacity at 44.1/48 kHz, or a voice memo at best quality), not through WSL: the repo's `Recorder` captures 16 kHz through the WSLg bridge, enough for STT but thin for a clone.
   - Use a quiet room with no echo, and the same mic and distance throughout.
   - Speak in the tone the assistant should have: friendly and calm, not reading-aloud stiff.
   - Avoid background music, other voices, and long silences.
   - Save it as WAV or high-quality MP3. Keep the file **out of the repo**, since `audio/` is gitignored.
7. Voices (left menu) → the **+** button → **Instant Voice Clone**: upload the file, name it, and confirm you have the right and consent to clone this voice (it's yours). ElevenLabs asks for ~1–2 min without reverb or background noise ([docs](https://elevenlabs.io/docs/product-guides/voices/voice-cloning/instant-voice-cloning)).
8. Copy the new voice ID into `.env` as **`ELEVENLABS_CLONE_VOICE_ID=...`**, and keep `ELEVENLABS_VOICE_ID` as the premade voice: the three-voice comparison needs both. `ELEVENLABS_VOICE=clone` in `.env` (or `voice.py --el-voice clone`) makes the voice loop use the clone.

**Rules**
- Never commit or share the API key or the voice ID. A clone of your voice is a security risk; banks deal with voice-fraud deepfakes.
- In any demo, say it's a consented clone of your own voice.
- When the project is done, cancel the subscription and delete the clone if you don't want it kept.

