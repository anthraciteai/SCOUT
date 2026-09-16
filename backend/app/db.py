import os
from sqlmodel import SQLModel, Session, create_engine

from .config import settings

os.makedirs(settings.data_dir, exist_ok=True)
os.makedirs(os.path.join(settings.data_dir, "uploads"), exist_ok=True)

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Import models so they are registered on SQLModel.metadata
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
