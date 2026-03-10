"""JWT authentication utilities for multi-tenant RS256 token verification."""

from dataclasses import dataclass

import jwt
from fastapi import HTTPException, status

from .config import get_settings
from .tenants import TenantRegistry


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request context."""

    tenant_id: str
    sub: str
    workflow_id: str | None = None


def decode_access_token(token: str, tenant_registry: TenantRegistry) -> AuthContext:
    """Decode and verify a tenant-scoped RS256 JWT.

    The token's `iss` claim is used to identify the tenant. The
    corresponding public key is looked up from the tenant registry
    and used to verify the signature.

    Args:
        token: The encoded JWT string.
        tenant_registry: Registry to look up tenant public keys.

    Returns:
        An AuthContext with tenant_id, sub, and optional workflow_id.

    Raises:
        HTTPException: If the token is expired, invalid, the issuer
            is missing, or the tenant is unknown.
    """
    settings = get_settings()

    # Extract kid from unverified header
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token header missing 'kid'",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode without verification to read the issuer claim
    try:
        unverified = jwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant_id = unverified.get("iss")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'iss' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant = tenant_registry.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unknown tenant: {tenant_id}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Select the correct public key using the kid
    public_key = tenant.public_keys.get(kid)
    if not public_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unknown key ID '{kid}' for tenant: {tenant_id}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify the token with the specific public key
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.jwt_algorithm],
            issuer=tenant_id,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthContext(
        tenant_id=tenant_id,
        sub=payload.get("sub", ""),
        workflow_id=payload.get("workflow_id"),
    )
