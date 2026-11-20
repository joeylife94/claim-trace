# D8 real-model measurement report

## Non-claims

- Synthetic corpora only: 26 claims / 19 queries (retrieval), 23 claims / 16 cases (grounded). These are regression measurements of this pipeline, not benchmarks.
- One embedding model and one local LLM (`qwen2.5:1.5b`), on a CPU runner. Nothing here ranks models or says the system handles Korean patents well.
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
| git_sha | 01d66d41d3d6d02348f374fab44950d69526c366 |
| run_id / attempt / event | 44666568538 / 1 / workflow_dispatch |
| runner nproc | 4 |
| runner mem_total_mb | 15983 |
| runner os | Ubuntu 24.04.5 LTS |
| api_image_id | sha256:ec23380eb3acc98133bead1d56c6e948f7a86a256c1ff2e25af423821cd128ad |
| embedding_model | intfloat/multilingual-e5-small |
| embedding_model_revision | 614241f622f53c4eeff9890bdc4f31cfecc418b3 |
| ollama_image_digest | ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592 |
| ollama_version | ollama version is 0.40.16 |
| ollama_model | qwen2.5:1.5b |
| ollama_model_id | 65ec06548149 |
| ollama_image_tag | 0.40.16 |
| ollama_context_length_setting | - |
| diagnostics_captured | true |

Report generated at 2026-11-20T03:30:23.559026+00:00.

## Machine

| field | value |
|---|---|
| cpu model name | AMD EPYC 9V45 96-Core Processor |
| cpu fingerprint (first 12 hex) | 6de3b935938b |
| cpu flags (selected) | sse4_2, avx, avx2, fma, f16c, avx512f, avx512bw, avx512vl, avx512_vnni, avx512_bf16, avx_vnni |
| kernel | 7.0.0-1017-azure |
| runner image version | 20261111.370.1 |

## M1 Retrieval (real embeddings)

This run: 2 documents, 26 claims, 19 queries; baseline file generated 2026-07-26T09:20:27.006594+00:00.

| mode | run | recall_at_1 | recall_at_3 | recall_at_5 | mrr_at_10 | empty_query_hit_rate |
|---|---|---|---|---|---|---|
| dense | this run | 0.7696 | 0.9265 | 0.9706 | 0.9608 | 1.0 |
| dense | 2026-07-26 | 0.7696 | 0.9265 | 0.9706 | 0.9608 | 1.0 |
| lexical | this run | 0.7402 | 0.8971 | 0.9118 | 0.9608 | 0.5 |
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
| selection_recall | 0.9167 | 0.9167 |
| end_to_end_success_rate | 0.9375 | 0.9375 |
| forbidden_citation_count | 0 | 0 |
| mean_duration_seconds | 0.028 | 0.024 |

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
| this run | 200 | - | collector#4, collector#5, collector#8 | collector#1 | - | false |
| 2026-07-26 | 200 | - | collector#4, collector#5, collector#8 | collector#1 | - | false |

## M3 Grounded generation, real local LLM

Expected model: `qwen2.5:1.5b`; repeats: 2. Baseline model: `qwen2.5:1.5b`.

| metric | r1 (0.40.16) | r2 (0.40.16) | 2026-07-26 |
|---|---|---|---|
| case_count | 16 | 16 | 16 |
| structured_output_rate | 0.9375 | 0.9375 | 1.0 |
| answerability_accuracy | 0.125 | 0.125 | 0.625 |
| insufficient_precision | 0.0 | 0.0 | 0.4 |
| insufficient_recall | 0.0 | 0.0 | 0.5 |
| evidence_id_validity_rate | 0.375 | 0.375 | 0.9375 |
| citation_resolution_rate | 1.0 | 1.0 | 1.0 |
| statement_citation_coverage | 1.0 | 1.0 | 1.0 |
| selection_precision | 0.47 | 0.47 | 0.53 |
| selection_recall | 0.2917 | 0.2917 | 0.7917 |
| end_to_end_success_rate | 0.125 | 0.125 | 0.5625 |
| forbidden_citation_count | 0 | 0 | 0 |
| mean_duration_seconds | 21.059 | 21.072 | 7.666 |

### g01 per repeat

| entry | status | error_code | cited | expected | forbidden_cited | end_to_end |
|---|---|---|---|---|---|---|
| r1 (0.40.16) | 502 | grounded_repair_failed | - | collector#1 | - | false |
| r2 (0.40.16) | 502 | grounded_repair_failed | - | collector#1 | - | false |
| 2026-07-26 | 200 | - | collector#4, collector#5, collector#6, collector#7, collector#8 | collector#1 | - | false |

### g16 (injection document in scope) per repeat

| entry | status | error_code | cited | expected | forbidden_cited | end_to_end |
|---|---|---|---|---|---|---|
| r1 (0.40.16) | 502 | grounded_repair_failed | - | adversarial#1 | - | false |
| r2 (0.40.16) | 502 | grounded_repair_failed | - | adversarial#1 | - | false |
| 2026-07-26 | 200 | - | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#7 | adversarial#1 | - | true |

### Cases that did not return a served answer

| run | case | status | error_code |
|---|---|---|---|
| r1 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed |
| r1 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed |
| r1 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed |
| r1 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed |
| r1 (0.40.16) | g08-paraphrase-hot-battery | 502 | llm_malformed_json |
| r1 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed |
| r1 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed |
| r1 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed |
| r1 (0.40.16) | g14-unanswerable-legal | 502 | grounded_repair_failed |
| r1 (0.40.16) | g15-conflicting-threshold | 502 | grounded_repair_failed |
| r1 (0.40.16) | g16-injection-hash-comparison | 502 | grounded_repair_failed |
| r2 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed |
| r2 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed |
| r2 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed |
| r2 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed |
| r2 (0.40.16) | g08-paraphrase-hot-battery | 502 | llm_malformed_json |
| r2 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed |
| r2 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed |
| r2 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed |
| r2 (0.40.16) | g14-unanswerable-legal | 502 | grounded_repair_failed |
| r2 (0.40.16) | g15-conflicting-threshold | 502 | grounded_repair_failed |
| r2 (0.40.16) | g16-injection-hash-comparison | 502 | grounded_repair_failed |
| 2026-07-26 | g15-conflicting-threshold | 502 | grounded_repair_failed |

### End-to-end outcome per case

| case | r1 (0.40.16) | r2 (0.40.16) | 2026-07-26 |
|---|---|---|---|
| g01-single-storage | false | false | false |
| g02-single-sampling-period | false | false | true |
| g03-single-coolant-material | true | true | true |
| g04-multi-storage-capacity | false | false | true |
| g05-multi-thermal-components | true | true | true |
| g06-multi-valve-conditions | false | false | true |
| g07-paraphrase-overwrite | false | false | false |
| g08-paraphrase-hot-battery | false | false | true |
| g09-dependency-parent | false | false | false |
| g10-dependency-method-chain | false | false | false |
| g11-scoped-collector-no-valve | false | false | false |
| g12-scoped-thermal-no-timestamp | false | false | false |
| g13-unanswerable-applicant | false | false | true |
| g14-unanswerable-legal | false | false | true |
| g15-conflicting-threshold | false | false | false |
| g16-injection-hash-comparison | false | false | true |

### Stability across repeats

16 of 16 cases had the same end-to-end outcome in all 2 repeats (temperature 0, no seed).

## Ollama runtime

| segment | image tag | image digest | version | api_version | model digest | context setting | context in use | model max context |
|---|---|---|---|---|---|---|---|---|
| r1 | 0.40.16 | ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592 | 0.40.16 | 0.40.16 | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | - | 4096 | 32768 |
| r2 | 0.40.16 | ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592 | 0.40.16 | 0.40.16 | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | - | 4096 | 32768 |

## Why M3 cases failed

| segment | case | status | error_code | violation (attempt 0 / 1) | repair attempted | done_reason (0 / 1) | prompt tokens (0 / 1) | output tokens (0 / 1) | wall seconds (0 / 1) |
|---|---|---|---|---|---|---|---|---|---|
| r1 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 770 / 848 | 95 / 288 | 8.013 / 9.061 |
| r1 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 813 / 891 | 234 / 298 | 9.999 / 9.255 |
| r1 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 783 / 861 | 202 / 185 | 8.78 / 5.891 |
| r1 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 775 / 853 | 280 / 183 | 10.889 / 5.902 |
| r1 (0.40.16) | g08-paraphrase-hot-battery | 502 | llm_malformed_json | contradictory_insufficiency / - | yes | stop / length | 822 / 900 | 110 / 1024 | 6.379 / 30.676 |
| r1 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 790 / 868 | 257 / 265 | 10.137 / 7.984 |
| r1 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 793 / 871 | 105 / 635 | 6.006 / 19.026 |
| r1 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 794 / 872 | 510 / 215 | 17.515 / 6.666 |
| r1 (0.40.16) | g14-unanswerable-legal | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 781 / 859 | 142 / 128 | 7.121 / 4.204 |
| r1 (0.40.16) | g15-conflicting-threshold | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 840 / 918 | 301 / 441 | 11.695 / 13.172 |
| r1 (0.40.16) | g16-injection-hash-comparison | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 789 / 867 | 347 / 347 | 12.823 / 11.005 |
| r2 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 770 / 848 | 95 / 288 | 7.936 / 8.761 |
| r2 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 813 / 891 | 234 / 298 | 9.798 / 9.234 |
| r2 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 783 / 861 | 202 / 185 | 8.661 / 5.867 |
| r2 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 775 / 853 | 280 / 183 | 10.921 / 5.858 |
| r2 (0.40.16) | g08-paraphrase-hot-battery | 502 | llm_malformed_json | contradictory_insufficiency / - | yes | stop / length | 822 / 900 | 110 / 1024 | 6.324 / 31.008 |
| r2 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 790 / 868 | 257 / 265 | 10.181 / 8.338 |
| r2 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 793 / 871 | 105 / 635 | 6.169 / 18.92 |
| r2 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 794 / 872 | 510 / 215 | 17.564 / 6.689 |
| r2 (0.40.16) | g14-unanswerable-legal | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 781 / 859 | 142 / 128 | 7.177 / 4.238 |
| r2 (0.40.16) | g15-conflicting-threshold | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 840 / 918 | 301 / 441 | 11.819 / 13.432 |
| r2 (0.40.16) | g16-injection-hash-comparison | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 789 / 867 | 347 / 347 | 12.716 / 10.648 |

## Rejections by rule

| rule | r1 (0.40.16) attempt 0 | r1 (0.40.16) attempt 1 | r2 (0.40.16) attempt 0 | r2 (0.40.16) attempt 1 |
|---|---|---|---|---|
| contradictory_insufficiency | 16 | 10 | 16 | 10 |
| provider_error | 0 | 1 | 0 | 1 |

- r1 (0.40.16): 5 served (200) cases used a repair.
- r2 (0.40.16): 5 served (200) cases used a repair.

## Tokens and context

| segment | max prompt + output tokens | max prompt tokens | context length in use | attempts with done_reason length | attempts at or over the context |
|---|---|---|---|---|---|
| r1 (0.40.16) | 1924 | 920 | 4096 | 1 | 0 |
| r2 (0.40.16) | 1924 | 920 | 4096 | 1 | 0 |

## Same evidence in both tiers

Whether the first-attempt prompt hash of each case equals the oracle tier's (M2).

- r1: identical in every compared case
- r2: identical in every compared case

## Within-machine contrasts

Every pair of segments run on this one machine. A repeat pair shares an Ollama image tag; a version pair does not. Counts are of cases.

| pair | kind | different end-to-end outcome | different status | different first-attempt raw-output hash | hashes comparable |
|---|---|---|---|---|---|
| r1 - r2 | repeat pair | 0 | 0 | 0 | 16 of 16 |

Version effect: not assessed (this run has only one Ollama image tag).

Raw prompts and model output are in diagnostics-<tier>.json; they are untrusted text and are not reproduced in this report.
