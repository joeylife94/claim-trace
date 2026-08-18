# ClaimTrace Proof Runtime

This directory owns the project-specific runtime used by Firebat Proof Factory.

## Firebat start

```bash
bash proof/firebat-start.sh
```

The script:

1. creates `.env` from `.env.example` only when missing;
2. uses dedicated host ports (`13000` web, `18000` API, `15432` PostgreSQL, `11435` Ollama);
3. starts PostgreSQL and the repository's optional Ollama service;
4. ensures `qwen2.5:1.5b` is present in the persistent `ollama_models` volume;
5. runs `alembic upgrade head` explicitly;
6. starts the API with `LLM_PROVIDER=ollama` and the web UI.

The embedding provider remains deterministic `fake` for Proof capture. This keeps retrieval fast and reproducible while the grounded-generation surface uses a real local model. The screenshot must not be described as a model-quality benchmark; it proves the real local-model integration and the citation/provenance workflow.

Override the local model when needed:

```bash
PROOF_CLAIMTRACE_OLLAMA_MODEL=qwen2.5:1.5b bash proof/firebat-start.sh
```

## Seed

After migrations and API health pass:

```bash
docker compose --profile llm exec -T api python -m evals.proof_seed
```

The seed reuses repository-authored synthetic patent documents and sends them through the real application path:

```text
synthetic PDF -> upload -> claim parse -> claim index
```

It does not write directly to PostgreSQL.

## Public Proof boundary

Public screenshots use the ordinary `collector` and `thermal` synthetic documents. The adversarial prompt-injection corpus remains an evaluation asset and is not part of the initial buyer-facing Proof set.
