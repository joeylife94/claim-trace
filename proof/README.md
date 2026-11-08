# ClaimTrace Proof Runtime

This directory owns the project-specific runtime used by Firebat Proof Factory.

## Firebat start

```bash
bash proof/firebat-start.sh
```

The script:

1. creates `.env` from `.env.example` only when missing;
2. uses dedicated host ports (`13000` web, `18000` API, `15432` PostgreSQL, `11435` Ollama), all published on `127.0.0.1` only via `proof/compose.firebat.yml`;
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
docker compose -p claimtrace-proof -f docker-compose.yml -f proof/compose.firebat.yml --profile llm exec -T api python -m evals.proof_seed
```

The seed reuses repository-authored synthetic patent documents and sends them through the real application path:

```text
synthetic PDF -> upload -> claim parse -> claim index
```

It does not write directly to PostgreSQL.

## Host publication boundary

`proof/compose.firebat.yml` is layered over `docker-compose.yml` and pins every published port (web, API, PostgreSQL, Ollama) to `127.0.0.1`. The base file's wildcard publication stays the local-development default. The `*_PORT` variables are port numbers only; the bind address is hard-coded in the overlay.

- `!override` is required on each `ports:` list. Plain Compose lists merge, so without it the base wildcard entry would remain next to the loopback one.
- `bash proof/firebat-start.sh --check` renders the config and runs `proof/check-firebat-bindings.py` (loopback-only binding, no host networking, one port entry per service, loopback CORS/API URLs, and no change to anything except `ports` compared with the base compose). It touches no containers. The same gate runs before every normal start.
- `bash proof/test-firebat-bindings.sh` runs the positive and negative cases offline (needs only the `docker compose` CLI and python3).
- A tailnet route, if ever approved, must be a separately reviewed Tailscale Serve path proxying to `127.0.0.1`; never widen the bind.
- Browsers must use `http://127.0.0.1:13000` (IPv4 loopback only; `[::1]` is not published).

### Runtime acceptance (Firebat-owned, not performed by this repository change)

- [ ] Take a fresh PostgreSQL backup.
- [ ] Check out the exact accepted SHA.
- [ ] `bash proof/firebat-start.sh --check` passes.
- [ ] Apply: `bash proof/firebat-start.sh`. By config hash, only `api` and `web` are expected to be recreated relative to the PR #72 shape, provided the apply uses the same checkout directory and `.env` (the PostgreSQL hash includes the absolute path of its init bind mount); confirm at apply time.
- [ ] `docker port` for each `claimtrace-proof` container, and `ss -ltnp`, show only `127.0.0.1:` for 13000/18000/15432/11435.
- [ ] Health/smoke: web `/`, API `/health`, `/api/v1/documents?limit=1`, `/api/v1/llm/status`.
- [ ] State checks: public table count unchanged; `ollama list` includes the model.
- [ ] Fleet audit reports `FAILURES=0 WARNINGS=0`.

## Public Proof boundary

Public screenshots use the ordinary `collector` and `thermal` synthetic documents. The adversarial prompt-injection corpus remains an evaluation asset and is not part of the initial buyer-facing Proof set.
