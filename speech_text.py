"""Step 2.5: the speech-text step. Rewrites a reply so Azure's Georgian voice can say it, just before TTS.
The text on screen stays as it was; only what the voice reads changes.

Why: Azure's Georgian voices have no English pronunciation and skip some symbols. Measured in 1.5
and 2.5 (TTS → STT round trips and Roman listening):
    "QR"          read as Georgian letters run together, "ქრ"      → ქიუარ
    "GB"          heard as "იგებ"                                   → გიგაბაიტი
    "15 ₾"        the ₾ sign is silent: "15"                        → 15 ლარი
    "0.50 ₾"                                                        → 50 თეთრი
    "10:00-დან"   read as "10 0 0 დან"                              → 10 საათიდან
    "5G"          heard as "5. ჯი" at best                          → 5 ჯი
    "„ჯიხვი S""   the S disappears                                  → ჯიხვი ეს
After the rewrite, prices, times and plan names come back word for word, and QR is said at all
("ქი ვარ" instead of nothing). eSIM comes back as "ის იმის", so only listening can tell if it sounds
right: a round trip tests TTS and STT together.
Step 3.6 (hiking guide) added, by the same pattern but not yet round-trip measured:
    "6 კმ-ია"     an abbreviation, read letter by letter                → 6 კილომეტრია
    "20.4"        a decimal point                                       → 20 მთელი 4
    "SOS"         would be spelled with English letter names            → სოს

How: a few regex rules for numbers and symbols, then every Latin-letter word is looked up in TERMS
(how a Georgian speaker says it), and short all-caps words not in TERMS are spelled with English
letter names (API → ეიპიაი). Anything left in Latin letters is reported by leftover_latin(), so the
voice loop can show which words still need an entry.

Georgian case suffixes are written after a hyphen on foreign words ("SIM-ის", "GB-ს"), so the rules
glue the suffix onto the spoken form: "SIM-ის" → "სიმის", "GB-ს" → "გიგაბაიტს".
(SSML <sub alias="ქიუარ">QR</sub> would do the same substitution, but then every reply has to be
wrapped in SSML and escaped; plain text is simpler and gives the same audio.)

Run:  python speech_text.py                  show what changes in every FAQ answer and fixed reply
      python speech_text.py "QR კოდი 5 ₾"    rewrite one text
"""
import re
import sys

# English term → how it's said, in Georgian letters. "|" splits the stem from the nominative ending:
# "გიგაბაიტ|ი" is said "გიგაბაიტი" on its own, but "GB-ს" becomes "გიგაბაიტს" (the ending drops before
# a suffix). Keys are matched as written first, then case-insensitively.
TERMS = {
    "GB": "გიგაბაიტ|ი", "MB": "მეგაბაიტ|ი", "SIM": "სიმ", "eSIM": "ისიმ", "PIN": "პინ", "PUK": "პუკ",
    "SMS": "ესემეს|ი", "LTE": "ელტეე", "WiFi": "ვაიფაი", "iPhone": "აიფონ|ი", "Android": "ანდროიდ|ი",
    "email": "იმეილ|ი", "online": "ონლაინ", "OK": "ოქეი", "key": "ქი", "app": "აპ|ი", "Jikhvi": "ჯიხვი",
    "SOS": "სოს", "GPS": "ჯიპიეს", "camping": "კემპინგ|ი", "trail": "ტრეილ|ი",
}
# English letter names in Georgian letters, for acronyms that aren't in TERMS (QR → ქიუარ).
LETTERS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                   ["ეი", "ბი", "სი", "დი", "ი", "ეფ", "ჯი", "ეიჩ", "აი", "ჯეი", "კეი", "ელ", "ემ", "ენ", "ოუ",
                    "პი", "ქიუ", "არ", "ეს", "ტი", "იუ", "ვი", "დაბლიუ", "ექს", "უაი", "ზედ"]))
MAX_SPELLED = 5   # all-caps words up to this length are spelled letter by letter
VOWELS = set("აეიოუ")
# After a stem ending in a consonant, these suffixes take a linking vowel: საათ + დან → საათიდან
LINKED_SUFFIX = {"დან": "იდან", "მდე": "ამდე"}

GEORGIAN_SUFFIX = r"(?:-([ა-ჰ]+))?"  # an optional "-ის", "-ზე", ... after a foreign word or a symbol

PRICE = re.compile(r"(\d+)(?:[.,](\d{1,2}))?\s?₾" + GEORGIAN_SUFFIX)
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b" + GEORGIAN_SUFFIX)
ALWAYS = re.compile(r"\b24/7\b")
RANGE = re.compile(r"\b(\d+)-(\d+)\b")
PERCENT = re.compile(r"(\d)\s?%")
KM = re.compile(r"(\d)\s?კმ" + GEORGIAN_SUFFIX + r"(?![ა-ჰ])")   # "6 კმ-ია" → "6 კილომეტრია"
DECIMAL = re.compile(r"\b(\d+)\.(\d+)\b")                       # "20.4" → "20 მთელი 4" (after prices)
NETWORK = re.compile(r"\b(\d)G\b" + GEORGIAN_SUFFIX)          # 4G, 5G
DIGIT_LATIN = re.compile(r"(\d)([A-Za-z])")                     # "1GB" → "1 GB"
LATIN_WORD = re.compile(r"(?<![A-Za-z])(Wi-Fi|[A-Za-z]+)" + GEORGIAN_SUFFIX)
LATIN = re.compile(r"[A-Za-z]+")
DECORATION = re.compile(r"[„“”\"«»]")  # quote marks are only visual
ARROW = re.compile(r"\s*→\s*")          # "„უსაფრთხოება" → „SIM-ის დაბლოკვა"" is a menu path


def with_suffix(spoken: str, suffix: str | None) -> str:
    """Join a spoken form ("stem|ending") and an optional Georgian suffix."""
    stem, _, ending = spoken.partition("|")
    if not suffix:
        return stem + ending
    if stem[-1] not in VOWELS:
        suffix = LINKED_SUFFIX.get(suffix, suffix)
    return stem + suffix


def say_price(m: re.Match) -> str:
    lari, tetri, suffix = int(m.group(1)), m.group(2), m.group(3)
    tetri = int(tetri.ljust(2, "0")) if tetri else 0  # "1.5" means 1 lari 50 tetri
    if lari and tetri:
        return f"{lari} ლარი და {tetri} {with_suffix('თეთრ|ი', suffix)}"
    if tetri:
        return f"{tetri} {with_suffix('თეთრ|ი', suffix)}"
    return f"{lari} {with_suffix('ლარ|ი', suffix)}"


def say_clock(m: re.Match) -> str:
    hours, minutes, suffix = int(m.group(1)), int(m.group(2)), m.group(3)
    if minutes == 0:
        return f"{hours} {with_suffix('საათ|ი', suffix)}"
    return f"{hours} საათი და {minutes} {with_suffix('წუთ|ი', suffix)}"


def say_latin(m: re.Match) -> str:
    word, suffix = m.group(1).replace("-", ""), m.group(2)  # "Wi-Fi" is looked up as "WiFi"
    spoken = TERMS.get(word) or next((v for k, v in TERMS.items() if k.lower() == word.lower()), None)
    if spoken is None and word.isupper() and len(word) <= MAX_SPELLED:
        spoken = "".join(LETTERS[c] for c in word)
    if spoken is None:
        return m.group(0)  # unknown word: leave it; leftover_latin() reports it
    return with_suffix(spoken, suffix)


def speakable(text: str) -> str:
    """The text as the Georgian voice should read it."""
    text = DECORATION.sub("", text)
    text = ARROW.sub(", ", text)
    text = PRICE.sub(say_price, text)
    text = CLOCK.sub(say_clock, text)
    text = ALWAYS.sub("24 საათი, კვირაში 7 დღე", text)
    text = RANGE.sub(r"\1-დან \2-მდე", text)
    text = PERCENT.sub(r"\1 პროცენტი", text)
    text = KM.sub(lambda m: f"{m.group(1)} {with_suffix('კილომეტრ|ი', m.group(2))}", text)
    text = DECIMAL.sub(r"\1 მთელი \2", text)
    text = NETWORK.sub(lambda m: f"{m.group(1)} {with_suffix('ჯი', m.group(2))}", text)
    text = DIGIT_LATIN.sub(r"\1 \2", text)
    text = LATIN_WORD.sub(say_latin, text)
    return re.sub(r" {2,}", " ", text).strip()


def leftover_latin(spoken: str) -> list[str]:
    """Latin-letter words still in the spoken text: the voice will mangle these. Add them to TERMS."""
    return LATIN.findall(spoken)


def _show_all() -> None:
    """Print every FAQ answer and fixed reply that the rewrite changes."""
    import json
    from pathlib import Path
    from graph import CLARIFY_FALLBACK, HANDOFF_REPLIES, NO_FACT, STEP_LIMIT_REPLY

    faq = json.loads((Path(__file__).parent / "data" / "faq.json").read_text(encoding="utf-8"))
    replies = [reply.format(fact=NO_FACT) for reply in HANDOFF_REPLIES.values()]
    texts = [e["answer"] for e in faq] + replies + [NO_FACT, CLARIFY_FALLBACK, STEP_LIMIT_REPLY]
    changed = 0
    for text in dict.fromkeys(texts):  # dedupe, keep order
        spoken = speakable(text)
        if spoken != text:
            changed += 1
            print(f"  {text}\n→ {spoken}\n")
        if leftover_latin(spoken):
            print(f"  left in Latin letters: {leftover_latin(spoken)}\n")
    print(f"{changed} of {len(set(texts))} texts changed")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = speakable(" ".join(sys.argv[1:]))
        print(out)
        if leftover_latin(out):
            print(f"left in Latin letters: {leftover_latin(out)}")
    else:
        _show_all()
