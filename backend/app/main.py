from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .routers import (
    analysis,
    debriefs,
    proposals,
    resume,
    system,
    topics,
    tracker,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SBIR Scout API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(topics.router)
app.include_router(analysis.router)
app.include_router(tracker.router)
app.include_router(proposals.router)
app.include_router(debriefs.router)
app.include_router(resume.router)


@app.get("/")
def root():
    return {"name": "SBIR Scout API", "docs": "/docs"}
