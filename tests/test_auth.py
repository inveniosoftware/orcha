"""Tests for multi-tenant JWT authentication."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database.models import Workflow, WorkflowStatus
from app.main import app
from app.tenants import TenantConfig, TenantRegistry

# ---------- Generate two RSA key pairs (one per test tenant) ----------


def _make_rsa_keypair():
    """Generate a fresh RSA key pair and return (private_pem, public_pem)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


TENANT_A_PRIVATE, TENANT_A_PUBLIC = _make_rsa_keypair()
TENANT_B_PRIVATE, TENANT_B_PUBLIC = _make_rsa_keypair()
ROGUE_PRIVATE, _ = _make_rsa_keypair()  # key not registered with any tenant

TEST_REGISTRY = TenantRegistry(
    {
        "tenant-a": TenantConfig(
            tenant_id="tenant-a",
            name="Tenant A",
            public_keys={"key-1": TENANT_A_PUBLIC.decode()},
        ),
        "tenant-b": TenantConfig(
            tenant_id="tenant-b",
            name="Tenant B",
            public_keys={"key-1": TENANT_B_PUBLIC.decode()},
        ),
    }
)


# ---------- Fixtures ----------


@pytest.fixture(autouse=True)
def configure_test_settings(monkeypatch, mocker):
    """Override settings and mock infrastructure for testing."""
    monkeypatch.setenv("AUTH_DISABLED", "false")

    get_settings.cache_clear()

    # Mock Temporal Client
    mocker.patch("app.main.Client.connect", return_value=mocker.AsyncMock())

    # Patch TenantRegistry.from_file so lifespan doesn't look for a real file
    mocker.patch(
        "app.main.TenantRegistry.from_file",
        return_value=TEST_REGISTRY,
    )


@pytest.fixture
def client():
    """Create a FastAPI TestClient."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_overrides():
    """Clean up dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


# ---------- Helpers ----------


def generate_test_token(
    tenant_id: str = "tenant-a",
    workflow_id: str | None = None,
    expired: bool = False,
    use_private_key: bytes = TENANT_A_PRIVATE,
    kid: str = "key-1",
    **extra_claims,
) -> str:
    """Generate a JWT signed with the specified tenant's private key."""
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)

    payload = {"iss": tenant_id, "exp": exp, **extra_claims}
    if workflow_id:
        payload["workflow_id"] = workflow_id

    headers = {"kid": kid}

    return jwt.encode(payload, use_private_key, algorithm="RS256", headers=headers)


# ---------- Basic auth tests ----------


def test_auth_missing_token_returns_401(client):
    """Endpoints require a Bearer token."""
    response = client.get("/")
    assert response.status_code == 401


def test_auth_valid_token_returns_200(client):
    """A valid RS256 token for a known tenant allows access."""
    token = generate_test_token()
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"message": "This is the backend service for Orcha!"}


def test_auth_expired_token_returns_401(client):
    """An expired token is rejected."""
    token = generate_test_token(expired=True)
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_auth_invalid_signature_returns_401(client):
    """A token signed by an unregistered key is rejected."""
    token = generate_test_token(use_private_key=ROGUE_PRIVATE)
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---------- Tenant identification tests ----------


def test_auth_missing_iss_returns_401(client):
    """A token without an 'iss' claim is rejected."""
    payload = {
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, TENANT_A_PRIVATE, algorithm="RS256")
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "iss" in response.json()["detail"].lower()


def test_auth_unknown_tenant_returns_401(client):
    """A token with an unrecognized 'iss' is rejected."""
    token = generate_test_token(tenant_id="unknown-tenant")
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "unknown tenant" in response.json()["detail"].lower()


def test_auth_tenant_b_valid_token(client):
    """Tenant B can authenticate with its own key pair."""
    token = generate_test_token(tenant_id="tenant-b", use_private_key=TENANT_B_PRIVATE)
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_auth_cross_tenant_key_rejected(client):
    """Tenant A's key cannot be used with tenant B's issuer claim."""
    # Sign with tenant-a's key but claim to be tenant-b
    token = generate_test_token(tenant_id="tenant-b", use_private_key=TENANT_A_PRIVATE)
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---------- Auth disabled tests ----------


def test_auth_disabled_bypass(client, monkeypatch):
    """When AUTH_DISABLED is true, any request passes without a token."""
    import app.dependencies as deps
    from app.config import Settings

    monkeypatch.setattr(deps, "settings", Settings(auth_disabled=True))
    # oauth2_scheme captures auto_error at import time, so also patch it
    monkeypatch.setattr(deps.oauth2_scheme, "auto_error", False)

    response = client.get("/")
    assert response.status_code == 200


# ---------- Workflow-scoped access tests ----------


def test_workflow_scoped_access_granted(client, db_session):
    """A token with a matching workflow_id is permitted."""
    wf = Workflow(
        status=WorkflowStatus.SUCCESS,
        url="https://example.com/test_a.pdf",
        tenant_id="tenant-a",
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)

    token = generate_test_token(workflow_id=wf.public_id)

    response = client.get(
        f"/workflows/{wf.public_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["public_id"] == wf.public_id


def test_workflow_scoped_access_denied(client):
    """A token with a mismatched workflow_id is rejected."""
    token = generate_test_token(workflow_id="some-other-workflow")

    response = client.get(
        "/workflows/my-target-workflow",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized for this workflow"


def test_workflow_admin_access_granted(client, db_session):
    """A token with no workflow_id or workflow_id='*' is permitted."""
    wf = Workflow(
        status=WorkflowStatus.SUCCESS,
        url="https://example.com/test_a.pdf",
        tenant_id="tenant-a",
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)

    token_no_id = generate_test_token()
    token_star = generate_test_token(workflow_id="*")

    for token in [token_no_id, token_star]:
        response = client.get(
            f"/workflows/{wf.public_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["public_id"] == wf.public_id


# ---------- Tenant isolation tests ----------


def test_tenant_cannot_access_other_tenants_workflow(client, db_session):
    """Tenant B cannot access a workflow owned by tenant A."""
    wf = Workflow(
        status=WorkflowStatus.SUCCESS,
        url="https://example.com/test_a.pdf",
        tenant_id="tenant-a",
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)

    token = generate_test_token(tenant_id="tenant-b", use_private_key=TENANT_B_PRIVATE)

    response = client.get(
        f"/workflows/{wf.public_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


# ---------- Key Rotation (kid) tests ----------


def test_auth_missing_kid_in_header_returns_401(client):
    """A token without any 'kid' in the header is rejected."""
    # Generate token bypassing the helper to omit the header
    now = datetime.now(timezone.utc)
    payload = {"iss": "tenant-a", "exp": now + timedelta(hours=1)}
    token = jwt.encode(payload, TENANT_A_PRIVATE, algorithm="RS256")

    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "missing 'kid'" in response.json()["detail"].lower()


def test_auth_with_invalid_kid_returns_401(client):
    """A token specifying a 'kid' that the tenant does not have is rejected."""
    token = generate_test_token(kid="unknown-key-id")
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "unknown key id" in response.json()["detail"].lower()


def test_auth_multiple_keys_support(client, mocker):
    """A tenant can have multiple active keys and auth succeeds with either."""
    # Create a secondary key pair for Tenant A
    secondary_private, secondary_public = _make_rsa_keypair()

    # Create a mock registry where Tenant A has two keys
    multi_key_registry = TenantRegistry(
        {
            "tenant-a": TenantConfig(
                tenant_id="tenant-a",
                name="Tenant A",
                public_keys={
                    "key-1": TENANT_A_PUBLIC.decode(),
                    "key-2025": secondary_public.decode(),
                },
            )
        }
    )

    from app.dependencies import get_tenant_registry

    app.dependency_overrides[get_tenant_registry] = lambda: multi_key_registry

    # Token signed with default key
    token_1 = generate_test_token(kid="key-1")

    # Token signed with secondary key
    token_2 = generate_test_token(use_private_key=secondary_private, kid="key-2025")

    response_1 = client.get("/", headers={"Authorization": f"Bearer {token_1}"})
    assert response_1.status_code == 200

    response_2 = client.get("/", headers={"Authorization": f"Bearer {token_2}"})
    assert response_2.status_code == 200


# ---------- Malformed token tests ----------


@pytest.mark.parametrize(
    "bad_token",
    ["not.a.jwt", "", "abc", "a.b.c"],
    ids=["garbled", "empty", "single-segment", "three-dots"],
)
def test_auth_malformed_token_returns_401(client, bad_token):
    """Completely garbled token strings are rejected."""
    response = client.get("/", headers={"Authorization": f"Bearer {bad_token}"})
    assert response.status_code == 401


# ---------- Stream endpoint auth tests ----------


def test_stream_missing_token_returns_422(client):
    """The stream endpoint requires a token query parameter."""
    response = client.get("/workflows/any-workflow/stream")
    assert response.status_code == 422  # FastAPI validation error


def test_stream_empty_token_returns_401(client):
    """The stream endpoint with an empty token returns 401."""
    response = client.get("/workflows/any-workflow/stream?token=")
    assert response.status_code == 401
    assert "missing token" in response.json()["detail"].lower()


def test_stream_expired_token_returns_401(client):
    """An expired token on the stream endpoint is rejected."""
    token = generate_test_token(expired=True)
    response = client.get("/workflows/any-workflow/stream", params={"token": token})
    assert response.status_code == 401


def test_stream_invalid_token_returns_401(client):
    """A rogue-signed token on the stream endpoint is rejected."""
    token = generate_test_token(use_private_key=ROGUE_PRIVATE)
    response = client.get("/workflows/any-workflow/stream", params={"token": token})
    assert response.status_code == 401


def test_stream_workflow_scope_mismatch_returns_403(client):
    """A scoped token for a different workflow is rejected on stream."""
    token = generate_test_token(workflow_id="other-workflow")
    response = client.get("/workflows/target-workflow/stream", params={"token": token})
    assert response.status_code == 403


def test_stream_cross_tenant_returns_403(client, db_session):
    """Tenant B cannot stream a workflow owned by tenant A."""
    wf = Workflow(
        status=WorkflowStatus.SUCCESS,
        url="https://example.com/test_a.pdf",
        tenant_id="tenant-a",
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)

    token = generate_test_token(tenant_id="tenant-b", use_private_key=TENANT_B_PRIVATE)

    response = client.get(f"/workflows/{wf.public_id}/stream", params={"token": token})
    assert response.status_code == 403


def test_stream_valid_token_returns_200(client, db_session):
    """A valid token for the owning tenant streams successfully."""
    wf = Workflow(
        status=WorkflowStatus.SUCCESS,
        url="https://example.com/test_a.pdf",
        tenant_id="tenant-a",
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)

    token = generate_test_token()

    response = client.get(f"/workflows/{wf.public_id}/stream", params={"token": token})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


# ---------- Create / List workflow auth tests ----------


def test_create_workflow_requires_auth(client):
    """POST /workflows/ without a token is rejected."""
    response = client.post("/workflows/", json={"url": "https://example.com/doc.pdf"})
    assert response.status_code == 401


def test_create_workflow_stamps_tenant_id(client, db_session, mocker):
    """POST /workflows/ stamps the tenant_id from the auth context."""
    token = generate_test_token()

    # Mock the temporal client to avoid real connection
    mock_temporal = mocker.AsyncMock()
    mocker.patch.object(client.app.state, "temporal_client", mock_temporal)

    response = client.post(
        "/workflows/",
        json={"url": "https://example.com/doc.pdf"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    # Verify the workflow was created with the correct tenant_id
    created_id = response.json()["public_id"]
    wf = db_session.get(Workflow, 1)
    assert wf is not None
    assert wf.tenant_id == "tenant-a"
    assert wf.public_id == created_id


def test_list_workflows_requires_auth(client):
    """GET /workflows/ without a token is rejected."""
    response = client.get("/workflows/")
    assert response.status_code == 401


def test_list_workflows_tenant_isolation(client, db_session):
    """GET /workflows/ only returns workflows for the authenticated tenant."""
    # Create workflows for two different tenants
    wf_a = Workflow(
        status=WorkflowStatus.SUCCESS,
        url="https://example.com/test_a.pdf",
        tenant_id="tenant-a",
    )
    wf_b = Workflow(
        status=WorkflowStatus.SUCCESS,
        url="https://example.com/test_b.pdf",
        tenant_id="tenant-b",
    )
    db_session.add_all([wf_a, wf_b])
    db_session.commit()
    db_session.refresh(wf_a)
    db_session.refresh(wf_b)

    # Tenant A should only see their own workflow
    token_a = generate_test_token()
    response = client.get(
        "/workflows/",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200
    workflows = response.json()
    assert len(workflows) == 1
    assert workflows[0]["tenant_id"] == "tenant-a"
    assert workflows[0]["public_id"] == wf_a.public_id

    # Tenant B should only see their own workflow
    token_b = generate_test_token(
        tenant_id="tenant-b", use_private_key=TENANT_B_PRIVATE
    )
    response = client.get(
        "/workflows/",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 200
    workflows = response.json()
    assert len(workflows) == 1
    assert workflows[0]["tenant_id"] == "tenant-b"
    assert workflows[0]["public_id"] == wf_b.public_id
