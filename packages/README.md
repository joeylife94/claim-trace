# packages/

Reserved for code shared between more than one application.

Nothing lives here, and nothing should until a second consumer actually exists.
Nothing has been extracted from `apps/api` or `apps/web` into this directory, and
there is no ingestion worker: ingestion runs inside the API request.

The candidates below were listed early in the project and none has been acted on.
Treat them as ideas, not a plan; the phase numbers refer to `docs/ROADMAP.md` and
those phases are not a schedule for extraction.

| Candidate | Would be shared by | Roadmap phase when listed |
| --- | --- | --- |
| API response types (generated from the OpenAPI schema) | `apps/web` and any future client | Phase 2 |
| Patent text normalisation helpers | `apps/api` and a second consumer, if one ever exists | Phase 2-3 |
| Evaluation datasets and metric helpers | `apps/api` and offline evaluation scripts | Phase 6 |

Guidelines when this directory is populated:

- A package is extracted only when a second consumer exists, never speculatively.
- Python packages are added to the API's dependency set as path dependencies;
  TypeScript packages are wired through npm workspaces.
- Shared packages must not import from `apps/`.
