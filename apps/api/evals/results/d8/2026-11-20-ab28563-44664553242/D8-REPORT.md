# D8 real-model measurement report

## Non-claims

- Synthetic corpora only: 26 claims / 19 queries (retrieval), 23 claims / 16 cases (grounded). These are regression measurements of this pipeline, not benchmarks.
- One embedding model and one local LLM (none: the LLM tier was not run), on a CPU runner. Nothing here ranks models or says the system handles Korean patents well.
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
| git_sha | ab285631a53342bc897d2d046cc562dde6945694 |
| run_id / attempt / event | 44664553242 / 1 / workflow_dispatch |
| runner nproc | 4 |
| runner mem_total_mb | 15701 |
| runner os | Ubuntu 24.04.5 LTS |
| api_image_id | sha256:54cb857f9afd933ed847fd5123470b90b302c0580ea42774a128870b082bfbaa |
| embedding_model | intfloat/multilingual-e5-small |
| embedding_model_revision | 614241f622f53c4eeff9890bdc4f31cfecc418b3 |
| ollama_image_digest | - |
| ollama_version | - |
| ollama_model | - |
| ollama_model_id | - |
| ollama_image_tag | - |
| ollama_context_length_setting | - |
| diagnostics_captured | true |

Report generated at 2026-11-20T03:00:19.948043+00:00.

## Machine

| field | value |
|---|---|
| cpu model name | Intel(R) Xeon(R) 6975P-C |
| cpu fingerprint (first 12 hex) | 42b949fc4f84 |
| cpu flags (selected) | sse4_2, avx, avx2, fma, f16c, avx512f, avx512bw, avx512vl, avx512_vnni, avx512_bf16, avx512_fp16, avx_vnni, amx_tile, amx_bf16, amx_int8 |
| kernel | 7.0.0-1014-aws |
| runner image version | 20261116.133.1 |

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
| mean_duration_seconds | 0.025 | 0.024 |

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

The LLM tier was not run (expected repeats: 0).
