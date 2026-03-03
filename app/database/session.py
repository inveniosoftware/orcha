from collections.abc import Generator

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
        return init_engine()
    return _engine


def get_session() -> Generator[Session, None, None]:
    """Yield a database session."""
    with Session(get_engine()) as session:
        yield session
