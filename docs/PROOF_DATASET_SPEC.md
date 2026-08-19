# ClaimTrace Proof Dataset Spec v0.1

Status: IMPLEMENTED — FINAL FIREBAT E2E REVALIDATION PENDING
Purpose: deterministic buyer-facing Proof capture for Firebat Proof Factory

## 1. Objective

Create a reproducible populated application state that proves ClaimTrace can:

1. ingest synthetic patent-like PDFs,
2. parse and index claim structure,
3. perform real hybrid retrieval,
4. expose exact document / claim / page / character provenance,
5. generate evidence-grounded answers whose citations resolve to stored source text.

The Proof path uses the real application lifecycle; direct DB insertion is not used.

## 2. Public Proof dataset

Source of truth:

```text
apps/api/evals/data/grounded_corpus.json
apps/api/evals/data/grounded_cases.json
```

Public Proof uses exactly two repository-authored synthetic documents:

| id | filename | title | claims |
| --- | --- | --- | ---: |
| collector | grounded-sensor-collector.pdf | 센서 데이터 수집 장치 | 8 |
| thermal | grounded-battery-thermal.pdf | 배터리 열 관리 장치 | 8 |

The adversarial prompt-injection corpus remains an evaluation/security asset and is excluded from initial public screenshots.

## 3. Seeding contract

```text
synthetic corpus
→ text-based PDF generation
→ POST /api/v1/documents
→ claim parse
→ claim index
→ Search / Grounded UI
```

Required properties:

- synthetic data only
- no customer or production data
- idempotent repeated runs
- filename-based reuse of completed Proof documents
- duplicate Proof filenames fail closed
- isolated `claimtrace-proof` Compose project
- real `intfloat/multilingual-e5-small` embeddings for buyer-facing retrieval
- real local Ollama generation with `qwen2.5:1.5b`

## 4. Documents Proof

`/documents` must show exactly:

1. `grounded-sensor-collector.pdf`
2. `grounded-battery-thermal.pdf`

The public capture must show `2 total`. A repeated run must reuse the same two Proof documents rather than create additional copies.

## 5. Search HERO

Query:

```text
오래된 데이터를 새로운 데이터로 덮어쓰는 기록 방법
```

Primary expected evidence:

- `collector` claim 4
- circular recording overwrites the oldest measurement with the new measurement

Buyer-facing Proof condition:

- hybrid retrieval executes through the real UI
- `multilingual-e5-small` is visible in the retrieval profile
- `deterministic-hash` is absent
- ranked results retain claim/page/character provenance

## 6. Grounded Answer HERO

### Primary HERO — thermal multi-evidence

Question:

```text
배터리 열 관리 장치에서 온도를 측정하는 수단과 냉매를 순환시키는 수단은 무엇인가?
```

Scope:

```text
grounded-battery-thermal.pdf
```

Mode: `hybrid`
Evidence count: `6`

Expected concepts:

- temperature measurement: thermocouples arranged per battery cell
- coolant circulation: circulation unit / electric pump

Expected supporting claims from the repository-owned eval labels:

- primary: thermal claim 1, claim 6
- acceptable support: thermal claim 4, claim 7

The committed real-model eval for `qwen2.5:1.5b + multilingual-e5-small` recorded this G05 scenario as end-to-end success with resolvable citations. That result is evidence for choosing the scenario, not a general model benchmark.

Buyer-facing capture gates require visible:

- `열전대`
- `전동 펌프`
- `Claim 6`
- `Claim 4`
- Answer panel
- Cited evidence panel

The capture fails if it shows:

- `Evidence not specific enough`
- `The retrieved claims do not answer this question`
- an API error state

### Rejected former HERO — G04 storage method + capacity

The previous question:

```text
저장부의 기록 방식과 기록 용량은 각각 무엇인가?
```

is no longer the public HERO. A Firebat run on 2026-08-19 retrieved the relevant evidence but the local model produced drafts rejected by the grounding validator on both the initial and repair attempts; the API correctly returned 502. Runtime logs showed Ollama itself completed both `/api/chat` requests successfully, so this was a model-output/grounding-contract failure rather than a timeout or provider outage.

## 7. Capture scenes

Promotion order:

1. Grounded Answer HERO — thermal multi-evidence result
2. Hybrid Search — collector claim retrieval + provenance
3. Documents — exactly two seeded PDFs
4. System Overview — API/PostgreSQL workflow state
5. Local LLM — supporting infrastructure Proof

The Local LLM screenshot is promotable only when it visibly reports real Ollama / `qwen2.5:1.5b`, never `fake` / `fake-model`.

## 8. Integrity gates

A screenshot set is promotable only when:

- target repository commit is recorded
- Proof Factory commit is recorded
- migrations are applied
- web/API/documents/LLM-status health checks pass
- Documents shows exactly two Proof documents
- Search uses real multilingual-E5 retrieval and has no duplicate seeded document copies
- Grounded HERO returns supported statements and cited evidence
- citation/source spans remain resolvable
- no secret, customer data, or credential is visible
- `proof-manifest.json` is generated

## 9. Current completion condition

Run:

```bash
bash ./scripts/proof-claim-trace-trial.sh
```

v0.1 is complete when a fresh artifact set passes all five scenes under the stricter buyer-facing gates and the resulting screenshots pass visual review.
