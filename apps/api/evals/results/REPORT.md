# ClaimTrace retrieval evaluation

Generated 2026-07-26T09:20:27.006594+00:00.

> Synthetic corpus of 26 newly authored Korean patent-like claims across 2 documents, with 19 queries. This is large enough to catch a broken retrieval channel and to compare two configurations. It is **far too small to establish retrieval quality**, and none of these numbers should be read as a benchmark result.

## Configuration

| Setting | Value |
| --- | --- |
| Embedding provider | `sentence-transformers` |
| Embedding model | `intfloat/multilingual-e5-small` |
| Model version | `st1-e5` |
| Dimension | 384 |
| Vectors normalised | True |
| Normalisation | `nfkc-v1` |
| Lexical strategy | `postgres-simple-fts-trgm` `v1` |
| RRF k | 60 |
| top_k | 10 |

## Results

Recall is *set* recall: for a query with three relevant claims, Recall@1 cannot exceed 0.33. The two queries with no relevant claim are excluded from recall and MRR and reported separately in the last column.

| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Returned something for a no-answer query |
| --- | --- | --- | --- | --- | --- |
| dense | 0.770 | 0.926 | 0.971 | 0.961 | 100% |
| lexical | 0.740 | 0.897 | 0.912 | 0.961 | 50% |
| hybrid | 0.799 | 0.926 | 0.941 | 1.000 | 100% |

Mean query latency: dense 17.59 ms, lexical 6.3 ms, hybrid 17.88 ms.
 Indexing the whole corpus took 10.28 s.

## By query category

| Category | dense MRR@10 | lexical MRR@10 | hybrid MRR@10 |
| --- | --- | --- | --- |
| dependency | 1.000 | 0.778 | 1.000 |
| exact_terminology | 1.000 | 1.000 | 1.000 |
| korean_compound | 1.000 | 1.000 | 1.000 |
| paraphrase | 0.833 | 1.000 | 1.000 |
| technical_number | 1.000 | 1.000 | 1.000 |

## Weak and failed cases (hybrid)

Every labelled query placed a relevant claim at rank 1 or 2.

## Where hybrid loses to a single channel

| Metric | Better channel | That channel | Hybrid | Difference |
| --- | --- | --- | --- | --- |
| recall_at_5 | dense | 0.971 | 0.941 | -0.029 |

Individual queries where a single channel had better Recall@5:

- `q05-paraphrase-battery-cooling` (paraphrase): dense Recall@5 1.00 vs hybrid 0.50

## Reproducing

```bash
docker compose up -d postgres
docker compose run --rm api python -m evals.run
```

Add `--provider fake` to run without downloading a model. The fake provider is deterministic but not semantic, so its dense numbers measure plumbing rather than retrieval quality.
