# Evaluations

Two reproducible measurements, over separate corpora:

- **Retrieval** (Phase 3A) - this page.
- **Grounded generation** (Phase 4A-2) - [below](#grounded-generation-evaluation-phase-4a-2).

---

## Retrieval evaluation (Phase 3A)

A small, reproducible measurement of ClaimTrace's claim retrieval.

```bash
docker compose up -d postgres
docker compose run --rm api python -m evals.run              # configured model
docker compose run --rm api python -m evals.run --provider fake
```

Writes `results/results.json` (machine-readable) and `results/REPORT.md`
(the summary), both committed so a change in retrieval behaviour shows up as a
diff.

### What it actually runs

The real pipeline, end to end, through the real HTTP API:

```
build synthetic PDFs → POST /documents → POST /claims/parse
  → POST /claims/index → POST /search/claims  (dense, lexical, hybrid)
```

There is deliberately **no** evaluation-only retrieval path. If claim search
regresses, this regresses. It runs against a dedicated `*_eval` database that it
creates, migrates, and truncates itself, so it never touches development data.

### The dataset

| | |
| --- | --- |
| `data/corpus.json` | 26 claims across 2 documents |
| `data/queries.json` | 19 queries with relevance labels |

All of it is newly authored for this repository. **No third-party or copyrighted
patent claim is reproduced here** - the subject matter is deliberately mundane
(a sensor collector, a battery thermal manager) and the wording is invented. The
point is to exercise Korean claim structure, dependency expressions, technical
units, and compound terminology, not to describe a real invention.

Query categories, chosen so that neither channel can win everything:

| Category | What it targets |
| --- | --- |
| `exact_terminology` | Verbatim phrases. Easy for lexical, harder for a small embedding model. |
| `korean_compound` | Compounds written without the spaces the claim uses (`환경감시모듈`). Full-text search cannot match these at all; trigram is what recovers them. |
| `paraphrase` | Almost no shared surface tokens with the target. The dense channel's job. |
| `dependency` | Structural queries (`다중종속항`, `제7항을 인용하는…`), which only match because the search text carries a metadata header. |
| `technical_number` | Units and figures (`섭씨 45도`, `50밀리볼트`). |
| `irrelevant` | **No relevant claim exists.** Scored separately, so a channel that always returns something is measurably wrong rather than silently rewarded. |

Labels were written from the claim text before any retrieval run and have not
been adjusted to improve any channel's score. `test_eval_metrics.py` asserts that
every label points at a claim that exists, so a stale label fails the suite
rather than quietly depressing a metric.

### Metrics

- **Recall@1/3/5** is *set* recall: the fraction of a query's relevant claims in
  the top *k*. For a query with three relevant claims, Recall@1 cannot exceed
  0.33, so a low Recall@1 here is partly an artefact of the labels.
- **MRR@10** uses the rank of the first relevant result; 0 if none is in the top
  10.
- Queries with no relevant claim are excluded from both averages - there is no
  meaningful recall of an empty set - and reported separately.

The report also contains a **"where hybrid loses to a single channel"** section.
It exists because MRR looks only at the first relevant hit and can hide a real
cost of fusion: RRF interleaves two lists, so a claim one channel ranked fourth
can be pushed past the cutoff by the other channel's confident-but-wrong
candidates. Looking for that deliberately is better than letting the aggregate
flatter the design.

### What these numbers are not

26 claims and 19 queries is enough to catch a broken retrieval channel and to
compare two configurations against each other. It is **far too small to establish
retrieval quality**, and nothing here should be quoted as a benchmark result. A
real evaluation needs a corpus orders of magnitude larger, labels from someone
who reads patents professionally, and queries that were not written by the person
who wrote the corpus.

With `--provider fake`, the dense numbers measure plumbing rather than retrieval:
that provider is deterministic but not semantic, and cannot match a paraphrase.

---

## Grounded-generation evaluation (Phase 4A-2)

```bash
docker compose up -d postgres
docker compose run --rm api python -m evals.grounded_run                # deterministic
docker compose run --rm api python -m evals.grounded_run --tier ollama  # real model
docker compose run --rm api python -m evals.grounded_run --tier ollama --limit 6
```

Writes `results/grounded/results-<tier>.json` and
`results/grounded/REPORT-<tier>.md`, both committed so a behaviour change shows
up as a diff.

### What it actually runs

The real pipeline, end to end, through the real HTTP API:

```
build synthetic PDFs → POST /documents → POST /claims/parse → POST /claims/index
  → POST /grounded/answers  → GET /documents/{id}/pages   (to verify every quote)
```

Every returned citation is checked by reading the page back through the public
pages endpoint and comparing the quote to the stored text at its own offsets. The
headline **citation resolution** number is therefore measured against persisted
state rather than asserted.

It runs against a dedicated `*_grounded_eval` database that it creates, migrates,
and truncates itself.

### The dataset

| | |
| --- | --- |
| `data/grounded_corpus.json` | 23 claims across 3 documents |
| `data/grounded_cases.json` | 16 questions with labels |

Newly authored for this repository; **no third-party or copyrighted patent claim
is reproduced.** Deliberately separate from `data/corpus.json`: adding these
documents there would change what competes in every retrieval query and silently
invalidate that evaluation's committed numbers.

The third document is **adversarial**. Every one of its claims carries an
injection payload appended to otherwise plausible claim text - "ignore all
previous instructions", a demand to cite `EV-999`, a forged `</evidence>` block,
a fake JSON answer, fabricated page numbers and offsets, a Markdown fence. It is
uploaded, parsed, indexed, retrieved, and cited exactly like the other two,
because that is how such text would actually arrive: inside a real claim in a
real document that somebody filed.

Case categories:

| Category | What it targets |
| --- | --- |
| `single_evidence` | One claim states the answer. |
| `multi_evidence` | The answer needs two or three claims together. |
| `paraphrase` | Almost no shared surface tokens with the target claim. |
| `dependency` | Requires reading the dependency relationship, not just the text. |
| `document_scoped` | Answerable in one document and **not** in the scoped one, so citing outside the scope is measurably wrong. |
| `unanswerable` | The corpus does not state the answer. Declining is correct. |
| `conflicting` | Two claims genuinely disagree. Both citing them and reporting the conflict are defensible, so the case is scored as ambiguous. |
| `injection` | The best evidence sits in a claim carrying an injection payload. |

Labels were written from the claim text before any run and have not been adjusted
to improve a score. `relevant` is what a correct answer must cite; `acceptable`
counts for precision but is never required for recall, so a defensible extra
citation costs nothing; `forbidden` must never be cited.

### Two tiers, measuring different things

**`deterministic`** replaces the model with an in-process oracle that parses the
evidence blocks it was given and cites the labelled claims that are present.

> This tier does **not** measure model quality, and nothing from it should ever
> be quoted as if it did.

What it measures is the pipeline - whether retrieval and the context budget
deliver the right claim to the prompt, whether a citation resolves character for
character, and whether a hostile answer is refused - reliably, on every run, in
seconds. A model-based tier measures those badly, because the failures are rare
and stochastic: waiting for a small model to hallucinate an identifier is not a
test.

It also runs a **guardrail sub-suite**: six complete, schema-shaped answers that
each break exactly one grounding rule (a fabricated identifier, the forged id the
adversarial corpus demands, an uncited statement, a model-supplied locator,
contradictory insufficiency flags, and a bare claim number used as an identifier)
sent through the whole pipeline against a real question. Each must be refused
rather than served.

**`ollama`** runs the configured local model. It is the only tier whose
evidence-selection numbers say anything about a model - and with a 1.5B model on
CPU over a 23-claim corpus, what they say is narrow.

### Metrics

| Metric | Definition |
| --- | --- |
| Structured-output success | The answer satisfied the JSON schema. |
| Answerability accuracy | Answered when the corpus answers, declined when it does not. Ambiguous cases count either way. |
| Insufficient precision / recall | Scored as a pair rather than averaged, because the two errors are not equivalent: declining an answerable question withholds a usable answer, while answering an unanswerable one is the failure this phase exists to prevent. |
| **Citation resolution** | Every returned quote is the stored page text at its own locator. |
| Evidence-ID validity | No answer was refused for naming an identifier the server never issued. |
| Statement citation coverage | Returned statements carrying a resolvable citation. |
| Evidence selection precision / recall | Against the labels. Meaningful as a *model* number only in the Ollama tier. |
| Forbidden citations | Citations outside a scoped question's document. |
| End-to-end success | All of the above, per case. |

Citation resolution is 1.000 on a correctly built system *by construction* - a
citation that cannot be resolved is refused rather than returned. It is reported
anyway, because it is this phase's central claim, and a claim nobody measures is
a claim nobody notices breaking.

### What these numbers are not

23 claims and 16 questions is enough to show the pipeline is wired correctly and
to catch a gross regression. It is **far too small to establish groundedness or
answer quality**, and none of it should be quoted as a benchmark. A real
evaluation needs a corpus orders of magnitude larger, labels from someone who
reads patents professionally, and questions not written by the person who wrote
the corpus.

Finally, the distinction the whole exercise rests on: a resolved citation shows
that a statement **points at** retrieved source text. It does not show that the
cited text **entails** the statement. That is a semantic judgement, and this
pipeline makes none.

ClaimTrace does not provide legal advice and does not determine infringement,
validity, novelty, inventive step, or patentability.
