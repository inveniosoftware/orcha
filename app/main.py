from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from temporalio.client import Client

from .config import get_settings
from .database.session import dispose_engine, init_engine
from .dependencies import get_current_user
from .routers import workflows


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down application resources."""
    settings = get_settings()
    engine = init_engine()
    app.state.db_engine = engine
    app.state.temporal_client = await Client.connect(settings.temporal_host)
    yield
    dispose_engine()


app = FastAPI(dependencies=[Depends(get_current_user)], lifespan=lifespan)


app.include_router(
    workflows.router,
    dependencies=[Depends(get_current_user)],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "This is the backend service for AIRDEC!"}
