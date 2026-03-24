from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from ..config import get_settings

_engine: Engine | None = None


def init_engine() -> Engine:
    """Create and store the global SQLAlchemy engine."""
    global _engine
    settings = get_settings()
    _engine = create_engine(settings.database_url)
    return _engine


def dispose_engine() -> None:
    """Dispose the global engine and release connections."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def get_engine() -> Engine:
    """Return the global engine, initializing it if needed."""
    if _engine is None:
        raise RuntimeError("Engine is not initialized!")
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a database session context manager."""
    with Session(get_engine()) as session:
        yield session


def get_db_session() -> Generator[Session, None, None]:
    """Make a database session for FastAPI dependencies."""
    with get_session() as session:
        yield session
