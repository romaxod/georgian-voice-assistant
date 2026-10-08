# Keyword search, ranking and Georgian morphology

Date: 2026-10-03. Checked against the SQLite FTS5 docs, the Manning/Raghavan/Schütze IR book site, search results on Georgian NLP tools, and by running `lookup_faq` and an FTS5 snippet in this repo (SQLite 3.45.1 has FTS5).

## 1. What you're learning, and why it matters

**Problem:** given a short query ("ბარათი", "ჯიხვი M"), return the right FAQ entries first. This is **retrieval**: finding relevant pieces of knowledge to give the model (the core of RAG, retrieval-augmented generation). Bad retrieval means the model answers from the wrong entry or invents.

**How `lookup_faq` scores.** Per search word, an entry gets points; the sum is its score; sort by score, then `id`:
- **+2** if the exact word is in `topic` or `keywords`. Whole-word match is done by padding with spaces: `' ' || topic || ' ' || keywords || ' ' LIKE '% word %'`.
- **+2** if the word's **stem** is in `topic` (the entry's headline), **+1** if the stem is anywhere in the entry.
- Stems under 3 letters skip substring checks (else "m" matches every "SIM" and "MB").
- **Stopwords** (რა, და, როგორ...) are dropped: they're in nearly every entry and match everything.

**Georgian morphology.** Georgian is **agglutinative**: endings attach to the word for case and plural. ბარათი (nominative), ბარათის (genitive), ბარათით (instrumental) share one stem. A **stem** is the shared front part. The naive stemmer cuts one suffix from `("ების","ებს","ები","ის","ით","ში","ზე","ად","ს","ი")` if at least 3 letters remain. `LIKE '%ბარათ%'` then finds all forms. It is crude: it can over-cut, and it misses stem changes inside the word (verbs especially).

**Why each rule exists (real before/after):**
- Count-only scoring: `ბარათი` -> `['balance-topup','new-number','pin-puk']`: all tied, alphabetical tie-break, a bank-card entry first. With topic weighting: `['sim-lost','sim-replace','balance-topup']`.
- `ტარიფები` lost the overview entry on a tie, and `ჯიხვი M` dropped the single letter M. After the whole-word bonus: `ტარიფები` -> `['plans-overview','plan-change','plan-l']`, `ჯიხვი M` -> `['plan-m','plan-l','plan-s']`.
- Others: `როუმინგი ევროპაში` -> `['roaming-europe','roaming-no-package']`; `esim` -> `['esim-activation','new-number']` (LIKE is case-insensitive for ASCII only, so Georgian has no case issue and Latin works); `პიცა` -> `[]`; `რა როგორ` -> `[]` (all stopwords). Returning `[]` is a feature: the model must say "I don't know" or hand off.
- **Real ambiguity:** ბარათი means SIM card and bank card. A good assistant asks a clarifying question; it's a good eval case for steps 2.2 and 3.1.

## 2. In this repo

`faq.py` functions `_words`, `_stem`, `_escape_like`, `lookup_faq`. Try `.venv/bin/python faq.py ბარათი`. Why plain `LIKE` for 21 entries: explainable (you can say why entry X ranked first), no dependencies, and the model in step 1.4 will send short keywords, not sentences.

## 3. How the pieces fit

```
query -> split, strip, lowercase, drop stopwords, dedupe, cap 5 -> per word: exact? stem-in-topic? stem-anywhere?
      -> sum points per entry -> ORDER BY score DESC, id LIMIT 3 -> list of dicts
```

## 4. Related tools and when to switch

- **SQLite FTS5:** a built-in full-text index. `CREATE VIRTUAL TABLE ft USING fts5(topic, body)`; the default `unicode61` tokenizer splits on non-letters and works with Georgian letters; prefix queries use `ბარათ*` (the `*` outside quotes); `ORDER BY bm25(ft)` ranks (lower is better). I ran it here: `match 'ბარათ*'` found ბარათი. Gotcha: `MATCH` has its own query syntax, so a stray quote is an error even with a placeholder: `fts5: syntax error near "'"`. Sanitize/quote the query (wrap each word in double quotes).
- **BM25:** the standard keyword ranking formula. Roughly: rare words count more (IDF, inverse document frequency), repeated words help with diminishing returns, long documents are normalized. It's what FTS5, Elasticsearch and Lucene use. It beats hand-tuned weights once you have hundreds of documents.
- **Stemmers/lemmatizers.** A **lemmatizer** maps a word to its dictionary form. For Georgian I found: a finite-state morphological analyzer (Irina Lobzhanidze, "Finite-State Computational Morphology: An Analyzer and Generator for Georgian", Springer, reported in search results), and a small seq2seq lemmatizer on GitHub, `screeve/lemmatizer` (BART trained on the Georgian National Corpus; 3 stars, 4 commits, MIT; I opened its README). I found no standard, maintained one in common libraries (NLTK/Snowball have no Georgian stemmer as far as I could confirm; I did not verify that exhaustively). So the hand-written suffix list is a reasonable stopgap, and its limits are worth measuring.
- **Embeddings / vector search:** convert text to vectors so "ფასი" and "ღირებულება" match by meaning. Handles synonyms and paraphrase, costs an embedding model, an index, and is harder to explain. **Hybrid search** runs BM25 and vectors, then merges rankings (e.g. reciprocal rank fusion). Switch when queries are long natural sentences, synonyms matter, or the corpus grows past a few hundred entries.
- **Retrieval evaluation:** build a tiny labeled set (e.g. 30 queries, each with the correct entry id(s)). **precision@k** = fraction of the top k results that are correct; **recall@k** = fraction of the correct entries that appear in the top k. Run it after each change (stemmer, weights, FTS5) to see if it really improved. This ties into Phase 3 evals; the break cases above are the seed of that set.

## 5. Hands-on exercises

1. Run `faq.py` with `ბარათი`, `ბარათის`, `ბარათით`. Check: overlapping top results.
2. Run `faq.py "რა როგორ"` and `faq.py პიცა`. Check: `[]` both.
3. Write 10 queries with the expected entry id in a Python list; compute precision@1 and recall@3 with a loop over `lookup_faq`. Check: a number you can compare after tweaking `SUFFIXES`.
4. Copy the FTS5 snippet: create an fts5 table in `:memory:`, insert the FAQ rows, query `ბარათ*` ordered by `bm25`. Check: compare ranking to `lookup_faq`.
5. Make a query that fools the stemmer (e.g. a short word ending in "ს"). Check: explain why.

## 6. Self-check

1. Why do suffixes matter for Georgian search? 2. Why a stem-length minimum of 3? 3. Why do topic matches weigh more than body matches? 4. What does FTS5 give you over LIKE, and what new risk? 5. Define precision@k and recall@k. 6. When would you add embeddings?

<details><summary>Answers</summary>

1. One word has many case forms; exact match misses most of them. 2. Short stems match inside unrelated words ("m" in SIM/MB). 3. The topic is the entry's headline; body mentions are incidental, so they caused ties and wrong first results. 4. A real index, tokenizer, prefix queries, BM25 ranking; but MATCH has its own syntax so input must be quoted. 5. Share of the top k that is relevant; share of all relevant that made the top k. 6. Natural-language queries, synonyms, large corpus, or when measured recall on the labeled set is too low.
</details>

## Query rewriting for follow-ups *(added 2026-10-03)* *(short note)*

**Problem:** `lookup_faq` only sees the words you give it. After "რა ღირს როუმინგი ევროპაში?", the follow-up "და რამდენ ხანს მოქმედებს?" has no roaming word in it, and after removing stopwords almost nothing is left to match. Searching with the raw follow-up finds nothing useful.

- **Conversational query rewriting** (also "standalone question generation"): before searching, an LLM turns the latest message plus the chat history into a self-contained search query. It is a standard step in conversational RAG.
- **In this repo (`graph.py`, step 2.1):** the `understand` node outputs `topic` with follow-ups resolved from history. Real runs: the first question gave `topic='როუმინგი ევროპა ფასი'`; the follow-up gave `'როუმინგი ევროპა ვადა'` and the answer was "7 დღე". The prompt tells it to output 2-4 keywords, not a sentence, which matches how `lookup_faq` scores (per word, stopwords dropped). See [LangChain chat models and structured output](2026-10-03-langchain-chat-models-structured-output.md).
- **Cost and risk:** one extra LLM call per turn (about 1-2.5 s in our runs), and a bad rewrite poisons retrieval: wrong topic, wrong facts. Test it with follow-up cases in the labeled set (precision@k above), not only first questions.
- **A precision problem it exposes:** "გაქვთ სატელევიზიო პაკეტები?" now always goes through lookup, which returned unrelated entries because it matched on "პაკეტ" (package) in other entries. The stem rule has no way to say "TV" is the important word. Fixes to try later: rank by rarity (BM25), require all rare words, or a minimum score, so "no good match" returns `[]` and the assistant offers an operator.
- **Where to read:** LangChain's conversational RAG tutorial and "history-aware retriever" idea; search those terms (not opened for this note).

## The vocabulary mismatch, query expansion and ties *(added 2026-10-08)* *(short note)*

**Problem (step 3.3):** the customer said "move me to ჯიხვი L"; the model searched `L პაკეტი გადართვა`; the FAQ says `ტარიფი` for plans (`პაკეტი` = add-on), so `plan-change` was never returned (0/5 in the eval). Lexical search only matches shared words.

- **The vocabulary problem** (Furnas, Landauer, Gomez, Dumais, "The vocabulary problem in human-system communication", CACM 30(11), 1987): two people pick the same word for a thing with probability under 0.20, and a system keyed to one designer's word fails 80-90% of the time in many cases (from the abstract as shown in search results). Their remedy, "unlimited aliasing", is many synonyms per entry. Here the LLM in `understand` is the aliasing layer, and it guessed wrong.
- **Query replacement vs expansion.** Prompt v1 told the model to use the FAQ's terms, so it *replaced* the customer's words: `ტარიფები` became `ტარიფი`. v2 says keep the customer's words and *add* the FAQ term. Expansion keeps recall from the original words and adds the vocabulary bridge; replacement throws away signal. Another route that doesn't touch the LLM: add synonyms to the FAQ entry's `keywords` (document expansion), e.g. `პაკეტი`, `პლანი` on `plan-change`.
- **Ties.** Our SQL is `ORDER BY score DESC, id LIMIT 3`. A one-word query scored every plan entry equally, so `id` order decided and `plans-overview` fell out of the top 3; the reply listed L and M but not S. A tie-break by id is arbitrary, not relevant. Better: a second sort key like "word found in topic", or a larger LIMIT for broad queries.
- **BM25/IDF** would weigh `ტარიფი` low if it appears in many entries, but all plan entries contain it, so it would still tie among them; length normalization would favor shorter entries, not the overview. **Embeddings** would put "გადამიყვანეთ L-ზე" near "plan change" with no shared word, which is the standard fix for vocabulary mismatch, at the cost of explainability. **Hybrid** search combines both. Full story and tests: [error analysis note](2026-10-08-error-analysis-and-fixing-one-failure.md).
- Source: <https://cacm.acm.org/magazines/1987/11/10035-the-vocabulary-problem-in-human-system-communication> was in search results as a mirror (<https://cacmb4.acm.org/magazines/1987/11/10035-the-vocabulary-problem-in-human-system-communication>); I did not open it. The summary above comes from the search result text.

## 7. Ways to learn it (choose later)

| Option | Good for | Time |
|---|---|---|
| A. Claude walks you through | Scoring rules and the labeled-set exercise | 45 min |
| B. Another AI tutor | BM25 math, embeddings vs keywords | 45 min |
| C. Primary docs | FTS5 and IR fundamentals | 2 h |
| D. Video/course | Hybrid search intuition | 1-2 h |

**A.** Paste: "Read learning/notes/2026-10-03-keyword-search-and-retrieval.md and walk me through exercises 1-5 with faq.py, then help me build the labeled query set."

**B.** NotebookLM with the C links. Prompt: "Using https://www.sqlite.org/fts5.html and https://nlp.stanford.edu/IR-book/html/htmledition/irbook.html, explain BM25 step by step with a 3-document example, then compare keyword, vector and hybrid search for a 21-entry Georgian FAQ."

**C.**
- <https://www.sqlite.org/fts5.html>: sections on tokenizers (unicode61), prefix queries, `bm25()`, and query syntax.
- <https://nlp.stanford.edu/IR-book/html/htmledition/irbook.html>: "Introduction to Information Retrieval" (Manning, Raghavan, Schütze, 2008); read the chapters on the term vocabulary (stemming and lemmatization), scoring/tf-idf, and evaluation (precision/recall). Chapter list from the book site; I didn't read the chapters.
- <https://github.com/screeve/lemmatizer>: the Georgian lemmatizer README.

**D.**
- "A no nonsense intro to BM25" (YouTube): <https://www.youtube.com/watch?v=TW9vHU1GpU4> (title and link from a search result; creator not confirmed; not watched).
- "Hybrid Search in RAG Explained" (YouTube): <https://www.youtube.com/watch?v=D8LmsEOJvPI> (same caveat).
- Course: "Retrieval Optimization: From Tokenization to Vector Quantization", DeepLearning.AI with Qdrant (instructor Kacper Łukawski), free, about 1.5 h, covers measuring retrieval quality: <https://www.deeplearning.ai/courses/retrieval-optimization-from-tokenization-to-vector-quantization> (details from search results; not opened).
