# Voice cloning: instant vs professional, consent, security risks

**Written:** 2026-10-07. ElevenLabs plans, docs and EU dates change; I checked the pages listed in C on this date.

## 1. What you're learning, and why it matters

**Problem.** The assistant should speak in Roman's own voice (step 2.6b). That is easy to do and also exactly the technique used in "CEO" phone scams. Anyone building a voice assistant has to understand both sides: how a clone is made, and why a voice is no longer proof of identity.

- A **voice clone** is a TTS voice built to sound like one specific person.
- **Instant voice cloning (IVC), "zero-shot":** you give the service about 1-2 minutes of audio. A **speaker encoder** turns it into a fixed-size vector (a **speaker embedding**: pitch range, timbre, speaking style). The big TTS model is *conditioned* on that vector when it generates speech. No training happens, so the clone exists in seconds. ElevenLabs' IVC docs recommend about 1-2 minutes of clear audio.
- **Professional voice cloning (PVC):** the model is **fine-tuned** (its weights are updated) on at least 30 minutes of studio-quality audio (2-3 hours recommended). It takes hours (3-6 typical), and you must pass a **verification step**: you record spoken lines with the same setup, so only the real speaker can create the voice. Per the PVC docs it isn't available on Free or Starter.
- Trade-offs:

| | Instant | Professional |
|---|---|---|
| Audio needed | ~1-2 min | 30 min minimum |
| Time | seconds | hours |
| Likeness | good timbre, weaker on rhythm and unusual styles | closest to the speaker |
| Other languages | tends to carry the sample's accent | better if trained in the target language |
| Plan | Starter and up | Creator and up |

- **What makes a good sample:** the encoder cannot separate the voice from the room. Noise, reverb and compression get cloned too (a clone from a noisy sample sounds noisy). So: quiet room, one speaker, consistent distance and level (ElevenLabs suggests about -23 to -18 dB RMS, true peak -3 dB), no music, and the **same language and tone** you want out. A clone of calm English reading will not sound like a helpful Georgian agent. That is why `data/clone_script.md` is written like assistant replies.
- **Consent and law (high level).** Platforms make you confirm you have the right to clone the voice. The EU AI Act, Article 50(4): deployers of an AI system that generates audio constituting a **deep fake** must disclose that it is artificially generated. Art. 50(2) requires providers to mark outputs in a machine-readable way. Article 50 applies from 2 August 2026; a Digital Omnibus deal moved only the 50(2) marking duty for systems already on the market to 2 December 2026 (per a Cloud Security Alliance note; I did not read the legal text of the amendment). Art. 50(1) also says people must be told when they talk to an AI. This is not legal advice.
- **Security risks:**
  - **Voice fraud.** A few seconds to a minute of public audio is enough for a convincing clone. Typical attacks: fake "CEO" calls to finance staff, "relative in trouble" calls, and calls to a bank's phone line.
  - **Voice authentication is weak.** Voiceprint login ("my voice is my password") compares the caller to an enrolled embedding, which is the same kind of vector a cloner imitates. In July 2025 OpenAI's Sam Altman told a Federal Reserve conference that "AI has fully defeated" voiceprint authentication.
  - **Defenses.** **Liveness / anti-spoofing** checks try to tell live speech from synthetic or replayed audio. The **ASVspoof** challenge series (2015 to 2024) provides shared datasets and metrics for such countermeasures. Real systems add other factors: a call-back to a known number, a one-time code, an app confirmation. Voice alone should never authorise money movement.
  - **Provider safeguards (ElevenLabs safety page):** blocks cloning of celebrity and other high-risk voices; verification for PVC; AI classifiers, human reviewers and investigations; bans for repeat violators; C2PA support; a public **AI Speech Classifier** that estimates whether a clip came from ElevenLabs. Detection classifiers are an arms race and mostly cover one vendor's output. **Watermarking** (inaudible signal in the audio, or C2PA metadata) helps only if the provider adds it and it survives re-recording.
  - **The voice ID is a secret.** Anyone with your API key and `voice_id` can synthesise speech in your voice on your quota. Never commit or share it.

## 2. In this repo

- Plan: ElevenLabs Starter (Free has no cloning). The recording was ~2 min of Georgian from `data/clone_script.md`, recorded on Windows because `Recorder` captures only 16 kHz mono through WSLg (fine for STT, thin for a clone). Script deliberately differs from the 10 blind-rating sentences, so the rating is not a replay of the sample.
- Creation, in the web UI: Voices, "+", Instant Voice Clone, upload, name, tick "you have the right and consent to clone the voice", Save. The API equivalent is `POST https://api.elevenlabs.io/v1/voices/add` (multipart `name` + `files`, optional `remove_background_noise`, `description`, `labels`); it returns `voice_id` and `requires_verification`.
- `.env`: `ELEVENLABS_CLONE_VOICE_ID` (the clone), `ELEVENLABS_VOICE_ID` (premade Brian), `ELEVENLABS_VOICE=ready|clone` picks one.
- Project rules (SETUP.md section 4): never commit the ID or key; say in any demo that it is a consented clone of his own voice; cancel and delete the clone afterwards if not wanted.
- Georgian was recorded in Georgian because ElevenLabs recommends recording in the language the clone will speak.

## 3. How the pieces fit together

`sample audio -> speaker encoder -> embedding -> TTS model (text + embedding) -> audio in that voice`. The same pipeline is what an attacker uses; the only differences are consent and what the output is used for.

## 4. Related tools

- Open-source zero-shot TTS (Coqui XTTS-v2, YourTTS) works the same way and runs locally from 3-10 s of audio. Not used: Georgian quality unknown to me, and the project compares hosted providers.
- Azure also has custom neural voice, gated behind an application and consent recording (not checked today). Our Azure voice is a stock one.
- Deployment angle for a real service: tell customers when a voice is synthetic; never clone real staff or customers without written consent; a synthetic voice must not sound like a named real employee; involve the fraud team; treat caller voice as a weak signal, not a credential; log which voice and model produced each call.

## 5. Hands-on exercises

1. Synthesise one Georgian and one English sentence with `ELEVENLABS_VOICE=clone` (see how `voice.py` and `compare_speech.py` select it). Listen for accent carry-over in English. Check: you can describe what changed in vowels or rhythm.
2. Same sentence with `ready` and `clone`. Check: you can name two differences besides timbre (pace, pauses).
3. (Optional, uses a clone slot) Create a second IVC from a deliberately noisy recording, with and without `remove_background_noise`. Check: the noisy one reproduces the noise.
4. Read https://elevenlabs.io/safety and list each safeguard under "prevent / detect / enforce". Check: five items, each with who enforces it.
5. Upload a clone sample to https://elevenlabs.io/ai-speech-classifier and note the result. Check: write one sentence on why this can't prove a clip is real.
6. Write a two-line disclosure the assistant says at the start of a call. Check: it says it is an automated assistant and that the voice is synthetic.

## 6. Self-check

1. What is the difference between IVC and PVC in what the model does with the sample?
2. Why does a clone from a noisy sample sound noisy?
3. Why is "voice as password" weak against clones?
4. Which two EU AI Act Article 50 duties matter for a TTS voice assistant?
5. Why is `voice_id` treated like a key?
6. Name three service-side controls besides voice matching.

<details><summary>Answers</summary>

1. IVC: no training; the model is conditioned on an embedding computed from the sample. PVC: weights fine-tuned on 30+ min, plus identity verification.
2. The encoder and model learn the whole recording's acoustics, not just the speaker.
3. Voiceprints compare against an embedding; clones imitate exactly that.
4. 50(1) tell people they are talking to AI; 50(4) disclose deep fakes (audio imitating a real person); 50(2) marking is the provider's job.
5. With the key and ID anyone can generate speech in that voice, billed to you.
6. Call-back to a known number, one-time code, app confirmation, liveness/anti-spoof checks, transaction limits, fraud monitoring.
</details>

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Exercises 1-2, 4 with the real clone | 40 min |
| B. Another AI tutor | Security and law overview with grounded sources | 45 min |
| C. Primary docs | Accurate details of cloning and the Act | 1 hr |
| D. Video / talk | Seeing the threat model explained | 30-60 min |

**A. Prompt:**
> Read learning/notes/2026-10-07-voice-cloning-consent-and-security.md. Walk me through exercises 1, 2 and 4 with my clone (never print the voice ID). Then ask me the self-check questions one at a time.

**B. Tool:** NotebookLM with the C links. Prompt:
> Using only these sources, explain how instant voice cloning differs from professional cloning, why voice authentication fails against clones, and what EU AI Act Article 50 requires of a voice assistant operator. End with a 5-question quiz. Sources: https://elevenlabs.io/docs/product-guides/voices/voice-cloning/instant-voice-cloning, https://elevenlabs.io/docs/product-guides/voices/voice-cloning/professional-voice-cloning, https://elevenlabs.io/safety, https://artificialintelligenceact.eu/article/50/, https://www.local10.com/business/2025/07/22/openais-sam-altman-warns-of-ai-voice-fraud-crisis-in-banking

**C. Reading (all opened 2026-10-07 unless noted):**
- [IVC guide](https://elevenlabs.io/docs/product-guides/voices/voice-cloning/instant-voice-cloning): sample quality, levels, consent.
- [PVC guide](https://elevenlabs.io/docs/product-guides/voices/voice-cloning/professional-voice-cloning): data amount, verification, plans.
- [Create IVC API](https://elevenlabs.io/docs/api-reference/voices/ivc/create): the `voices/add` request.
- [ElevenLabs safety](https://elevenlabs.io/safety): provider safeguards.
- [AI Act Article 50](https://artificialintelligenceact.eu/article/50/): read paragraphs 1, 2 and 4.
- [CSA note on the 50(2) delay](https://labs.cloudsecurityalliance.org/research/csa-research-note-eu-ai-act-article50-watermarking-deadline/): seen in search results only, not opened.
- [Altman at the Fed (news report)](https://www.local10.com/business/2025/07/22/openais-sam-altman-warns-of-ai-voice-fraud-crisis-in-banking): seen in search results only, not opened.
- ASVspoof overview paper: [ASVspoof 2019 (arXiv 2102.05889 via alphaXiv)](https://alphaxiv.org/abs/2102.05889): seen in search results only, not opened.

**D. Talk/video:**
- Hany Farid, "Creating, Weaponizing, and Detecting Deep Fakes" (MIT CSAIL Hot Topics): https://www.csail.mit.edu/news/hot-topics-computing-creating-weaponizing-and-detecting-deep-fakes-prof-hany-farid . Title and speaker confirmed in search results; I did not open the page or confirm a recording exists.
- I could not verify a YouTube video or free course on audio-deepfake fraud. Search "audio deepfake detection ASVspoof tutorial" and "voice cloning scam bank" and check the channel before trusting it.
- Related in this repo: ElevenLabs plan facts in [code-switching note](2026-10-02-code-switching-stt-tts.md), blind rating method in [evaluating speech providers](2026-10-04-evaluating-speech-providers.md).
