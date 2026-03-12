"""FastAPI application entry point with multi-tenant auth."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from temporalio.client import Client

from .config import get_settings
from .database.session import dispose_engine, init_engine
from .dependencies import get_current_user
from .routers import workflows
from .tenants import TenantRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down application resources."""
    settings = get_settings()
    engine = init_engine()
    app.state.db_engine = engine
    app.state.temporal_client = await Client.connect(settings.temporal_host)

    # Load tenant registry
    if not settings.auth_disabled:
        app.state.tenant_registry = TenantRegistry.from_file(
            settings.tenants_config_path,
        )
    else:
        app.state.tenant_registry = TenantRegistry()

    yield
    dispose_engine()


app = FastAPI(lifespan=lifespan)

# Apply CORS middleware using settings
_settings = get_settings()
if _settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.allowed_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

app.include_router(workflows.router)


@app.get("/")
async def root(auth=Depends(get_current_user)):
    """Health check endpoint."""
    return {"message": "This is the backend service for Orcha!"}
