# Retrieval evaluation

A small, reproducible measurement of ClaimTrace's claim retrieval.

```bash
docker compose up -d postgres
docker compose run --rm api python -m evals.run              # configured model
docker compose run --rm api python -m evals.run --provider fake
```

Writes `results/results.json` (machine-readable) and `results/REPORT.md`
(the summary), both committed so a change in retrieval behaviour shows up as a
diff.

## What it actually runs

The real pipeline, end to end, through the real HTTP API:

```
build synthetic PDFs → POST /documents → POST /claims/parse
  → POST /claims/index → POST /search/claims  (dense, lexical, hybrid)
```

There is deliberately **no** evaluation-only retrieval path. If claim search
regresses, this regresses. It runs against a dedicated `*_eval` database that it
creates, migrates, and truncates itself, so it never touches development data.

## The dataset

| | |
| --- | --- |
| `data/corpus.json` | 26 claims across 2 documents |
| `data/queries.json` | 19 queries with relevance labels |

All of it is newly authored for this repository. **No third-party or copyrighted
patent claim is reproduced here** - the subject matter is deliberately mundane
(a sensor collector, a battery thermal manager) and the wording is invented. The
point is to exercise Korean claim structure, dependency expressions, technical
units, and compound terminology, not to describe a real invention.

Query categories, chosen so that neither channel can win everything:

| Category | What it targets |
| --- | --- |
| `exact_terminology` | Verbatim phrases. Easy for lexical, harder for a small embedding model. |
| `korean_compound` | Compounds written without the spaces the claim uses (`환경감시모듈`). Full-text search cannot match these at all; trigram is what recovers them. |
| `paraphrase` | Almost no shared surface tokens with the target. The dense channel's job. |
| `dependency` | Structural queries (`다중종속항`, `제7항을 인용하는…`), which only match because the search text carries a metadata header. |
| `technical_number` | Units and figures (`섭씨 45도`, `50밀리볼트`). |
| `irrelevant` | **No relevant claim exists.** Scored separately, so a channel that always returns something is measurably wrong rather than silently rewarded. |

Labels were written from the claim text before any retrieval run and have not
been adjusted to improve any channel's score. `test_eval_metrics.py` asserts that
every label points at a claim that exists, so a stale label fails the suite
rather than quietly depressing a metric.

## Metrics

- **Recall@1/3/5** is *set* recall: the fraction of a query's relevant claims in
  the top *k*. For a query with three relevant claims, Recall@1 cannot exceed
  0.33, so a low Recall@1 here is partly an artefact of the labels.
- **MRR@10** uses the rank of the first relevant result; 0 if none is in the top
  10.
- Queries with no relevant claim are excluded from both averages - there is no
  meaningful recall of an empty set - and reported separately.

The report also contains a **"where hybrid loses to a single channel"** section.
It exists because MRR looks only at the first relevant hit and can hide a real
cost of fusion: RRF interleaves two lists, so a claim one channel ranked fourth
can be pushed past the cutoff by the other channel's confident-but-wrong
candidates. Looking for that deliberately is better than letting the aggregate
flatter the design.

## What these numbers are not

26 claims and 19 queries is enough to catch a broken retrieval channel and to
compare two configurations against each other. It is **far too small to establish
retrieval quality**, and nothing here should be quoted as a benchmark result. A
real evaluation needs a corpus orders of magnitude larger, labels from someone
who reads patents professionally, and queries that were not written by the person
who wrote the corpus.

With `--provider fake`, the dense numbers measure plumbing rather than retrieval:
that provider is deterministic but not semantic, and cannot match a paraphrase.
