# infra/

Infrastructure assets for local and on-premise operation. Deployment tooling
(Kubernetes, Terraform, CI pipelines) is deliberately out of scope for this phase.

| Path | Purpose |
| --- | --- |
| `postgres/init/` | SQL executed once by the PostgreSQL entrypoint on a fresh data directory. |

The container topology itself lives in `../docker-compose.yml`; service images are
defined by `../apps/api/Dockerfile` and `../apps/web/Dockerfile`.
