# Azure basics for this project: accounts, resources, regions, keys, policy, cost

Checked 2026-10-02 against Microsoft Learn and Azure pages (linked below). Portal screens and limits change, so trust the live page over this note.

## 1. What you're learning, and why it matters

**Problem.** Azure looks complicated because one product (Speech) sits inside four layers of organization, a region system, a policy system and two ways to authenticate. Once you know the layers, each thing you did on 2026-10-02 has a reason. A user of Azure needs only: where is my resource, what does it cost, how do I call it, how do I clean it up.

**The hierarchy** ([Resource Manager overview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/overview))
- **Tenant / account**: your identity directory (Microsoft Entra ID). Your university email created one for the student offer. It holds *who you are*, not resources.
- **Subscription**: the billing and access container. Yours is "Azure for Students". Credit and spending limits belong to it.
- **Resource group**: a container for resources that share a lifecycle. Delete the group and everything in it is deleted. Yours: `voice-assistant`.
- **Resource**: one manageable item (VM, storage account, Speech service). Yours: `roma-voice-assistant`, type Speech, tier F0.
- Docs name four *scopes*: management groups, subscriptions, resource groups, resources. Settings such as policies apply at a scope and **are inherited downward**.

**Marketplace: first-party vs third-party.** The portal's Marketplace shows Microsoft's own services (marked *Azure Service*, button **Create**) next to other companies' SaaS products (button **Subscribe**). Subscribing starts a separate paid contract with that company. You picked **"Speech" by Microsoft** (Create), which is the real Azure resource that covers STT and TTS with one key (SETUP.md §2). I found no Microsoft page describing this distinction; it's from your experience in the portal.

**Regions and data residency.** A resource lives in one **region** (a datacenter area, e.g. `italynorth`). Your audio and text are processed by that region's service. Keys are **region-scoped**: Microsoft's REST docs say a 401 means "Make sure your Speech resource key or token is valid and in the correct region", and the regional endpoint is `https://<region>.tts.speech.microsoft.com/...` (the TTS REST page lists Italy North and Switzerland North). That's why `.env` needs both `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`. Not all features exist in all regions (Speech is in fewer regions than Azure overall).

**Azure Policy.** Rules that a subscription owner attaches to a scope, e.g. "only allow these regions". Your university's policy produced `RequestDisallowedByAzure` when you picked Germany West Central. You read it with `az policy assignment list --query "[].{name:displayName, regions:parameters.listOfAllowedLocations.value}" -o json` and got 5 regions. Reading an assignment: *scope* (what it covers), *definition* (the rule), *parameters* (the values, here the allowed list). Portal path: **Policy -> Assignments -> open "Allowed resource deployment regions" -> Parameters**. A policy blocks *creation*; it doesn't care which regions the service supports, so you intersected the two lists (italynorth, switzerlandnorth).

**Pricing tiers: F0 vs S0** ([quotas](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits), [pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/))
- **F0 (free)**: 5 audio hours of STT and 0.5 million neural TTS characters per month (pricing page). One F0 Speech resource per subscription (SETUP.md; I didn't find this on a docs page, but the portal enforces it).
- **S0 (standard)**: pay per use, higher limits, needed for fast transcription at scale and batch.
- F0 limits that matter: real-time STT allows **1 concurrent request**; real-time TTS allows **20 transactions per 60 seconds**; neither is adjustable on F0. Fast and batch transcription show "Not applicable" for F0 in the quota table, so check whether fast transcription works on F0 before relying on it (BUILD_PLAN 1.5).
- **At the limit:** the docs describe **HTTP 429 (too many requests)** for rate limits and say clients should retry with backoff; for TTS, many 429s come from backend capacity for a voice, not your quota. I did **not** find a page stating what happens when the *monthly* free allowance runs out, so don't assume; check the portal's usage and the error you get.

**Keys vs endpoints** ([authentication](https://learn.microsoft.com/en-us/azure/ai-services/authentication))
- **Endpoint** = where to send requests (region or custom subdomain URL). **Key** = the secret that proves you may use it, sent as the `Ocp-Apim-Subscription-Key` header.
- **KEY 1 and KEY 2**: "You can use either KEY1 or KEY2. Always having two keys allows you to securely rotate and regenerate keys without causing a service disruption." Rotation: switch the app to KEY 2, regenerate KEY 1, later swap back.
- Keys are secrets: `.env` only, never in chat or git. Entra ID auth (no keys) exists and is preferred in companies, but needs a custom subdomain; not needed here.

**Five ways to talk to Azure, and when to use each**
- **Portal** (portal.azure.com): create/delete resources, see keys, usage, cost. Use for one-off setup.
- **Speech Studio**: no-code tryouts of STT/TTS/voice gallery with your resource. Use to judge quality before coding.
- **Cloud Shell / `az` CLI**: scriptable management commands, no install (browser). Use for listing, policy queries, cleanup.
- **SDK** (`azure-cognitiveservices-speech`): your Python code calling Speech. This is what the project uses.
- **REST**: the raw HTTP API under everything; use when no SDK fits. See [how-speech-services-work](2026-10-02-how-speech-services-work.md).
- Underneath, management calls (create/delete) go through Azure Resource Manager; Speech calls themselves go straight to the regional service.

**Monitoring cost and usage.** Resource page -> **Monitoring -> Metrics** (usage by type), and **Cost Management + Billing** at the subscription (spend vs credit). Check both weekly while building.

**Cleanup and credit expiry**
- Deleting the resource group removes all resources in it (Resource Manager docs).
- Azure for Students ([page](https://azure.microsoft.com/en-us/free/students)): $100 credit "within 12 months", no card. After that you're notified and choose pay-as-you-go; if you don't upgrade, "your subscription and products will be disabled".

## 2. Why Azure Speech? How it compares *(added 2026-10-02)*

Explanation only, no exercises. Georgian cells were checked on 2026-10-02 against each provider's own language page; "not listed" means I looked at that page and didn't find Georgian, and "unverified" means I couldn't confirm it.

**What Azure Speech is.** One Microsoft service, one resource and one key, covering speech-to-text (STT), text-to-speech (TTS), translation and more. Around it are Speech Studio (no-code testing), SDKs (Python, C#, JS...) and a REST API. It is part of Azure AI services, now branded Foundry Tools in the docs.

**Comparison for Georgian (`ka-GE`)**

| Provider | Georgian STT | Georgian TTS | Biasing for Georgian | Real-time streaming (Georgian STT) | Free tier | Access for a student in Tbilisi |
|---|---|---|---|---|---|---|
| **Azure Speech** | Yes (`ka-GE`) | Yes: 2 standard voices (Eka, Giorgi); no HD/multilingual | Phrase list not shown for ka-GE; custom speech plain-text only | Yes (real-time SDK) | F0: 5 h STT, 0.5M TTS chars/month | Student credit, no card; region policy limits choices |
| **Google Cloud** | Yes: `chirp` (asia-southeast1), `chirp_2` (asia-southeast1), `chirp_3` (eu) | Not listed on the voices page | "Model adaptation" listed for `chirp_2`/`chirp_3`, not `chirp` | Unverified | Unverified | Needs a billing account (not checked) |
| **AWS** | Yes: Transcribe `ka-GE`, batch and streaming (streaming not in some regions) | Not listed (Polly has no Georgian) | Custom vocabulary column shows batch, streaming for ka-GE; custom language models: no | Yes, per the table | Unverified | Needs an AWS account with a card (not checked) |
| **OpenAI** | `gpt-transcribe` is multilingual; Georgian not explicitly confirmed. Whisper's language list includes `ka` | Not listed (TTS follows Whisper's list, which didn't include Georgian on the TTS page) | `prompt`, `keywords`, `languages` params; effect on Georgian unverified | Unverified | None found in docs | Prepaid credit, no free tier found |
| **ElevenLabs** | Scribe v2, "High Accuracy" tier (5-10% WER) | Yes in Eleven v4, v4 Turbo and v3; not in Flash v2.5 or Multilingual v2 | Keyterms: 1,000 in batch, 50 in realtime | Scribe v2 Realtime exists; Georgian there unverified | Free plan exists, details unverified | Account plus key; quotas not verified |
| **Whisper (open source)** | Yes, `ka` is in the language list; accuracy not verified | No (STT only) | Prompt text only | Not built in (file-based) | Free, runs on your hardware | Needs a GPU or slow CPU |
| **Meta MMS (open source)** | Claims 1,100+ languages; Georgian row not confirmed | Claims 1,100+ languages; Georgian not confirmed | None documented | Not mentioned | Free, CC-BY-NC license (non-commercial) | Research-grade setup; unverified for Georgian |

Sources: Azure language support; Google [STT languages](https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages) and [TTS voices](https://docs.cloud.google.com/text-to-speech/docs/voices); AWS [Transcribe languages](https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html) and [Polly languages](https://docs.aws.amazon.com/polly/latest/dg/supported-languages.html); OpenAI [speech-to-text](https://developers.openai.com/api/docs/guides/speech-to-text) and [text-to-speech](https://developers.openai.com/api/docs/guides/text-to-speech); ElevenLabs [models](https://elevenlabs.io/docs/overview/models) and [STT](https://elevenlabs.io/docs/capabilities/speech-to-text); Whisper [tokenizer](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py); [MMS README](https://github.com/facebookresearch/fairseq/blob/main/examples/mms/README.md). Google's TTS page fetch may have been partial, so treat "not listed" there as likely but not certain.

**Why we chose Azure**
- It documents Georgian for both STT and TTS, which several big providers don't (AWS has no Georgian TTS; OpenAI TTS doesn't list it).
- Free F0 tier plus the $100 student credit with no card (SETUP.md §2).
- One key and one SDK for both directions, so the voice loop (STT -> LLM -> TTS) needs one account.
- Speech Studio lets you judge quality without code, which is how you tested Eka and Giorgi.
- Docs are detailed and consistent; the quickstarts exist in Python.
- It's not a claim that Azure is the *best* Georgian speech system. It was the lowest-friction one with documented Georgian in both directions. Quality was to be tested, and you did.

**Where it's weaker, honestly**
- **Naturalness**: you rated Eka 3/5, Giorgi 3.5-4/5: understandable, not natural. Georgian has only standard neural voices, no HD or multilingual ones.
- **Biasing**: phrase lists aren't shown for `ka-GE`, so you can't boost rare words or tech terms ([code-switching note](2026-10-02-code-switching-stt-tts.md)).
- **Code-switching**: language ID doesn't switch mid-sentence.
- **F0 limits**: 1 concurrent real-time STT request, TTS capped at 20 transactions per 60 s, and fast transcription shows "Not applicable" on F0 (section 1).
- **Friction**: the Azure for Students subscription policy limited regions, and the Marketplace has look-alike paid cards.
- **Why this motivates BUILD_PLAN 2.6a**: the weaknesses are about *quality* (voice, rare words), not whether it works. ElevenLabs lists Georgian TTS (v4/v3) and has a Georgian-capable STT with keyterms, which targets exactly the two gaps. That's why 2.6a compares them on the same sentences behind a swappable interface, with Azure as fallback.

**Bottom line.** Azure is the safe default: documented Georgian in both directions, a free start, and one place to learn the basics. ElevenLabs is the likely winner on voice naturalness and on boosting tech terms; AWS and Google are credible for STT only (Google has model adaptation listed for Georgian; AWS has custom vocabulary), but neither gives Georgian TTS in what I verified. OpenAI would be the simplest to add if its Georgian STT proves good, and Whisper/MMS only matter if you wanted offline or free self-hosting at the cost of setup and licensing.

## 3. In this repo
SETUP.md §2 has the exact steps and the region decision; PROJECT_CONTEXT's decision log records `italynorth`. Code-switching limits of the service itself are in [the code-switching note](2026-10-02-code-switching-stt-tts.md); how the Speech SDK and audio work is in [how speech services work](2026-10-02-how-speech-services-work.md).

## 4. How the pieces fit
```
tenant (you) -> subscription (Students, $100) -> resource group voice-assistant
                                                   -> Speech resource roma-voice-assistant (F0, italynorth)
                                                        KEY 1/KEY 2 + region -> .env -> SDK/REST -> Speech service
policy (inherited from subscription) limits where you may create resources
```

## 5. Related tools
- Foundry/multi-service resource: one key for many AI services; we use the single Speech resource.
- Azure Key Vault, managed identities: where companies keep secrets; overkill for this project.
- Other clouds' speech (Google, AWS) work similarly: account, project, key, region.

## 6. Hands-on exercises
1. Portal -> your Speech resource -> **Keys and Endpoint**. Find KEY 1 (don't paste it anywhere) and the region. Check: region equals `AZURE_SPEECH_REGION` in `.env`.
2. Portal -> **Policy -> Assignments**, open the allowed-regions assignment, read Scope and Parameters. Check: you see the 5 regions.
3. Resource -> **Monitoring -> Metrics**. Find a usage metric. Check: you can say how much STT you used from the Speech Studio tests.
4. Cloud Shell (bash): `az account show -o table`, then `az group list -o table`, then `az resource list -g voice-assistant -o table`. Check: your subscription, `voice-assistant`, and `roma-voice-assistant` appear.
5. Portal -> **Cost Management**. Check: you can name the credit left. Don't delete anything yet.

## 7. Self-check
1. Name the four levels from account down to resource and what each holds.
2. Why did Germany West Central fail, and why isn't "the region supports Speech" enough?
3. Why does the app need both a key and a region?
4. Why two keys?
5. What deletes everything in one step, and what happens to Students resources if you never upgrade after the credit ends?
6. F0 gives 1 concurrent real-time STT request: what does that mean for a test that sends two at once?

<details><summary>Answers</summary>

1. Tenant (identities), subscription (billing/credit), resource group (lifecycle container), resource (the service).
2. A policy assignment on the subscription allows only 5 regions; you need a region both allowed by policy and supporting Speech.
3. The key is the secret; the region selects the regional endpoint, and keys are valid only in their region (401 otherwise).
4. Zero-downtime rotation: move to one key, regenerate the other.
5. Deleting the resource group; after the credit period the subscription and products are disabled unless you upgrade.
6. The second may be throttled (429-type error); retry or serialize.
</details>

## 8. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Doing exercises 1-5 on your real resource | About 45 min |
| B. Another AI tutor | Concept Q&A and quiz | About 45 min |
| C. Primary docs | Accurate definitions | About 1 hr |
| D. Video/course | Overview before touching the portal | Not verified |

**A. Prompt:**
> Walk me through learning/notes/2026-10-02-azure-basics.md. Do the 5 exercises one at a time on my real Azure resource: tell me where to click or what to run, ask me what I see, and never ask me to paste a key. Then quiz me on the self-check.

**B. Prompt (NotebookLM or any chat AI):**
> Using only these sources, explain Azure's tenant/subscription/resource group/resource hierarchy, how regions and region-scoped keys work, and how KEY1/KEY2 rotation works. Then quiz me with 5 questions. Sources: https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/overview, https://learn.microsoft.com/en-us/azure/ai-services/authentication, https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits, https://azure.microsoft.com/en-us/free/students

**C. Docs (opened 2026-10-02):**
- Azure Resource Manager overview: scopes, resource group rules, deletion.
- AI services authentication: keys, KEY1/KEY2, Entra ID.
- Speech quotas and limits: F0 vs S0, 429 advice.
- Speech pricing: the free allowances.
- Azure for Students: credit and expiry behavior.
- Hands-on module (from search, not read in full): https://learn.microsoft.com/training/modules/create-speech-enabled-apps ("Create speech-enabled apps with Microsoft Foundry"; provisioning a Speech resource, STT, TTS, SSML).

**D. Video:** my search returned articles and course catalog pages (e.g. a Skillsoft course "Microsoft Azure Fundamentals: Resource Management Hierarchy", likely paywalled), so I couldn't confirm a specific free video. Search terms: "Azure subscription vs resource group explained", "AZ-900 Azure fundamentals". Microsoft Learn's free AZ-900 learning path is a reasonable alternative; I didn't open it.
