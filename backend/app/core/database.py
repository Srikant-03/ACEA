from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,  # Check connection liveliness
    pool_recycle=3600    # Recycle connections every hour
)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI dependency for database sessions."""
    with Session(engine) as session:
        yield session

from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

@contextmanager
def safe_session():
    """
    Context manager for safe database transactions.
    Automatically commits on success, rollbacks on error.
    """
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database transaction failed: {e}")
            raise e
        finally:
            session.close()
