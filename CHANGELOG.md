# Changelog

## [Unreleased]

### Features

- *(funding)* Add retry policy
- Add cli for evals
  - Reuse app metadata extraction flow in evals

### Fixes

- *(evals)* Improve dataset synchronization
- Replace OUTPUT_RETRIES with RETRIES due to bump in pydantic-ai


## [0.6.0] - 2026-09-08

### Features
- *(schema)* Add metadata fields
- *(workflow)* Add new fields suggestions: funding, license and copyright
  - Resolve funders, awards and licenses via the `resolve_metadata_suggestions` activity
  - Split the LLM schema between extracted fields and resolved suggestions

### Fixes
- *(evals)* Skip Zenodo dataset if not published yet
- *(agent)* Retry output validation failures: Set `output_retries=2` on the agent to solve output validation issues

### Refactor
- *(helm)* Tenants.json as a ConfigMap instead of a Persistent Volume Claim
- *(agent)* Move the LLM agent construction logic from `activities._llm` to a dedicated module `agent`
- *(activities)* Share HTTP allowlist
  - Move `_http_verify_for_pdf_url` to `app.activities.utils.http_verify`, generalize its error message, and use it in both activities.
  - Rename `PDF_HTTP_ALLOWLIST` to `HTTP_ALLOWLIST` to be more accurate, and exposes `INVENIO_BASE_URL` through the chart.

## [0.5.0] - 2026-08-13

### Features
- `orcha run` runs the complete local stack: migrations, a Temporal dev server, the API, and a worker, with prefixed logs and shared teardown
  - Requires the `temporal` CLI; `--reset` deletes `orcha.db`/`temporal.db` first, a normal shutdown preserves them
- SQLite is the local-development default database; PostgreSQL remains the production default
  - `DB_URL` overrides everything; otherwise `DB_DIALECT` picks between `DB_PATH` (sqlite) and the `DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`/`DB_NAME` fields (postgresql)
  - **Breaking:** the `PGUSER`/`PGPASSWORD`/`PGHOST`/`PGPORT`/`PGDATABASE` settings are removed; use the `DB_*` fields instead
- *(auth)* Add `DEV_MODE`, which runs the API with authentication off and serves every request as the `dev` tenant
  - `orcha run` turns it on, so a local InvenioRDM needs no keys; `AUTH_DISABLED` overrides it either way for exercising real tenant tokens locally
  - **Breaking:** `AUTH_DISABLED` now defaults to unset and follows `DEV_MODE`; the tenant it stands in for is `dev` rather than `dev-tenant`
- *(cli)* Add `orcha tenants` for the tenant registry
  - `add` registers a tenant's public key, `list` shows what is registered
  - `token` signs a token for a tenant from its private key
- Add evals pipeline to Orcha

## [0.4.0] - 2026-07-30

### Features

- Allow local file downloads without ssl verification or with custom ca bundle
- *(workflow)* Add a funding check workflow
  - Refactor(extraction): Move shared LLM construction logic from extract_metadata into a reusable _llm.build_agent helper, and use it in the existing metadata extraction activity.
  - Add a new check_funding_relevance activity. The new activity assesses whether a record's title and description match a grant description, guided by a caller-supplied rule.

### Fixes

- Silently fail if requested page is out of index: handles cases where the file passed has less pages than the default for extraction.
- Helm: handle new setting pdf_http_allowlist

## [0.3.0] - 2026-07-07

### Features
- *(feedback)* Add workflow feedback flow
  - New `POST /workflows/{id}/feedback` endpoint to submit feedback on a workflow result

## [0.2.2] - 2026-07-07

### Features
- *(extract)* Reduce fabricated metadata suggestions
  - Tell the model to leave absent fields empty instead of using placeholders
  - Skip the LLM on near-empty text (<50 chars); image-only PDFs otherwise make the model fabricate records
  - Clear title/description/doi whose values aren't present in the source text

### Fixes
- *(schema)* Tighten extraction prompts so the model copies the source faithfully
  - Copy the abstract word-for-word instead of paraphrasing or shortening it
  - Include every author instead of truncating the list with et al.
  - Resolve each author's affiliation marker and drop the marker and postal address
- Stop falling back to the tenant id as the user id
- *(helm)* Keep the migration job and its logs after it finishes
  - Drop ttlSecondsAfterFinished so failed jobs and their logs aren't deleted
  - Drop hook-succeeded so a completed job stays until the next install or upgrade

### Refactor
- *(helm)* Extract shared db and langfuse env helpers

## [0.2.1] - 2026-07-02

### Fixes
- Install the langfuse extra in the Docker image

## [0.2.0] - 2026-07-02

### Features
- *(tracking)* Add created, starttime, endtime to workflows, needed for KPIs
- *(workflow)* Add user_id to workflows and context
- *(tracing)* Add optional Langfuse tracing
- *(helm)* Add database migration job and Langfuse secrets

### Fixes
- *(db)* Add unique constraint on public_id
- Limit retries per activity and workflow
- *(orcid)* Fix ORCID extraction and validation
  - Validate with idutils, shared by schema and extractor; drop IDs that fail the check digit
  - Flatten creators into parallel name/orcid/affiliation lists so gpt-oss keeps them in tool calls
  - Inline each ORCID next to its author and match the anchor by its position rather than the first substring match

### Refactor
- *(extractor)* Name the ORCID icon-matching tolerances
- *(helm)* Make worker replicas configurable

## [0.1.3] - 2026-06-29

### Features

- Configurable LLM settings via LLM_SETTINGS with more reliable extraction
  - LlmSettings parses the JSON LLM_SETTINGS env var: 
  model forwards to the chat model's request settings, output selects the structured-output strategy

### Fixes

- *(schema)* Keep YYYY-MM precision for publication dates
  - The validator collapsed YYYY-MM to YYYY; keep whatever precision is given
- *(extractor)* Stop flattening tables into full_text
  - Tables were re-appended as pipe-joined rows that duplicated page text and added empty-cell noise,
  bloating the prompt on dense documents. They remain in extra

### Refactor
- Add error logging for Orcha, providing more visibility on the errors in the terminal
- *(extraction)* Flat LLM schema with configurable output mode

## [0.1.2] - 2026-06-22

### Fixes
- Use valid sse framing

## [0.1.1] - 2026-06-17

### Features

- *(db)* Add alembic; initial migration
- *(helm)* Add initial chart for orcha
  - Added the Helm chart for deploying Orcha (with support for tenants)
  - Added deployment documentation (available in charts/orcha/README.md)

## [0.0.1] - 2026-06-09
_First release._

[unreleased]: https://github.com/inveniosoftware/orcha/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/inveniosoftware/orcha/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/inveniosoftware/orcha/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/inveniosoftware/orcha/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/inveniosoftware/orcha/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/inveniosoftware/orcha/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/inveniosoftware/orcha/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/inveniosoftware/orcha/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/inveniosoftware/orcha/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/inveniosoftware/orcha/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/inveniosoftware/orcha/compare/v0.0.1...v0.1.1
[0.0.1]: https://github.com/inveniosoftware/orcha/releases/tag/v0.0.1
