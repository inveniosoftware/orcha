# Orcha

Orcha AI extraction.

## Prerequisites

- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python ≥ 3.14

## Local Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Run the complete local stack

SQLite is the local-development default, so no Docker services are required.
`orcha run` applies migrations against a local `orcha.db` file, starts a
Temporal dev server backed by `temporal.db`, then the API and a worker:

```bash
uv run orcha run
```

This requires the [`temporal` CLI](https://docs.temporal.io/cli#install) to
be installed. Stopping it (Ctrl-C) preserves both database files; pass
`--reset` to delete them first and start from a clean state:

```bash
uv run orcha run --reset
```

### Running against PostgreSQL

To use PostgreSQL instead (e.g. to match production), start the Dockerized
services, point the app at them, and run the API and worker as separate
processes:

```bash
uv run orcha services start
export DB_DIALECT=postgresql   # DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME
                                # default to the docker-compose values
uv run orcha migrate
uv run orcha run server --dev  # FastAPI dev server
uv run orcha run workers       # Temporal worker for the default queue

# Run a worker for a specific queue
uv run orcha run workers --task-queue low-priority
```

## Authentication

The API uses **multi-tenant RS256 (asymmetric) JWT authentication**. Each tenant has its own RSA key pair(s). The tenant signs tokens with their private key; the server verifies them using the tenant's registered public key.

Tenants are identified by the `iss` (issuer) claim in the JWT. To support zero-downtime key rotation, the server allows multiple public keys per tenant. In token headers, tenants must include a Key ID (`kid`) that matches one of their defined keys in the configuration.

### Local development

`orcha run` sets `DEV_MODE`, which turns authentication off: no token is
required and every request runs as the `dev` tenant, so tenant scoping behaves
the same as it does anywhere else.

```bash
uv run orcha run
curl http://localhost:8000/
```

`AUTH_DISABLED` overrides that either way, so `AUTH_DISABLED=0 uv run orcha run`
exercises real tenant tokens against the local stack.

See [Running against a local InvenioRDM](docs/invenio.md) for pointing an
instance at a local Orcha.

### Tenant Configuration

Real tenants live in `tenants.json` (override with `TENANTS_CONFIG_PATH`), keyed
by the `iss` claim their tokens carry:

```json
{
  "tenant-a": {
    "name": "Tenant A",
    "public_keys": {
      "kid-1": "-----BEGIN PUBLIC KEY-----\nMIIBI...\n-----END PUBLIC KEY-----"
    }
  }
}
```

A tenant generates its own key pair and sends you the public half:

```bash
uv run orcha tenants add tenant-a ./their_public_key.pem
uv run orcha tenants list
```

Pass `--kid` to register a second key alongside the first, and `--force` to
replace one. `orcha tenants token tenant-a ./private_key.pem` signs a token from
the tenant side, with `--kid` to pick the key, `--workflow-id` to scope it to
one workflow and `--expires-in` to set its lifetime in seconds.

> ⚠️ **Never commit `tenants.json` or `.pem` files** — they are already in `.gitignore`.

### Configuration

| Variable              | Description                              | Required    |
| --------------------- | ---------------------------------------- | ----------- |
| `JWT_ALGORITHM`       | Signing algorithm (default: RS256)       | No          |
| `DEV_MODE`            | Run as the `dev` tenant with auth off    | Development |
| `AUTH_DISABLED`       | Override the auth switch either way      | Development |
| `TENANTS_CONFIG_PATH` | Path to tenants JSON (default: tenants.json) | Production  |

### LLM Configuration

The service supports multiple LLM backends. Configure a single setting, `LLM`,
in the form `<provider>/<model>`.

#### LiteLLM (default/recommended)

```bash
export LLM="litellm/groq/qwen/qwen3-32b"
```

Optional configuration:

```bash
export LITELLM_API_BASE="<litellm-endpoint>"
export LITELLM_API_KEY="<api-key>"
```

#### Langfuse (non-default)

Used both for `orcha evals run --langfuse` and for tracing Temporal
workflows when `LANGFUSE_ENABLED=True`. Optional configuration:

```bash
export LANGFUSE_BASE_URL="<langfuse-endpoint>"
export LANGFUSE_SECRET_KEY="<secret-api-key>"
export LANGFUSE_PUBLIC_KEY="<public-api-key>"
```

#### Ollama (local/dev)

```bash
export LLM="ollama/llama3.1"
export OLLAMA_BASE_URL="http://localhost:11434/v1"
```

## Evaluations

`orcha evals sync_dataset` downloads the eval dataset into a local cache once;
`orcha evals run` reuses it for dataset evaluation and fails with a hint if it isn't there yet:

```bash
uv run orcha evals sync_dataset
uv run orcha evals run --model "litellm/gpt-oss-20b"
```

By default, `orcha evals run` extracts and evaluates locally, writing a JSON
summary per item plus the run's average score to `app/evals/eval_results` (override
with `--output`). Pass `--langfuse` to sync the prompt, store the dataset, and
report the experiment in Langfuse instead:

```bash
uv run orcha evals run --model "litellm/gpt-oss-20b" --langfuse
```

Use `--samples N` to evaluate a representative subset instead of the full
dataset; items are sampled proportionally across each dataset resource type:

```bash
uv run orcha evals run --samples 20
```


## CLI Reference

| Command                            | Description                               |
|------------------------------------|-------------------------------------------|
| `orcha services start`             | Start PostgreSQL + Temporal via Docker    |
| `orcha services stop`              | Stop all Docker services                  |
| `orcha migrate`                    | Apply all database migrations             |
| `orcha run`                        | Migrate, then start Temporal, API, and worker (SQLite) |
| `orcha run --reset`                | Same, after deleting `orcha.db` and `temporal.db` |
| `orcha run server`                 | Start the FastAPI server only             |
| `orcha run server --dev`           | Start the FastAPI server with hot reload  |
| `orcha run workers`                | Start Temporal worker for default queue   |
| `orcha run workers --task-queue Q` | Start Temporal worker for a specific queue |
| `orcha tenants list`               | List registered tenants and their key IDs |
| `orcha tenants add T KEY.pem`      | Register a tenant's public key            |
| `orcha tenants token T KEY.pem`    | Sign a token for a tenant                 |
| `orcha evals sync_dataset`         | Download the eval dataset into the local cache |
| `orcha evals run`                  | Run a local metadata extraction evaluation, writing results to `app/evals/eval_results` |
| `orcha evals run --output DIR`     | Same, writing results to `DIR` instead   |
| `orcha evals run --langfuse`       | Extraction evaluation, and report the experiment in Langfuse |
| `orcha evals run --samples N`      | Evaluate N items, sampled per category    |

## Database Migrations

The deployed schema is managed with Alembic. Apply committed migrations with:

```bash
uv run alembic upgrade head
```

For local setup, `uv run orcha migrate` is a convenience wrapper around the
same Alembic upgrade.

See [Database Migrations](docs/migrations.md) for the full process of generating
and reviewing migrations when SQLModel models change.

## Useful Commands

```bash
# Stop and remove volumes (reset databases)
docker compose down -v

# View Docker service logs
docker compose logs -f

# Open Temporal UI
open http://localhost:8080
```

## Releasing

Release for Orcha are done manually. Pushing a `v*` tag triggers the image build, so commit the version bump and changelog before you tag.

### 1. Bump the version

Bump `pyproject.toml` and re-lock in one step:

```bash
uv version --bump patch   # or: minor, major
```

Then set the same `X.Y.Z` in `charts/orcha/Chart.yaml`, in both `version` and `appVersion`.

### 2. Update the changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/). Every `feat:`/`fix:`/`refactor:` commit should already have a bullet under `## [Unreleased]`. At release time, promote that section:

- Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and open a fresh empty `## [Unreleased]` above it.
- In the link footer, repoint `[unreleased]` to `vX.Y.Z...HEAD` and add `[X.Y.Z]: .../compare/<prev>...vX.Y.Z`.

### 3. Commit, tag, and push

```bash
git commit -am "release: vX.Y.Z"
git tag vX.Y.Z
git push origin main vX.Y.Z
```

The tag push kicks off the Docker workflow below, which builds and publishes the image.

## Docker Image Release

Docker images are automatically built and published to `registry.cern.ch/orcha/orcha` by the [Docker workflow](.github/workflows/dockerpublish.yml).

### Triggers

| Event | Image tag |
|---|---|
| Push a `v*` tag (e.g. `v1.2.3`) | `1.2.3` |
| Manual via GitHub UI (`workflow_dispatch`) | depends on branch/tag |

### Required secrets

The workflow uses two repository secrets that must be configured in `Settings → Secrets and variables → Actions`:

| Secret | Description                     |
|---|---------------------------------|
| `REGISTRY_USER` | registry robot account username |
| `REGISTRY_PASSWORD` | registry robot account password |
