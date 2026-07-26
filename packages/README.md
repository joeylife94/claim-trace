# packages/

Reserved for code shared between more than one application.

Nothing lives here yet, and nothing should until a second consumer actually exists.
Likely first candidates, in the order the roadmap reaches them:

| Candidate | Shared by | Reached in |
| --- | --- | --- |
| API response types (generated from the OpenAPI schema) | `apps/web` and any future client | Phase 2 |
| Patent text normalisation helpers | ingestion worker and `apps/api` | Phase 2-3 |
| Evaluation datasets and metric helpers | `apps/api` and offline evaluation scripts | Phase 6 |

Guidelines when this directory is populated:

- A package is extracted only when a second consumer exists, never speculatively.
- Python packages are added to the API's dependency set as path dependencies;
  TypeScript packages are wired through npm workspaces.
- Shared packages must not import from `apps/`.
