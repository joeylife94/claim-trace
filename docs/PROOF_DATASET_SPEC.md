# ClaimTrace Proof Dataset Spec v0.1

Status: IMPLEMENTED — FIREBAT E2E VALIDATION PENDING
Purpose: deterministic buyer-facing proof capture for Firebat Proof Factory

## 1. Objective

Create a reproducible populated application state that proves ClaimTrace can:

1. ingest synthetic patent-like PDFs,
2. parse claim structure,
3. index claims for hybrid retrieval,
4. return ranked claim results with source provenance,
5. generate evidence-grounded answers whose citations resolve to stored page text.

The proof dataset exercises the real application path. Direct database insertion is not used when the existing ingestion / parse / index / grounded-answer APIs can create the same state.

## 2. Source-of-truth dataset

Reuse the repository-owned synthetic grounded-generation corpus under:

```text
apps/api/evals/data/grounded_corpus.json
apps/api/evals/data/grounded_cases.json
```

The corpus is authored specifically for this repository and contains no copied third-party patent claim text.

### Public Proof documents

Use exactly these two ordinary documents for the public Proof dataset:

| Corpus id | Filename | Title | Claims | Public Proof |
| --- | --- | --- | ---: | --- |
| `collector` | `grounded-sensor-collector.pdf` | 센서 데이터 수집 장치 | 8 | YES |
| `thermal` | `grounded-battery-thermal.pdf` | 배터리 열 관리 장치 | 8 | YES |

### Excluded from public Proof

Do not include `adversarial` in the initial landing-page screenshot set.

Reason: it intentionally embeds prompt-injection payloads inside claim text. It remains useful as technical security / guardrail Proof, but it distracts from the primary buyer story in the public portfolio.

## 3. Seeding contract

The Proof seed uses the same application path already exercised by the grounded evaluation:

```text
synthetic claim corpus
      ↓
generate text-based PDF
      ↓
POST /api/v1/documents
      ↓
POST /api/v1/documents/{id}/claims/parse
      ↓
POST /api/v1/documents/{id}/claims/index
      ↓
search / grounded-answer UI
```

### Required properties

- deterministic
- idempotent for repeated Proof runs
- synthetic data only
- no customer / production data
- no direct DB insert
- public screenshots use the real `intfloat/multilingual-e5-small` retrieval model
- grounded generation uses a real local Ollama model in the Firebat Proof runtime

Repeated Proof runs reuse the same two filenames through the public application path. Duplicate filenames fail closed rather than silently contaminating the Proof state.

## 4. Expected populated Documents state

After seeding, `/documents` must show exactly the two public Proof documents:

1. `grounded-sensor-collector.pdf`
2. `grounded-battery-thermal.pdf`

Both must be successfully ingested and have extracted page text available.

Expected structure from the current corpus renderer:

- 8 claims per document
- 7 claims per rendered page maximum
- therefore 2 rendered pages per Proof document

The Documents screenshot proves ingestion and traceable source storage rather than merely showing an upload form.

## 5. Search Proof scenario

### S1 — Primary hybrid-search Proof

Query:

```text
오래된 데이터를 새로운 데이터로 덮어쓰는 기록 방법
```

Primary expected evidence:

- document: `collector`
- claim: 4
- meaning: circular recording overwrites the oldest measurement with a new measurement

Acceptable adjacent evidence:

- claim 5, because it depends on claim 4 and constrains storage capacity

Buyer-facing claim:

> Hybrid claim retrieval can surface a paraphrased requirement and preserve the source document / claim / page location needed to verify the match.

The public Search screenshot must show `multilingual-e5-small` and must not show `deterministic-hash`.

## 6. Grounded Answer Proof scenario

### G05 — Primary HERO Proof

Question:

```text
배터리 열 관리 장치에서 온도를 측정하는 수단과 냉매를 순환시키는 수단은 무엇인가?
```

The Firebat adapter scopes the question to:

```text
grounded-battery-thermal.pdf
```

and uses hybrid retrieval with six evidence candidates.

Required visible answer/evidence concepts:

- `열전대`
- `전동 펌프`
- Claim 6
- Claim 4

Expected answer meaning:

- temperature measurement is performed with the claimed temperature-measurement structure, including thermocouples
- coolant circulation is performed with the circulation structure, including an electric pump

Buyer-facing claim:

> ClaimTrace answers a document-scoped multi-evidence question through real hybrid retrieval and a real local model, while exposing resolvable claim citations for every supported statement.

### Why G05 replaced the former G04 HERO

The former storage-method / 512 MB scenario had succeeded in an earlier committed evaluation, but a stricter Firebat runtime reproduced two consecutive grounding-validator rejections. The API correctly returned 502 rather than promoting an invalid grounded answer.

G05 is a previously exercised real-model multi-evidence scenario and is now the public HERO candidate. Scenario-selection evidence is not a general model-quality benchmark.

## 7. Grounded runtime hardening

Firebat validation exposed two separate automation/runtime issues that are now treated as explicit contracts:

1. **Generation output headroom** — the Proof runtime keeps `GROUNDED_MAX_OUTPUT_TOKENS=1024`. A temporary 384-token bound truncated schema-constrained JSON and correctly failed generation.
2. **Long-running UI submit** — the Playwright click that submits the Grounded server action has an explicit long timeout rather than inheriting the generic 30-second action timeout.

The Grounded system prompt also instructs the local model to answer only the facts requested, avoid repeating evidence or reasoning, and use the minimum number of supported statements needed. This is ordinary grounded-answer behavior, not a Proof-only fake response path.

The Proof still fails closed when:

- the API returns an error,
- the Answer panel never appears,
- cited evidence is absent,
- the expected answer concepts are missing,
- an insufficient-evidence state is visible.

## 8. Scenes to promote

Initial public Proof promotion order:

1. **Grounded Answer HERO** — G05 result populated with citations
2. **Hybrid Search** — S1 result populated with source provenance
3. **Documents / Document Detail** — seeded document state with extracted pages / claim traceability
4. **System Overview** — API + PostgreSQL operational state and workflow map
5. **Local LLM** — supporting technical Proof only when it visibly reports the real Ollama provider/model

The Firebat Proof runtime starts the repository's optional Ollama service and uses `qwen2.5:1.5b` by default. The LLM screenshot must not be promoted if it shows `fake` / `fake-model`.

## 9. Capture behavior

The Playwright capture does not merely navigate to empty forms.

For result-state scenes it:

1. waits until the project runtime and migrations are ready,
2. runs the Proof seed,
3. navigates to the relevant page,
4. fills the fixed Proof query/question,
5. selects the required document/mode/result count,
6. submits the form,
7. waits for an expected result/evidence marker,
8. captures only after the result state is visible.

Current stable selectors are the existing field names and result headings. Add `data-testid` only if those contracts become unstable.

## 10. Framing

Current full-page captures may leave excessive empty space for sparse states.

After the populated-state Firebat run:

- evaluate `fullPage: false` for Search and Grounded if the populated image remains too tall,
- prefer a viewport that keeps input + result + provenance visible together,
- avoid cropping out citation/source-locator details,
- retain Overview as a broader workflow screenshot.

Final crop decisions are based on generated populated screenshots, not guessed in advance.

## 11. Integrity rules

A screenshot is promotable only when:

- the target repository commit is recorded,
- the Proof Factory commit is recorded,
- the target working tree is clean or the dirty state is explicitly reviewed,
- migrations are applied,
- API health passes,
- `/api/v1/documents` passes,
- exactly the two seed documents are present,
- repeated seed reuses the same documents,
- Search uses the real multilingual-E5 profile,
- result-state interaction succeeds,
- the Grounded HERO was generated by the configured real local Ollama provider,
- citations shown in the HERO scene resolve to persisted source text,
- no secret, customer data, or internal credential is visible.

The existing committed Ollama evaluation for `qwen2.5:1.5b` on the repository's small synthetic corpus reported 1.000 citation resolution and 3/3 multi-evidence case success. Those numbers justify using a previously exercised scenario; they are not a general model-quality benchmark and must not be marketed as one.

## 12. Implemented components

### ClaimTrace

```text
apps/api/evals/proof_seed.py
proof/firebat-start.sh
proof/README.md
docs/PROOF_DATASET_SPEC.md
```

`proof_seed.py` reuses the existing corpus and PDF builder and exercises upload -> parse -> index over the running API.

`firebat-start.sh` uses dedicated Firebat ports, starts PostgreSQL plus the optional Ollama Compose profile, waits for Ollama readiness, ensures the configured model is present in the persistent named volume, runs Alembic migrations, and starts API/Web with real retrieval and generation providers.

### Firebat Proof Factory

The `firebat-ops:agent/proof-factory` adapter:

- invokes the ClaimTrace project-owned runtime,
- gates on web/API/documents/LLM-status endpoints,
- invokes `evals.proof_seed`,
- captures populated Documents,
- executes the Search S1 interaction,
- executes the Grounded G05 interaction and waits for cited evidence,
- captures the real local-model diagnostics surface,
- writes normal provenance artifacts.

A guarded `proof-claim-trace-trial.sh` wrapper updates the ClaimTrace Proof branch only when its checkout is clean, runs the complete capture, and prints recent API/Web/Ollama diagnostics automatically if the trial fails.

## 13. v0.1 completion criteria

GitHub-side implementation is complete. v0.1 is runtime-complete when one Firebat command reproducibly produces a new artifact set where:

- Documents shows exactly the two seeded synthetic documents,
- repeated seed reports reuse rather than duplicate creation,
- Search S1 visibly returns the expected collector evidence under `multilingual-e5-small`,
- Grounded G05 visibly returns a supported answer with the required thermal evidence,
- Local LLM visibly reports the real Ollama provider/model,
- Overview remains healthy,
- no public screenshot exposes fake-model diagnostics,
- the run writes its normal `proof-manifest.json` provenance record.

The remaining action is the final Firebat E2E trial and visual review of the resulting populated screenshots.
