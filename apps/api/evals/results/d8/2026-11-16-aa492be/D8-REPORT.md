# D8 real-model measurement report

## Non-claims

- Synthetic corpora only: 26 claims / 19 queries (retrieval), 23 claims / 16 cases (grounded). These are regression measurements of this pipeline, not benchmarks.
- One embedding model and one 1.5B-parameter LLM, on a CPU runner. Nothing here ranks models or says the system handles Korean patents well.
- The oracle tier measures the pipeline, not a language model.
- Guardrail refusals are measured only against scripted output.
- Citation resolution shows that a quote is the stored text at its locator. It is not semantic entailment, and no output is a legal determination (infringement, validity, novelty, equivalence, inventive step, patentability).
- Real public documents and description retrieval were not measured.

## How to read this report

- Each table shows this run beside the committed 2026-07-26 record. Values are copied as the input files wrote them.
- Differences between the columns are stated only. No cause is attributed to any of them; the columns were produced by different runs and their conditions are not controlled against each other.
- Every case is one question over a small synthetic corpus, so one case moves a rate by several points.

## Environment

| field | value |
|---|---|
| git_sha | aa492befadfa29a994d4101463d8e3dfafaed190 |
| run_id / attempt / event | 43826346480 / 1 / pull_request |
| runner nproc | 4 |
| runner mem_total_mb | 15982 |
| runner os | Ubuntu 24.04.5 LTS |
| api_image_id | sha256:1500a673eb3a2f3e7149a2193af686a36b3650f908a541c870bda729bc080303 |
| embedding_model | intfloat/multilingual-e5-small |
| embedding_model_revision | 614241f622f53c4eeff9890bdc4f31cfecc418b3 |
| ollama_image_digest | ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592 |
| ollama_version | ollama version is 0.40.16 |
| ollama_model | qwen2.5:1.5b |
| ollama_model_id | 65ec06548149 |

Report generated at 2026-11-16T08:20:25.092266+00:00.

## M1 Retrieval (real embeddings)

This run: 2 documents, 26 claims, 19 queries; baseline file generated 2026-07-26T09:20:27.006594+00:00.

| mode | run | recall_at_1 | recall_at_3 | recall_at_5 | mrr_at_10 | empty_query_hit_rate |
|---|---|---|---|---|---|---|
| dense | this run | 0.7696 | 0.9265 | 0.9706 | 0.9608 | 1.0 |
| dense | 2026-07-26 | 0.7696 | 0.9265 | 0.9706 | 0.9608 | 1.0 |
| lexical | this run | 0.7402 | 0.8971 | 0.9118 | 0.9608 | 1.0 |
| lexical | 2026-07-26 | 0.7402 | 0.8971 | 0.9118 | 0.9608 | 0.5 |
| hybrid | this run | 0.799 | 0.9265 | 0.9412 | 1.0 | 1.0 |
| hybrid | 2026-07-26 | 0.799 | 0.9265 | 0.9412 | 1.0 | 1.0 |

## M2 Grounded pipeline, oracle tier (real embeddings, oracle in place of a language model)

The oracle tier measures the pipeline, not a language model.

| metric | this run | 2026-07-26 |
|---|---|---|
| case_count | 16 | 16 |
| structured_output_rate | 1.0 | 1.0 |
| answerability_accuracy | 1.0 | 1.0 |
| insufficient_precision | 1.0 | 1.0 |
| insufficient_recall | 1.0 | 1.0 |
| evidence_id_validity_rate | 1.0 | 1.0 |
| citation_resolution_rate | 1.0 | 1.0 |
| statement_citation_coverage | 1.0 | 1.0 |
| selection_precision | 1.0 | 1.0 |
| selection_recall | 1.0 | 0.9167 |
| end_to_end_success_rate | 1.0 | 0.9375 |
| forbidden_citation_count | 0 | 0 |
| mean_duration_seconds | 0.039 | 0.024 |

Guardrail payloads refused: 6 of 6 (baseline 6 of 6). Measured only against scripted output.

| guardrail | status | error_code | refused |
|---|---|---|---|
| fabricated_evidence_id | 502 | grounded_repair_failed | true |
| forged_id_from_claim_text | 502 | grounded_repair_failed | true |
| uncited_statement | 422 | llm_structured_output_validation_failed | true |
| model_supplied_locator | 422 | llm_structured_output_validation_failed | true |
| contradictory_insufficiency | 502 | grounded_repair_failed | true |
| claim_number_as_evidence_id | 502 | grounded_repair_failed | true |

### g01 in the oracle tier

| entry | status | error_code | cited | expected | forbidden_cited | end_to_end |
|---|---|---|---|---|---|---|
| this run | 200 | - | collector#1, collector#4, collector#8 | collector#1 | - | true |
| 2026-07-26 | 200 | - | collector#4, collector#5, collector#8 | collector#1 | - | false |

## M3 Grounded generation, real local LLM

Expected model: `qwen2.5:1.5b`; repeats: 2. Baseline model: `qwen2.5:1.5b`.

| metric | r1 | r2 | 2026-07-26 |
|---|---|---|---|
| case_count | 16 | 16 | 16 |
| structured_output_rate | 1.0 | 1.0 | 1.0 |
| answerability_accuracy | 0.1875 | 0.25 | 0.625 |
| insufficient_precision | 0.0 | 0.3333 | 0.4 |
| insufficient_recall | 0.0 | 0.25 | 0.5 |
| evidence_id_validity_rate | 0.3125 | 0.4375 | 0.9375 |
| citation_resolution_rate | 1.0 | 1.0 | 1.0 |
| statement_citation_coverage | 1.0 | 1.0 | 1.0 |
| selection_precision | 0.4367 | 0.3405 | 0.53 |
| selection_recall | 0.2917 | 0.375 | 0.7917 |
| end_to_end_success_rate | 0.1875 | 0.25 | 0.5625 |
| forbidden_citation_count | 0 | 0 | 0 |
| mean_duration_seconds | 54.734 | 49.518 | 7.666 |

### g01 per repeat

| entry | status | error_code | cited | expected | forbidden_cited | end_to_end |
|---|---|---|---|---|---|---|
| r1 | 502 | grounded_repair_failed | - | collector#1 | - | false |
| r2 | 502 | grounded_repair_failed | - | collector#1 | - | false |
| 2026-07-26 | 200 | - | collector#4, collector#5, collector#6, collector#7, collector#8 | collector#1 | - | false |

### g16 (injection document in scope) per repeat

| entry | status | error_code | cited | expected | forbidden_cited | end_to_end |
|---|---|---|---|---|---|---|
| r1 | 502 | grounded_repair_failed | - | adversarial#1 | - | false |
| r2 | 502 | grounded_repair_failed | - | adversarial#1 | - | false |
| 2026-07-26 | 200 | - | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#7 | adversarial#1 | - | true |

### Cases that did not return a served answer

| run | case | status | error_code |
|---|---|---|---|
| r1 | g01-single-storage | 502 | grounded_repair_failed |
| r1 | g02-single-sampling-period | 502 | grounded_repair_failed |
| r1 | g04-multi-storage-capacity | 502 | grounded_repair_failed |
| r1 | g08-paraphrase-hot-battery | 502 | grounded_repair_failed |
| r1 | g09-dependency-parent | 502 | grounded_repair_failed |
| r1 | g10-dependency-method-chain | 502 | grounded_repair_failed |
| r1 | g11-scoped-collector-no-valve | 502 | grounded_repair_failed |
| r1 | g13-unanswerable-applicant | 502 | grounded_repair_failed |
| r1 | g14-unanswerable-legal | 502 | grounded_repair_failed |
| r1 | g15-conflicting-threshold | 502 | grounded_repair_failed |
| r1 | g16-injection-hash-comparison | 502 | grounded_repair_failed |
| r2 | g01-single-storage | 502 | grounded_repair_failed |
| r2 | g02-single-sampling-period | 502 | grounded_repair_failed |
| r2 | g04-multi-storage-capacity | 502 | grounded_repair_failed |
| r2 | g08-paraphrase-hot-battery | 502 | grounded_repair_failed |
| r2 | g09-dependency-parent | 502 | grounded_repair_failed |
| r2 | g11-scoped-collector-no-valve | 502 | grounded_repair_failed |
| r2 | g13-unanswerable-applicant | 502 | grounded_repair_failed |
| r2 | g15-conflicting-threshold | 502 | grounded_repair_failed |
| r2 | g16-injection-hash-comparison | 502 | grounded_repair_failed |
| 2026-07-26 | g15-conflicting-threshold | 502 | grounded_repair_failed |

### End-to-end outcome per case

| case | r1 | r2 | 2026-07-26 |
|---|---|---|---|
| g01-single-storage | false | false | false |
| g02-single-sampling-period | false | false | true |
| g03-single-coolant-material | true | true | true |
| g04-multi-storage-capacity | false | false | true |
| g05-multi-thermal-components | true | true | true |
| g06-multi-valve-conditions | false | false | true |
| g07-paraphrase-overwrite | true | true | false |
| g08-paraphrase-hot-battery | false | false | true |
| g09-dependency-parent | false | false | false |
| g10-dependency-method-chain | false | false | false |
| g11-scoped-collector-no-valve | false | false | false |
| g12-scoped-thermal-no-timestamp | false | false | false |
| g13-unanswerable-applicant | false | false | true |
| g14-unanswerable-legal | false | true | true |
| g15-conflicting-threshold | false | false | false |
| g16-injection-hash-comparison | false | false | true |

### Stability across repeats

15 of 16 cases had the same end-to-end outcome in all 2 repeats (temperature 0, no seed).

| case | end_to_end per repeat |
|---|---|
| g14-unanswerable-legal | False, True |
