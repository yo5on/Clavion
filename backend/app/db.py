from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .core.config import settings

# StaticPool keeps one connection, so an in-memory test database survives across sessions
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False},
                       **({"poolclass": StaticPool} if ":memory:" in settings.database_url else {}))
SessionLocal = sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _secure_delete(conn, _):
    # Deleted cases hold medical and financial details: overwrite freed pages instead of leaving them on disk.
    conn.execute("PRAGMA secure_delete = ON")


class Base(DeclarativeBase):
    pass


class Case(Base):
    """A saved claim audit. Stores extracted results only, never the uploaded documents."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    with SessionLocal() as s:
        yield s


def db_ok() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

