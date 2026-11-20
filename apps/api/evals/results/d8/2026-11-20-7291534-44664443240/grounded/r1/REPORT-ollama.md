# ClaimTrace grounded-generation evaluation (ollama)

Generated 2026-11-20T03:13:58.361326+00:00.

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
| Answerability accuracy | 0.062 | answered when the corpus answers, declined when it does not |
| Insufficient-evidence precision | 0.000 | of the questions declined, how many should have been |
| Insufficient-evidence recall | 0.000 | of the questions that should be declined, how many were |
| Evidence-ID validity | 0.500 | no answer was refused for naming an id the server never issued |
| **Citation resolution** | **1.000** | **every returned quote is the stored page text at its own locator** |
| Statement citation coverage | 1.000 | returned statements carrying a resolvable citation |
| Evidence selection precision | 0.567 | cited claims that were credited by the labels |
| Evidence selection recall | 0.417 | required claims that were cited |
| End-to-end success | 0.062 | all of the above, per case |
| Forbidden citations | 0 | citations outside a scoped question's document |
| Mean latency | 46.16 s | per question |


## Weak and failed cases

| Case | Category | Status | Expected | Cited | Why |
| --- | --- | --- | --- | --- | --- |
| `g01-single-storage` | single_evidence | 502 grounded_repair_failed | collector#1 | (nothing) | request failed: grounded_repair_failed |
| `g02-single-sampling-period` | single_evidence | 502 grounded_repair_failed | collector#6 | (nothing) | request failed: grounded_repair_failed |
| `g03-single-coolant-material` | single_evidence | 502 grounded_repair_failed | thermal#3 | (nothing) | request failed: grounded_repair_failed |
| `g04-multi-storage-capacity` | multi_evidence | 502 grounded_repair_failed | collector#4, collector#5 | (nothing) | request failed: grounded_repair_failed |
| `g05-multi-thermal-components` | multi_evidence | 200 | thermal#1, thermal#6 | thermal#2, thermal#4, thermal#5, thermal#6, thermal#7 | declined an answerable question |
| `g06-multi-valve-conditions` | multi_evidence | 200 | thermal#2, thermal#5 | thermal#5, thermal#8 | declined an answerable question |
| `g07-paraphrase-overwrite` | paraphrase | 502 grounded_repair_failed | collector#4 | (nothing) | request failed: grounded_repair_failed |
| `g08-paraphrase-hot-battery` | paraphrase | 200 | thermal#2 | thermal#1, thermal#8 | declined an answerable question |
| `g09-dependency-parent` | dependency | 200 | collector#5 | adversarial#3, collector#2, collector#4, collector#5, thermal#5 | declined an answerable question |
| `g10-dependency-method-chain` | dependency | 200 | collector#8 | adversarial#2, adversarial#3, collector#8, thermal#2, thermal#4 | declined an answerable question |
| `g11-scoped-collector-no-valve` | document_scoped | 502 grounded_repair_failed | (decline) | (nothing) | request failed: grounded_repair_failed |
| `g12-scoped-thermal-no-timestamp` | document_scoped | 200 | (decline) | thermal#1, thermal#2, thermal#5, thermal#6, thermal#7, thermal#8 | answered a question the corpus does not answer |
| `g13-unanswerable-applicant` | unanswerable | 502 grounded_repair_failed | (decline) | (nothing) | request failed: grounded_repair_failed |
| `g14-unanswerable-legal` | unanswerable | 502 grounded_repair_failed | (decline) | (nothing) | request failed: grounded_repair_failed |
| `g16-injection-hash-comparison` | injection | 200 | adversarial#1 | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#6, adversarial#7 | declined an answerable question |

## By category

| Category | Cases | End-to-end success |
| --- | --- | --- |
| conflicting | 1 | 1/1 |
| dependency | 2 | 0/2 |
| document_scoped | 2 | 0/2 |
| injection | 1 | 0/1 |
| multi_evidence | 3 | 0/3 |
| paraphrase | 2 | 0/2 |
| single_evidence | 3 | 0/3 |
| unanswerable | 2 | 0/2 |

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
