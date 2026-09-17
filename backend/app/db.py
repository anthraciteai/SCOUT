import os
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, create_engine

from .config import settings

os.makedirs(settings.data_dir, exist_ok=True)
os.makedirs(os.path.join(settings.data_dir, "uploads"), exist_ok=True)

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def _auto_migrate() -> None:
    """Add any columns present on the models but missing from existing tables.

    Lightweight forward-only migration for SQLite so new nullable columns (e.g.
    AnalysisRun.heavy_lift) don't break inserts against a pre-existing DB.
    """
    insp = inspect(engine)
    for table_name, table in SQLModel.metadata.tables.items():
        if not insp.has_table(table_name):
            continue
        existing = {c["name"] for c in insp.get_columns(table_name)}
        for col in table.columns:
            if col.name in existing:
                continue
            coltype = col.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(
                    text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {coltype}')
                )
    # Pre-kind rows should stay company so Flint does not treat a product pack as ME.
    if insp.has_table("resume"):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE resume SET kind = 'company' WHERE kind IS NULL OR kind = ''")
            )


def init_db() -> None:
    # Import models so they are registered on SQLModel.metadata
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _auto_migrate()


def get_session():
    with Session(engine) as session:
        yield session
