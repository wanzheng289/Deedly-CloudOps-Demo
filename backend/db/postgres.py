from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from project.backend.core.config import get_service_config

DATABASE_URL = get_service_config().database_url

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def init_db() -> None:
    # Delayed import to avoid circular dependency.
    from project.backend.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
