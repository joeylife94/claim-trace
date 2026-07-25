# tests/

Cross-service tests that exercise more than one running component.

Unit and API tests live next to the code they cover, because they run with that
application's toolchain and inside its container image:

| Suite | Location | Command |
| --- | --- | --- |
| Backend unit / API tests | `apps/api/tests/` | `make test` (`uv run pytest`) |
| Web lint and type checks | `apps/web/` | `make web-lint`, `make web-typecheck` |

This directory is where end-to-end tests will go once there is a workflow spanning
web -> API -> PostgreSQL that is worth asserting on (Phase 2 and later). Such tests
require a running `docker compose` environment, which is why they are kept out of
the default `make test` gate.

No test in this repository may depend on an external LLM, a network model
provider, or a real patent document.
