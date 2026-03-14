# Orcha Workflows

Backend service for Orcha AI extraction, built with **FastAPI**, **Temporal**, and **PostgreSQL**.

## Prerequisites

- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python ≥ 3.14

## Local Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Start infrastructure (PostgreSQL + Temporal)

```bash
uv run orcha services start
```

### 3. Create database tables

```bash
uv run orcha init-db
```

### 4. Start the application

```bash
# Start both server and worker
uv run orcha run

# Or start them individually
uv run orcha run server     # FastAPI dev server
uv run orcha run workers    # Temporal worker
```

## Authentication

The API uses **multi-tenant RS256 (asymmetric) JWT authentication**. Each tenant has its own RSA key pair(s). The tenant signs tokens with their private key; the server verifies them using the tenant's registered public key.

Tenants are identified by the `iss` (issuer) claim in the JWT. To support zero-downtime key rotation, the server allows multiple public keys per tenant. In token headers, tenants must include a Key ID (`kid`) that matches one of their defined keys in the configuration.

### Tenant Configuration

Create a `tenants.json` file at the project root:

```json
{
  "tenant-a": {
    "name": "Tenant A",
    "public_keys": {
      "kid-1": "-----BEGIN PUBLIC KEY-----\nMIIBI...\n-----END PUBLIC KEY-----"
    }
  },
  "tenant-b": {
    "name": "Tenant B",
    "public_keys": {
      "kid-1": "-----BEGIN PUBLIC KEY-----\nMIIBI...\n-----END PUBLIC KEY-----"
    }
  }
}
```

Each key in the JSON must match the `iss` claim the tenant will use in their JWTs.

> ⚠️ **Never commit `tenants.json` or `.pem` files** — they are already in `.gitignore`.

### Generating RSA Keys (Tenant-Side)

Each tenant generates their own key pair and sends you **only the public key**:

```bash
# Generate a 2048-bit RSA private key (tenant keeps this secret)
openssl genpkey -algorithm RSA -out private_key.pem -pkeyopt rsa_keygen_bits:2048

# Extract the public key (send this to the server operator)
openssl rsa -pubout -in private_key.pem -out public_key.pem
```

### Configuration

| Variable              | Description                              | Required    |
| --------------------- | ---------------------------------------- | ----------- |
| `JWT_ALGORITHM`       | Signing algorithm (default: RS256)       | No          |
| `AUTH_DISABLED`       | Set to `true` to skip auth               | Development |
| `TENANTS_CONFIG_PATH` | Path to tenants JSON (default: tenants.json) | Production  |

**Local development** — bypass authentication entirely:

```bash
export AUTH_DISABLED=true
```

### Creating a Test Token (Tenant-Side)

Tokens **must** include the `iss` claim matching the tenant ID. Optionally include `workflow_id` to scope access.

```python
import jwt
from datetime import datetime, timedelta, timezone

private_key = open("private_key.pem").read()

token = jwt.encode(
    {
        "iss": "tenant-a",                                    # Required: must match tenants.json key
        "workflow_id": "YOUR_WORKFLOW_ID",                    # Optional: scope to a specific workflow
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    },
    private_key,
    algorithm="RS256",
    headers={"kid": "kid-1"}                                  # Required: must match kid in tenants.json public_keys
)
print(token)
```

Use the token:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/workflows/<YOUR_WORKFLOW_ID>
```

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

#### Ollama (local/dev)

```bash
export LLM="ollama/llama3.1"
export OLLAMA_BASE_URL="http://localhost:11434/v1"
```


## CLI Reference

| Command                | Description                              |
|------------------------| ---------------------------------------- |
| `orcha services start` | Start PostgreSQL + Temporal via Docker   |
| `orcha services stop`  | Stop all Docker services                 |
| `orcha init-db`        | Create database tables from models       |
| `orcha run`            | Start both server and worker             |
| `orcha run server`     | Start FastAPI dev server only            |
| `orcha run workers`    | Start Temporal worker only               |

## Useful Commands

```bash
# Stop and remove volumes (reset databases)
docker compose down -v

# View Docker service logs
docker compose logs -f

# Open Temporal UI
open http://localhost:8080
```
