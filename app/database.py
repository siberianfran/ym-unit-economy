"""SQLAlchemy engine, sessionmaker, base for models."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from app.config import settings


_db_url = settings.database_url
if _db_url.startswith("postgres://"):
    _db_url = "postgresql+psycopg://" + _db_url[len("postgres://"):]
elif _db_url.startswith("postgresql://") and "+" not in _db_url.split("://")[0]:
    _db_url = "postgresql+psycopg://" + _db_url[len("postgresql://"):]

engine = create_engine(
    _db_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _db_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base for all ORM models."""
    pass


def get_db() -> Session:
    """FastAPI dependency: yields a DB session and closes it after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
