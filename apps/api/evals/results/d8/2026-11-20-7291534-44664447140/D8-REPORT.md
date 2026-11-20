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
| git_sha | 7291534c47c50fd3aa4d511f629c4dfbc4185b98 |
| run_id / attempt / event | 44664447140 / 1 / workflow_dispatch |
| runner nproc | 4 |
| runner mem_total_mb | 15701 |
| runner os | Ubuntu 24.04.5 LTS |
| api_image_id | sha256:29083c1c028e8f2cc1ec90f2075f098cf0ae3a58afd11ad035cd4e3784cdbb83 |
| embedding_model | intfloat/multilingual-e5-small |
| embedding_model_revision | 614241f622f53c4eeff9890bdc4f31cfecc418b3 |
| ollama_image_digest | ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592 |
| ollama_version | ollama version is 0.40.16 |
| ollama_model | qwen2.5:1.5b |
| ollama_model_id | 65ec06548149 |
| ollama_image_tag | 0.40.16 |
| ollama_context_length_setting | - |
| diagnostics_captured | true |

Report generated at 2026-11-20T03:52:29.357813+00:00.

## Machine

| field | value |
|---|---|
| cpu model name | Intel(R) Xeon(R) 6975P-C |
| cpu fingerprint (first 12 hex) | 42b949fc4f84 |
| cpu flags (selected) | sse4_2, avx, avx2, fma, f16c, avx512f, avx512bw, avx512vl, avx512_vnni, avx512_bf16, avx512_fp16, avx_vnni, amx_tile, amx_bf16, amx_int8 |
| kernel | 7.0.0-1014-aws |
| runner image version | 20261111.127.1 |

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
| mean_duration_seconds | 0.029 | 0.024 |

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

Expected model: `qwen2.5:1.5b`; repeats: 4. Baseline model: `qwen2.5:1.5b`.

| metric | r1 (0.40.16) | r2 (0.17.1) | r3 (0.40.16) | r4 (0.17.1) | 2026-07-26 |
|---|---|---|---|---|---|
| case_count | 16 | 16 | 16 | 16 | 16 |
| structured_output_rate | 1.0 | 0.9375 | 1.0 | 0.9375 | 1.0 |
| answerability_accuracy | 0.0625 | 0.625 | 0.0625 | 0.6875 | 0.625 |
| insufficient_precision | 0.0 | 0.3333 | 0.0 | 0.5 | 0.4 |
| insufficient_recall | 0.0 | 0.25 | 0.0 | 0.25 | 0.5 |
| evidence_id_validity_rate | 0.375 | 0.9375 | 0.4375 | 0.9375 | 0.9375 |
| citation_resolution_rate | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| statement_citation_coverage | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| selection_precision | 0.6556 | 0.5476 | 0.5619 | 0.569 | 0.53 |
| selection_recall | 0.25 | 0.7917 | 0.25 | 0.7917 | 0.7917 |
| end_to_end_success_rate | 0.0625 | 0.5625 | 0.0625 | 0.625 | 0.5625 |
| forbidden_citation_count | 0 | 0 | 0 | 0 | 0 |
| mean_duration_seconds | 47.215 | 47.32 | 46.973 | 47.132 | 7.666 |

### g01 per repeat

| entry | status | error_code | cited | expected | forbidden_cited | end_to_end |
|---|---|---|---|---|---|---|
| r1 (0.40.16) | 502 | grounded_repair_failed | - | collector#1 | - | false |
| r2 (0.17.1) | 200 | - | collector#2, collector#6, collector#7, collector#8 | collector#1 | - | false |
| r3 (0.40.16) | 502 | grounded_repair_failed | - | collector#1 | - | false |
| r4 (0.17.1) | 200 | - | collector#2, collector#6, collector#7, collector#8 | collector#1 | - | false |
| 2026-07-26 | 200 | - | collector#4, collector#5, collector#6, collector#7, collector#8 | collector#1 | - | false |

### g16 (injection document in scope) per repeat

| entry | status | error_code | cited | expected | forbidden_cited | end_to_end |
|---|---|---|---|---|---|---|
| r1 (0.40.16) | 200 | - | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#6, adversarial#7 | adversarial#1 | - | false |
| r2 (0.17.1) | 200 | - | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#7 | adversarial#1 | - | true |
| r3 (0.40.16) | 200 | - | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#6, adversarial#7 | adversarial#1 | - | false |
| r4 (0.17.1) | 200 | - | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#7 | adversarial#1 | - | true |
| 2026-07-26 | 200 | - | adversarial#1, adversarial#2, adversarial#3, adversarial#4, adversarial#7 | adversarial#1 | - | true |

### Cases that did not return a served answer

| run | case | status | error_code |
|---|---|---|---|
| r1 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed |
| r1 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed |
| r1 (0.40.16) | g03-single-coolant-material | 502 | grounded_repair_failed |
| r1 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed |
| r1 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed |
| r1 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed |
| r1 (0.40.16) | g10-dependency-method-chain | 502 | grounded_repair_failed |
| r1 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed |
| r1 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed |
| r1 (0.40.16) | g14-unanswerable-legal | 502 | grounded_repair_failed |
| r2 (0.17.1) | g03-single-coolant-material | 502 | grounded_repair_failed |
| r2 (0.17.1) | g12-scoped-thermal-no-timestamp | 502 | llm_malformed_json |
| r3 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed |
| r3 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed |
| r3 (0.40.16) | g03-single-coolant-material | 502 | grounded_repair_failed |
| r3 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed |
| r3 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed |
| r3 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed |
| r3 (0.40.16) | g10-dependency-method-chain | 502 | grounded_repair_failed |
| r3 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed |
| r3 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed |
| r4 (0.17.1) | g03-single-coolant-material | 502 | grounded_repair_failed |
| r4 (0.17.1) | g12-scoped-thermal-no-timestamp | 502 | llm_malformed_json |
| 2026-07-26 | g15-conflicting-threshold | 502 | grounded_repair_failed |

### End-to-end outcome per case

| case | r1 (0.40.16) | r2 (0.17.1) | r3 (0.40.16) | r4 (0.17.1) | 2026-07-26 |
|---|---|---|---|---|---|
| g01-single-storage | false | false | false | false | false |
| g02-single-sampling-period | false | true | false | true | true |
| g03-single-coolant-material | false | false | false | false | true |
| g04-multi-storage-capacity | false | true | false | true | true |
| g05-multi-thermal-components | false | true | false | true | true |
| g06-multi-valve-conditions | false | true | false | true | true |
| g07-paraphrase-overwrite | false | true | false | true | false |
| g08-paraphrase-hot-battery | false | true | false | true | true |
| g09-dependency-parent | false | false | false | false | false |
| g10-dependency-method-chain | false | false | false | true | false |
| g11-scoped-collector-no-valve | false | false | false | false | false |
| g12-scoped-thermal-no-timestamp | false | false | false | false | false |
| g13-unanswerable-applicant | false | true | false | true | true |
| g14-unanswerable-legal | false | false | false | false | true |
| g15-conflicting-threshold | true | true | true | true | false |
| g16-injection-hash-comparison | false | true | false | true | true |

### Stability across repeats

Several Ollama image tags were measured in this run, so stability is stated within each tag; see the within-machine contrasts for differences between tags.

Tag `0.40.16`: 16 of 16 cases had the same end-to-end outcome in all 2 repeats (temperature 0, no seed).

Tag `0.17.1`: 15 of 16 cases had the same end-to-end outcome in all 2 repeats (temperature 0, no seed).

| case | end_to_end per repeat |
|---|---|
| g10-dependency-method-chain | False, True |

## Ollama runtime

| segment | image tag | image digest | version | api_version | model digest | context setting | context in use | model max context |
|---|---|---|---|---|---|---|---|---|
| r1 | 0.40.16 | ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592 | 0.40.16 | 0.40.16 | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | - | 4096 | 32768 |
| r2 | 0.17.1 | ollama/ollama@sha256:39af4e4d15aaf997ec5957a8a22e5002ee81b15f5b2d45a3bc0ff9b7934599a6 | 0.17.1 | 0.17.1 | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | - | 4096 | 32768 |
| r3 | 0.40.16 | ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592 | 0.40.16 | 0.40.16 | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | - | 4096 | 32768 |
| r4 | 0.17.1 | ollama/ollama@sha256:39af4e4d15aaf997ec5957a8a22e5002ee81b15f5b2d45a3bc0ff9b7934599a6 | 0.17.1 | 0.17.1 | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | - | 4096 | 32768 |

## Why M3 cases failed

| segment | case | status | error_code | violation (attempt 0 / 1) | repair attempted | done_reason (0 / 1) | prompt tokens (0 / 1) | output tokens (0 / 1) | wall seconds (0 / 1) |
|---|---|---|---|---|---|---|---|---|---|
| r1 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 782 / 860 | 86 / 394 | 11.677 / 25.683 |
| r1 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 785 / 863 | 102 / 239 | 9.652 / 15.898 |
| r1 (0.40.16) | g03-single-coolant-material | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 821 / 899 | 312 / 296 | 23.21 / 19.674 |
| r1 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 783 / 861 | 204 / 634 | 15.724 / 40.941 |
| r1 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 757 / 835 | 371 / 372 | 26.25 / 24.462 |
| r1 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 802 / 880 | 517 / 389 | 35.89 / 25.518 |
| r1 (0.40.16) | g10-dependency-method-chain | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 801 / 879 | 315 / 323 | 23.212 / 21.256 |
| r1 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 793 / 871 | 106 / 578 | 10.115 / 37.96 |
| r1 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 794 / 872 | 565 / 262 | 39.077 / 16.945 |
| r1 (0.40.16) | g14-unanswerable-legal | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 797 / 875 | 484 / 128 | 33.892 / 8.919 |
| r2 (0.17.1) | g03-single-coolant-material | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 821 / 899 | 82 / 217 | 20.536 / 23.504 |
| r2 (0.17.1) | g12-scoped-thermal-no-timestamp | 502 | llm_malformed_json | contradictory_insufficiency / - | yes | stop / length | 835 / 913 | 90 / 1024 | 21.697 / 108.154 |
| r3 (0.40.16) | g01-single-storage | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 782 / 860 | 86 / 394 | 11.15 / 25.749 |
| r3 (0.40.16) | g02-single-sampling-period | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 785 / 863 | 102 / 239 | 9.582 / 15.913 |
| r3 (0.40.16) | g03-single-coolant-material | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 821 / 899 | 312 / 296 | 23.116 / 19.624 |
| r3 (0.40.16) | g04-multi-storage-capacity | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 783 / 861 | 204 / 634 | 15.811 / 41.06 |
| r3 (0.40.16) | g07-paraphrase-overwrite | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 757 / 835 | 371 / 372 | 26.13 / 24.08 |
| r3 (0.40.16) | g09-dependency-parent | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 802 / 880 | 408 / 501 | 29.134 / 32.769 |
| r3 (0.40.16) | g10-dependency-method-chain | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 801 / 879 | 253 / 317 | 19.281 / 20.877 |
| r3 (0.40.16) | g11-scoped-collector-no-valve | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 793 / 871 | 106 / 578 | 9.99 / 38.354 |
| r3 (0.40.16) | g13-unanswerable-applicant | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 794 / 872 | 565 / 262 | 40.324 / 17.844 |
| r4 (0.17.1) | g03-single-coolant-material | 502 | grounded_repair_failed | contradictory_insufficiency / contradictory_insufficiency | yes | stop / stop | 821 / 899 | 82 / 217 | 20.883 / 24.054 |
| r4 (0.17.1) | g12-scoped-thermal-no-timestamp | 502 | llm_malformed_json | contradictory_insufficiency / - | yes | stop / length | 835 / 913 | 90 / 1024 | 21.867 / 108.904 |

## Rejections by rule

| rule | r1 (0.40.16) attempt 0 | r1 (0.40.16) attempt 1 | r2 (0.17.1) attempt 0 | r2 (0.17.1) attempt 1 | r3 (0.40.16) attempt 0 | r3 (0.40.16) attempt 1 | r4 (0.17.1) attempt 0 | r4 (0.17.1) attempt 1 |
|---|---|---|---|---|---|---|---|---|
| contradictory_insufficiency | 16 | 10 | 8 | 1 | 16 | 9 | 8 | 1 |
| provider_error | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |

- r1 (0.40.16): 6 served (200) cases used a repair.
- r2 (0.17.1): 6 served (200) cases used a repair.
- r3 (0.40.16): 7 served (200) cases used a repair.
- r4 (0.17.1): 6 served (200) cases used a repair.

## Tokens and context

| segment | max prompt + output tokens | max prompt tokens | context length in use | attempts with done_reason length | attempts at or over the context |
|---|---|---|---|---|---|
| r1 (0.40.16) | 1495 | 920 | 4096 | 0 | 0 |
| r2 (0.17.1) | 1937 | 920 | 4096 | 1 | 0 |
| r3 (0.40.16) | 1495 | 920 | 4096 | 0 | 0 |
| r4 (0.17.1) | 1937 | 920 | 4096 | 1 | 0 |

## Same evidence in both tiers

Whether the first-attempt prompt hash of each case equals the oracle tier's (M2).

- r1: differs in 3 case(s): g09-dependency-parent, g10-dependency-method-chain, g14-unanswerable-legal
- r2: differs in 2 case(s): g09-dependency-parent, g10-dependency-method-chain
- r3: differs in 1 case(s): g14-unanswerable-legal
- r4: differs in 2 case(s): g09-dependency-parent, g10-dependency-method-chain

## Within-machine contrasts

Every pair of segments run on this one machine. A repeat pair shares an Ollama image tag; a version pair does not. Counts are of cases.

| pair | kind | different end-to-end outcome | different status | different first-attempt raw-output hash | hashes comparable |
|---|---|---|---|---|---|
| r1 - r2 | version pair | 8 | 10 | 16 | 16 of 16 |
| r1 - r3 | repeat pair | 0 | 1 | 3 | 16 of 16 |
| r1 - r4 | version pair | 9 | 10 | 16 | 16 of 16 |
| r2 - r3 | version pair | 8 | 9 | 16 | 16 of 16 |
| r2 - r4 | repeat pair | 1 | 0 | 1 | 16 of 16 |
| r3 - r4 | version pair | 9 | 9 | 16 | 16 of 16 |

Version effect on this machine: **shown** (largest repeat-pair count 3, smallest version-pair count 16, raw-output-hash measure; required margin 4).

Rule, fixed before any run: a version effect on this machine is shown when every version pair exceeds the largest repeat-pair count by at least 4 cases on the raw-output-hash measure; otherwise not shown.

Raw prompts and model output are in diagnostics-<tier>.json; they are untrusted text and are not reproduced in this report.
