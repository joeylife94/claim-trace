# tests/

This directory holds no tests. It is a pointer: ClaimTrace's tests live next to
the code they cover, because they run with that application's toolchain and
inside its container image.

| Suite | Location | Command |
| --- | --- | --- |
| Backend, database-free tier | `apps/api/tests/` | `make test-unit` (`uv run pytest -m "not integration"`) |
| Backend, PostgreSQL `integration` tier | `apps/api/tests/` | `make test-docker` (`docker compose run --rm api pytest`); `make test` runs the whole suite on the host and skips this tier when PostgreSQL is unreachable |
| Real-public-corpus acceptance (D3 / D4) | `apps/api/tests/d3_acceptance/`, `apps/api/tests/d4_acceptance/` | Not collected by default (`norecursedirs` in `apps/api/pyproject.toml`); run explicitly by the `Progression D3 Real Public Corpus` and `Progression D4 Description Evidence` workflows |
| Web lint and type checks | `apps/web/` | `make web-lint`, `make web-typecheck` |
| Browser end-to-end (Playwright scripts) | `apps/web/e2e/*.mjs` | Run by the `scripts/verify-*.sh` and `scripts/capture-v1-07-proof.sh` scripts or directly by a workflow; see below |
| Retrieval and grounded evaluations | `apps/api/evals/` | `make eval`, `make eval-fake`, `make verify-deterministic-regression`; see `apps/api/evals/README.md` |

`make check` runs lint, format check, the host backend test run, and the web lint
and type check. It does not run the PostgreSQL tier in Docker, the end-to-end
scripts, the evaluations, or the acceptance tests.

## End-to-end tests

The end-to-end tests are Playwright scripts under `apps/web/e2e/`. They need a
running web -> API -> PostgreSQL stack and a Chromium install, which is why they
are outside the default `make test` gate. They are started in two ways:

- By a script: `scripts/verify-v1-06-golden-path.sh` (`v1-06-golden-path.mjs`),
  `scripts/verify-progression-retry-real.sh` (`progression-retry-real.mjs`),
  and `scripts/capture-v1-07-proof.sh` (`v1-07-proof-capture.mjs`).
  `scripts/verify-controlled-pilot-handoff.sh` chains several of these.
- Directly by a GitHub Actions workflow: `v1-03-golden-path.mjs`,
  `v1-05-review-golden-path.mjs`, and `progression-retry-ui.mjs` have no wrapper
  script.

Note that `scripts/capture-v1-07-proof.sh` writes into `docs/proof` by default
and removes the existing `screenshots/` and `demo/` there first; set
`V1_07_PROOF_DIR` to redirect the output elsewhere.

## Real patent documents

No default test depends on an external LLM, a network model provider, or a real
patent document. The default suites use synthetic PDFs and the fake LLM and
embedding providers.

There is one deliberate exception, kept out of the default run. The D3 and D4
acceptance tests exercise two real public Korean patent PDFs. Each file is
pinned by SHA-256 in `docs/real-public-corpus/manifest.json`, downloaded at run
time, never committed, and checked by `scripts/verify-d3-real-corpus-inputs.sh`
(which fails closed on a hash or text-support mismatch) before the tests use it.
They are acceptance checks of the product path, not retrieval-quality
measurements and not legal evidence.
