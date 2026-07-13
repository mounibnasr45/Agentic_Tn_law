# Retrieval evaluation

A 56-question golden set over the Tunisian Constitution and Penal Code, four ranking
metrics, and an ablation that runs in CI and fails the build on regression.

```bash
docker compose up -d db
alembic upgrade head
python -m app.cli ingest
python -m eval.ablation              # print the table
python -m eval.ablation --gate       # fail if hit@5 regressed vs baseline.json
```

## What it found

The harness was not decoration. It found three real bugs, two of them in code that
looked fine and passed its tests.

### 1. The encoder was silently truncating the corpus

`paraphrase-multilingual-MiniLM-L12-v2` accepts **128 tokens**. `chunk_size` is measured
in **characters** — 700 chars is roughly 200–250 French tokens. So:

- **182 of 474** penal-code chunks (38%) exceeded the encoder's limit
- **6,329 of 51,951 tokens (12% of the corpus)** were dropped before ever being embedded

No exception. `transformers` prints a warning that nobody was reading. The text existed
in Postgres, was returned by the lexical arm, and was invisible to the dense arm.

`intfloat/multilingual-e5-small` takes 512 tokens and is also 384-dim, so the swap needed
no schema migration:

| | MiniLM-L12 (128 tok) | e5-small (512 tok) |
|---|---|---|
| hit@1 | 0.250 | **0.679** |
| hit@5 | 0.500 | **0.839** |
| MRR | 0.364 | **0.747** |

### 2. The lexical arm matched nothing on real questions

The first ablation showed every fusion weight from 0.0 to 0.8 scoring **identically**, and
lexical-only scoring 0.018 hit@10. That is not a tuning curve; that is a dead arm.

`websearch_to_tsquery` **ANDs** unquoted terms. A natural-language question —
*"Quelle est la peine pour un vol commis avec arme ?"* — compiles to

```
'quel' & 'pein' & 'vol' & 'comm' & 'arme'
```

and demands every stem in a single chunk. Across 716 chunks that matched **exactly zero**.
Hybrid retrieval was silently identical to dense-only.

AND-semantics is right for a keyword search box. It is wrong for a system whose users ask
questions in sentences. OR-ing the lexemes and ranking by `ts_rank_cd` took the lexical
arm from 0.018 to 0.518 hit@10 — and took the best hybrid config from 0.500 to 0.714 hit@5.

A keyword-shaped test would have passed the whole time.

### 3. An `AsyncSession` race that only fires on a cold connection

The two arms ran under `asyncio.gather()` — free parallelism, apparently. A SQLAlchemy
`AsyncSession` is **not** safe for concurrent use: two coroutines racing to provision the
same connection raise `InvalidRequestError`. It only fires on a session that has not yet
opened a connection, so it passes every warm test and fails intermittently on the first
query of a fresh request. Now sequential, and documented.

## The result nobody wanted

With the encoder fixed, **dense-only beats every hybrid configuration**:

| configuration | arm | hit@1 | hit@3 | hit@5 | hit@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|---|
| `w=0.0` **←** | dense only | **0.679** | **0.786** | **0.839** | 0.875 | **0.747** | **0.778** |
| `w=0.2` | hybrid | 0.321 | 0.554 | 0.732 | 0.786 | 0.483 | 0.556 |
| `w=0.4` | hybrid | 0.304 | 0.536 | 0.679 | 0.768 | 0.462 | 0.536 |
| `w=1.0` | lexical only | 0.179 | 0.286 | 0.357 | 0.554 | 0.265 | 0.332 |
| RRF | rank fusion | 0.393 | 0.679 | 0.750 | 0.821 | 0.543 | 0.611 |

The obvious defence of the lexical arm is that this golden set is all natural-language
questions, and lexical retrieval should earn its keep on **article-number lookups** —
*"que dit l'article 258 ?"*. That is a testable claim, so it was tested:

| | article-lookup hit@5 |
|---|---|
| dense only | **5/6** |
| hybrid w=0.2 | 4/6 |
| RRF | 4/6 |
| lexical only | 1/6 |

It does not hold. `e5-small` handles article numbers fine on its own.

**So the deployed default is dense-only, and `config.py` says why.** Shipping "hybrid"
because hybrid sounds better would be choosing a worse system for a nicer word.

The lexical arm and RRF stay in the codebase and in the ablation, because this result is
specific to *this* corpus (712 chunks) and *this* encoder, and must be re-measured before
it is trusted anywhere else.

Worth noting *why* weighted fusion loses: `normalize_bm25` min-max scales the top-50
lexical candidates onto [0,1], so the best lexical candidate always scores 1.0 — even when
it is junk. Normalising within the candidate set destroys the absolute-quality signal.
RRF, which never compares the two score scales, does measurably better (0.750 vs 0.732),
which is consistent with that explanation.

## Design

**Article-level relevance.** A long article is split across several chunks, and retrieving
any one of its parts means the retriever found the right law. Scoring at chunk level would
punish the retriever for our chunking decisions rather than for its ranking.

**No LLM judge.** Retrieval is a ranking problem, and ranking has real metrics. An LLM
grader is nondeterministic (the same run scores differently), costs money on every
execution, and cannot gate a build — you cannot fail CI on a number that wobbles.
Everything in `metrics.py` is a division.

**The regression gate tolerates 3 points, not zero.** With 56 questions, one question
flipping moves hit@5 by 1.8 points. A zero-tolerance gate would fail on noise and be
switched off within a week, which is worse than having no gate.

## Limitations

- 56 questions is small. A difference of ±0.05 is about three questions.
- The golden set is entirely natural-language questions plus the six article-lookup probes
  above. Multi-article questions, negations, and cross-references are not represented.
- One relevant article per question. Real legal questions often have several.
