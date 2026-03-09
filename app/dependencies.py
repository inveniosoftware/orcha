"""FastAPI dependencies for multi-tenant authentication."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from .auth import AuthContext, decode_access_token
from .config import get_settings
from .tenants import TenantRegistry

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token", auto_error=not settings.auth_disabled
)


def get_tenant_registry(request: Request) -> TenantRegistry:
    """Retrieve the tenant registry from application state.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The TenantRegistry stored on app.state.
    """
    return request.app.state.tenant_registry


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    tenant_registry: TenantRegistry = Depends(get_tenant_registry),
) -> AuthContext:
    """Extract and verify the JWT, resolving the tenant.

    When AUTH_DISABLED=true, authentication is skipped and a
    dummy AuthContext is returned (for local development only).

    Args:
        token: The Bearer token extracted by OAuth2PasswordBearer.
        tenant_registry: The loaded tenant registry.

    Returns:
        An AuthContext with tenant_id, sub, and optional workflow_id.
    """
    if settings.auth_disabled:
        return AuthContext(tenant_id="dev-tenant", sub="dev-user")

    return decode_access_token(token, tenant_registry)
