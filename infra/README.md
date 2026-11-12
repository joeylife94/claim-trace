# infra/

Infrastructure assets for local and on-premise operation. Deployment tooling
(Kubernetes, Terraform, deployment pipelines) does not exist in this repository.
Continuous-integration verification workflows do: they live in
`../.github/workflows` and build and test the stack, but nothing here deploys it.

| Path | Purpose |
| --- | --- |
| `postgres/init/` | SQL executed once by the PostgreSQL entrypoint on a fresh data directory. |

The container topology itself lives in `../docker-compose.yml`; service images are
defined by `../apps/api/Dockerfile` and `../apps/web/Dockerfile`. That stack is a
local-development stack (hot-reload servers, source bind mounts, no
authentication), not a deployment definition.
