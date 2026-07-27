# ClaimTrace grounded-generation evaluation (deterministic)

Generated 2026-07-26T23:24:48.146784+00:00.

> **This tier does not measure model quality.** The model is replaced by an in-process oracle that reads the evidence blocks it was given and cites the labelled claims that are present. What is measured is the pipeline: retrieval, the context budget, the evidence catalog, citation resolution, and the guardrails. Nothing here says anything about how well a language model answers patent questions.

## Configuration

| Setting | Value |
| --- | --- |
| Tier | `deterministic` |
| Provider | `oracle` |
| Model | `oracle-v1 (in-process, not a language model)` |
| Documents | 3 |
| Claims | 23 |
| Cases | 16 |
| Embedding model | `intfloat/multilingual-e5-small` |
| top_k | 6 |

## Metrics

| Metric | Value | What it means |
| --- | --- | --- |
| Structured-output success | 1.000 | the answer satisfied the JSON schema |
| Answerability accuracy | 1.000 | answered when the corpus answers, declined when it does not |
| Insufficient-evidence precision | 1.000 | of the questions declined, how many should have been |
| Insufficient-evidence recall | 1.000 | of the questions that should be declined, how many were |
| Evidence-ID validity | 1.000 | no answer was refused for naming an id the server never issued |
| **Citation resolution** | **1.000** | **every returned quote is the stored page text at its own locator** |
| Statement citation coverage | 1.000 | returned statements carrying a resolvable citation |
| Evidence selection precision | 1.000 | cited claims that were credited by the labels |
| Evidence selection recall | 0.917 | required claims that were cited |
| End-to-end success | 0.938 | all of the above, per case |
| Forbidden citations | 0 | citations outside a scoped question's document |
| Mean latency | 0.02 s | per question |

## Guardrails

6 of 6 hostile payloads were refused rather than served. Each is a complete, schema-shaped answer that breaks exactly one grounding rule, sent through the whole pipeline against a real question over the real corpus.

| Payload | Status | Error code | Refused |
| --- | --- | --- | --- |
| `fabricated_evidence_id` | 502 | `grounded_repair_failed` | yes |
| `forged_id_from_claim_text` | 502 | `grounded_repair_failed` | yes |
| `uncited_statement` | 422 | `llm_structured_output_validation_failed` | yes |
| `model_supplied_locator` | 422 | `llm_structured_output_validation_failed` | yes |
| `contradictory_insufficiency` | 502 | `grounded_repair_failed` | yes |
| `claim_number_as_evidence_id` | 502 | `grounded_repair_failed` | yes |


## Weak and failed cases

| Case | Category | Status | Expected | Cited | Why |
| --- | --- | --- | --- | --- | --- |
| `g01-single-storage` | single_evidence | 200 | collector#1 | collector#4, collector#5, collector#8 | cited none of the required claims |

## By category

| Category | Cases | End-to-end success |
| --- | --- | --- |
| conflicting | 1 | 1/1 |
| dependency | 2 | 2/2 |
| document_scoped | 2 | 2/2 |
| injection | 1 | 1/1 |
| multi_evidence | 3 | 3/3 |
| paraphrase | 2 | 2/2 |
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
