# Georgian in Unicode: Mkhedruli and Mtavruli

*(short note)*

Checked 2026-10-03: the Unicode 11.0 overview page, and Python 3.14 snippets run in this repo's venv (Unicode data 16.0.0). The Unicode chart PDF for Georgian Extended (U+1C90) downloaded but my fetch tool couldn't read it, so the ranges below come from the Unicode 11 page and the code points checked in Python.

## 1. What and why

**Problem.** Azure STT returned `Გამარჯობა` for a sentence start. It looks the same, but the first letter is `Გ` U+1C92, not `გ` U+10D2, so `"Გამარჯობა" == "გამარჯობა"` is `False`. That breaks keyword search (`lookup_faq`) and eval comparisons.

- **Mkhedruli** (U+10D0-U+10FF) is the everyday Georgian alphabet and has no case. **Mtavruli** is a set of capital-style letters (U+1C90-U+1CBF) added in **Unicode 11 (2018)** for headings and all-caps text. The Unicode 11 page says they have case mappings to the Mkhedruli letters. `unicodedata.name("Გ")` is `GEORGIAN MTAVRULI CAPITAL LETTER GAN`.
- Offset: each Mtavruli letter is exactly `0xBC0` above its Mkhedruli letter (`0x1C92 - 0x10D2 = 0xBC0`). U+1CBB and U+1CBC are unassigned, hence the exclusion in `MTAVRULI_TO_MKHEDRULI`.
- Azure's display formatting capitalizes sentence starts and, for Georgian, uses Mtavruli.

**Fix and alternatives**
- `str.lower()` / `casefold()` do map Mtavruli back (`"Გ".lower() == "გ"` is `True` here), but also lowercase `QR` and `API`, which we want to keep. So `speech_smoke.py` uses `str.translate` with a dict from code point to code point: `text.translate({0x1C92: 0x10D2, ...})`. `translate` looks up each character's ordinal in the table and leaves others alone.
- For **comparison** (search, WER) lowercasing everything is fine and simpler: `casefold()` is the string-comparison version of `lower()`.

**Normalization before comparing text** (general, applies to eval later)
- Case (`casefold`), punctuation (STT adds `.` and `,`; a reference sentence may not), whitespace, and Unicode form. `unicodedata.normalize("NFC", s)` composes characters; NFKC also folds compatibility variants. Georgian letters have no combining forms, so NFC changes nothing here (I checked `"Გ"`), but text from other sources (Latin with accents) can differ.
- `unicodedata.name(ch)` and `ord(ch)` / `hex(ord(ch))` are the tools for finding out what a mystery character is. Exercise: `python -c "import unicodedata as u;print([(hex(ord(c)),u.name(c)) for c in 'Გა'])"`.

## 2. In this repo
`to_mkhedruli()` in `speech_smoke.py` is applied to every transcript. Step 2.1 (STT into the agent) and 3.4 (eval) should reuse it, then add `casefold` and punctuation stripping for WER.

## 3. How it fits
`audio -> Azure STT (display text with Mtavruli capitals) -> to_mkhedruli -> text for lookup_faq / LLM / WER`

## 4. Related tools
- `str.lower()`/`casefold()`: simplest; use for comparison but not for display text.
- `re` with `re.IGNORECASE`: also handles it, but less explicit.
- Request raw (non-display) output: Azure's detailed results include a lexical form; I didn't test whether it avoids the capitals.

## Sources
- [Unicode 11.0 overview](https://www.unicode.org/versions/Unicode11.0.0/): opened; mentions Georgian Mtavruli capitals (U+1C90..U+1CBA, U+1CBD..U+1CBF) with case mappings.
- Georgian Extended chart: https://www.unicode.org/charts/PDF/U1C90.pdf (redirects to the current version; PDF not readable by my tool, open it in a browser).
- [Python `str` methods (`translate`, `lower`, `casefold`)](https://docs.python.org/3/library/stdtypes.html#str.translate) and the `unicodedata` module docs: https://docs.python.org/3/library/unicodedata.html (the second page not opened).
- Related: [keyword search and Georgian morphology](2026-10-03-keyword-search-and-retrieval.md), [speech services](2026-10-02-how-speech-services-work.md).
