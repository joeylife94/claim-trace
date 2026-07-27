# ClaimTrace grounded-generation evaluation (ollama)

Generated 2026-07-26T23:27:56.274319+00:00.

> **A small model on a synthetic corpus.** These numbers describe `qwen2.5:1.5b` answering 16 newly authored questions over 23 synthetic claims. That is enough to show the pipeline works with a real model and to catch a gross regression. It is **not** a benchmark, and it does not establish that this system answers Korean patent questions well.

## Configuration

| Setting | Value |
| --- | --- |
| Tier | `ollama` |
| Provider | `ollama` |
| Model | `qwen2.5:1.5b` |
| Documents | 3 |
| Claims | 23 |
| Cases | 16 |
| Embedding model | `intfloat/multilingual-e5-small` |
| top_k | 6 |

## Metrics

| Metric | Value | What it means |
| --- | --- | --- |
| Structured-output success | 1.000 | the answer satisfied the JSON schema |
| Answerability accuracy | 0.625 | answered when the corpus answers, declined when it does not |
| Insufficient-evidence precision | 0.400 | of the questions declined, how many should have been |
| Insufficient-evidence recall | 0.500 | of the questions that should be declined, how many were |
| Evidence-ID validity | 0.938 | no answer was refused for naming an id the server never issued |
| **Citation resolution** | **1.000** | **every returned quote is the stored page text at its own locator** |
| Statement citation coverage | 1.000 | returned statements carrying a resolvable citation |
| Evidence selection precision | 0.530 | cited claims that were credited by the labels |
| Evidence selection recall | 0.792 | required claims that were cited |
| End-to-end success | 0.562 | all of the above, per case |
| Forbidden citations | 0 | citations outside a scoped question's document |
| Mean latency | 7.67 s | per question |


## Weak and failed cases

| Case | Category | Status | Expected | Cited | Why |
| --- | --- | --- | --- | --- | --- |
| `g01-single-storage` | single_evidence | 200 | collector#1 | collector#4, collector#5, collector#6, collector#7, collector#8 | cited none of the required claims |
| `g07-paraphrase-overwrite` | paraphrase | 200 | collector#4 | collector#4, collector#5, collector#8 | declined an answerable question |
| `g09-dependency-parent` | dependency | 200 | collector#5 | collector#4, collector#5 | declined an answerable question |
| `g10-dependency-method-chain` | dependency | 200 | collector#8 | adversarial#1, collector#8 | declined an answerable question |
| `g11-scoped-collector-no-valve` | document_scoped | 200 | (decline) | collector#1, collector#2, collector#4, collector#6 | answered a question the corpus does not answer |
| `g12-scoped-thermal-no-timestamp` | document_scoped | 200 | (decline) | thermal#1, thermal#2, thermal#5, thermal#6, thermal#7, thermal#8 | answered a question the corpus does not answer |
| `g15-conflicting-threshold` | conflicting | 502 grounded_repair_failed | thermal#2 | (nothing) | request failed: grounded_repair_failed |

## By category

| Category | Cases | End-to-end success |
| --- | --- | --- |
| conflicting | 1 | 0/1 |
| dependency | 2 | 0/2 |
| document_scoped | 2 | 0/2 |
| injection | 1 | 1/1 |
| multi_evidence | 3 | 3/3 |
| paraphrase | 2 | 1/2 |
| single_evidence | 3 | 2/3 |
| unanswerable | 2 | 2/2 |

## What a passing citation does and does not establish

A resolved citation establishes that the statement points at retrieved source text, that the text is stored by this deployment, and that a reader can open the exact page and character range it came from.

It does **not** establish that the cited claim entails the statement. No amount of identifier checking can prove that a sentence is a faithful reading of the text it cites; that is a semantic judgement, and this pipeline makes none. A grounded answer is a *checkable* answer, not a verified one.

ClaimTrace does not provide legal advice and does not determine infringement, validity, novelty, inventive step, or patentability.

## Reproducing

```bash
docker compose up -d postgres
docker compose run --rm api python -m evals.grounded_run

# with the configured local model (Ollama must be reachable)
docker compose run --rm api python -m evals.grounded_run --tier ollama
```
