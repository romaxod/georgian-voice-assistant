# Setup: accounts, keys, and Python environments

**Written:** October 1, 2026. Prices and free tiers change; recheck anything marked as a price before relying on it.

| # | Item | Type | Status |
|---|---|---|---|
| 1 | LLM API key (paid OpenAI or Anthropic) | To do (you) | ☐ |
| 2 | Azure Speech key | To do (you) | ☐ |
| 3 | pyenv and virtual environments | Learning | ☐ Choose how to learn it |

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

The **free (F0) tier** includes **5 audio hours of STT per month** and **0.5 million characters of neural TTS per month**, which is far more than this project needs. ([pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/))

### Steps

1. **Sign up for Azure for Students:** <https://azure.microsoft.com/free/students>. Use your **university email** (Free University). You must be 18+ and a student; it gives **$100 of credit with no card** for 12 months. If your university email doesn't verify, a regular free Azure account also works but asks for a card.
2. Go to <https://portal.azure.com>, choose **Create a resource**, and search for **Speech** (it may be listed under Azure AI services or Foundry).
3. Fill in the form:
   - **Resource group:** create a new one called `voice-assistant`. Deleting the group later removes everything inside it.
   - **Region:** choose a European region such as **West Europe**, and write it down.
   - **Name:** any name, for example `roma-voice-assistant`.
   - **Pricing tier:** **Free F0**. You can have only one F0 Speech resource per subscription.
4. After the resource is created, open it and go to **Keys and Endpoint**. Add **KEY 1** and the **Location/Region** to `.env`:
   ```
   AZURE_SPEECH_KEY=paste-key-1-here
   AZURE_SPEECH_REGION=westeurope
   ```
5. **No-code quality test (do this early):** in the Speech playground (Azure AI Foundry, formerly Speech Studio), have both Georgian voices read a sentence the assistant might actually say. For example: *„თქვენი ბარათის ლიმიტის შესაცვლელად გადადით აპლიკაციის პარამეტრებში.“* Then try live transcription by saying a question in Georgian. Note how it did:
   - TTS (Eka / Giorgi): ____________
   - STT accuracy on your voice: ____________

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
