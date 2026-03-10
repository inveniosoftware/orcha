"""Shared test fixtures for the AIRDEC test suite."""

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session, SQLModel

from app.database.session import get_session
from app.main import app

# In-memory SQLite engine shared across all sessions via StaticPool.
# StaticPool ensures every connection returns the same underlying
# database, so test inserts are visible to route handler sessions.
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture
def db_session():
    """Provide a real SQLModel session backed by in-memory SQLite.

    Creates all tables before the test and drops them after.
    Overrides both the FastAPI ``get_session`` dependency and
    ``app.state.db_engine`` so that route handlers and the
    stream generator use the same test database.
    """
    SQLModel.metadata.create_all(_test_engine)

    def _override_get_session():
        with Session(_test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session

    # Also set db_engine on app state so code that creates Session()
    # directly (e.g. the SSE stream generator) uses the test engine.
    app.state.db_engine = _test_engine

    with Session(_test_engine) as session:
        yield session

    SQLModel.metadata.drop_all(_test_engine)
