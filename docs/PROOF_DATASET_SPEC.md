# ClaimTrace Proof Dataset Spec v0.1

Status: DRAFT
Purpose: deterministic buyer-facing proof capture for Firebat Proof Factory

## 1. Objective

Create a reproducible populated application state that proves ClaimTrace can:

1. ingest synthetic patent-like PDFs,
2. parse claim structure,
3. index claims for hybrid retrieval,
4. return ranked claim results with source provenance,
5. generate evidence-grounded answers whose citations resolve to stored page text.

The proof dataset must exercise the real application path. Direct database insertion is not the preferred path when the existing ingestion / parse / index / grounded-answer APIs can create the same state deterministically.

## 2. Source-of-truth dataset

Reuse the repository-owned synthetic grounded-generation corpus under:

```text
apps/api/evals/data/grounded_corpus.json
apps/api/evals/data/grounded_cases.json
```

The corpus is already authored specifically for this repository and contains no copied third-party patent claim text.

### Public Proof documents

Use exactly these two ordinary documents for the public Proof dataset:

| Corpus id | Filename | Title | Claims | Public Proof |
| --- | --- | --- | ---: | --- |
| `collector` | `grounded-sensor-collector.pdf` | 센서 데이터 수집 장치 | 8 | YES |
| `thermal` | `grounded-battery-thermal.pdf` | 배터리 열 관리 장치 | 8 | YES |

### Excluded from public Proof

Do not include `adversarial` in the initial landing-page screenshot set.

Reason: it intentionally embeds prompt-injection payloads inside claim text. It remains useful as a technical security / guardrail Proof, but it would distract from the primary buyer story in the public portfolio.

## 3. Seeding contract

The Proof seed must use the same application path already exercised by the grounded evaluation:

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
- no direct DB insert unless a later technical constraint makes the real path impractical
- embedding provider may be `fake` for deterministic Proof-state construction
- public screenshots must not imply fake embeddings measure semantic-model quality

## 4. Expected populated Documents state

After seeding, `/documents` must show at least:

1. `grounded-sensor-collector.pdf`
2. `grounded-battery-thermal.pdf`

Both must be successfully ingested and have extracted page text available.

Expected structure from the current corpus renderer:

- 8 claims per document
- 7 claims per rendered page maximum
- therefore 2 rendered pages per Proof document

The Documents screenshot should prove ingestion and traceable source storage rather than merely showing an upload form.

## 5. Search Proof scenarios

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

### S2 — Exact technical-fact search

Query:

```text
측정값의 표본화 주기는 얼마인가?
```

Primary expected evidence:

- document: `collector`
- claim: 6
- answer fact: 20 ms

This is a backup scene, not the primary landing screenshot.

## 6. Grounded Answer Proof scenarios

### G1 — Primary HERO Proof

Question:

```text
저장부의 기록 방식과 기록 용량은 각각 무엇인가?
```

Required evidence:

- `collector`, claim 4
- `collector`, claim 5

Expected answer facts:

- recording method: circular recording / oldest value overwritten by new value
- storage capacity: 512 MB

Why this is the HERO scene:

- concise question
- concrete answer
- naturally requires multiple evidence items
- citations can visibly resolve to two related claims
- demonstrates retrieval + grounding + provenance in one screenshot

Buyer-facing claim:

> ClaimTrace answers from retrieved claim evidence and keeps each supported statement linked to resolvable source spans.

### G2 — Secondary multi-evidence Proof

Question:

```text
배터리 열 관리 장치에서 온도를 측정하는 수단과 냉매를 순환시키는 수단은 무엇인가?
```

Primary relevant evidence:

- `thermal`, claim 1
- `thermal`, claim 6

Acceptable supporting evidence:

- `thermal`, claim 4
- `thermal`, claim 7

Expected answer concepts:

- temperature measurement uses a temperature measurement unit, with thermocouples arranged per battery cell
- coolant circulation uses a circulation unit, with an electric pump as supporting detail

This is the secondary grounded screenshot if a second result-state Proof is needed.

## 7. Scenes to promote

Initial public Proof promotion order:

1. **Grounded Answer HERO** — G1 result populated with citations
2. **Hybrid Search** — S1 result populated with source provenance
3. **Document Detail or Documents** — seeded document state with extracted pages / claim traceability
4. **System Overview** — API + PostgreSQL operational state and workflow map

Do not promote the current `Local LLM` screenshot while it visibly reports `fake` / `fake-model` as a buyer-facing capability claim. It can remain technical evidence or be recaptured later against a real local provider.

## 8. Capture behavior

The Playwright capture must not merely navigate to empty forms.

For result-state scenes it should:

1. wait until Proof seeding has completed,
2. navigate to the relevant page,
3. fill the fixed Proof query/question,
4. submit the form,
5. wait for an expected result/evidence marker,
6. capture only after the deterministic result state is visible.

Prefer stable `data-testid` selectors for Proof-critical result containers if current UI text selectors are insufficiently stable.

## 9. Framing

Current full-page captures leave excessive empty space for Search / Grounded / Documents empty states.

After populated-state capture exists:

- evaluate `fullPage: false` for Search and Grounded scenes,
- prefer a viewport that keeps input + result + provenance visible together,
- avoid cropping out the citation/source-locator portion of the result,
- retain Overview as a broader workflow screenshot.

Final crop decisions must be based on generated populated screenshots, not guessed in advance.

## 10. Integrity rules

A screenshot is promotable only when:

- the target repository commit is recorded,
- the Proof Factory commit is recorded,
- the target working tree is clean or the dirty state is explicitly reviewed,
- migrations are applied,
- API health passes,
- `/api/v1/documents` passes,
- seed documents are present,
- result-state interaction succeeds,
- citations shown in the HERO scene resolve to persisted source text,
- no secret, customer data, or internal credential is visible.

## 11. Implementation boundary for the next step

The next implementation should add a project-local Proof seed entry point that reuses the existing synthetic corpus / PDF builder / application endpoints rather than duplicating a second synthetic dataset.

Recommended conceptual command:

```text
python -m proof.seed
```

or an equivalent container-safe command callable from Firebat Proof Factory as `prepare.command`.

It should seed only the two public Proof documents by default. Adversarial / guardrail material should require an explicit separate mode.

## 12. v0.1 completion criteria

This spec is implemented when one Firebat command can reproducibly produce a new artifact set where:

- Documents shows the two seeded synthetic documents,
- Search S1 visibly returns the expected collector claim evidence,
- Grounded G1 visibly returns an answer with multiple resolvable citations,
- Overview remains healthy,
- no public screenshot exposes fake-model diagnostics as the primary buyer claim,
- the run writes its normal `proof-manifest.json` provenance record.
