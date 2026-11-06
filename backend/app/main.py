from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .identity import bind_identity_middleware
from .org_seed import seed_org
from .routers import (
    analysis,
    auth,
    catalog,
    debriefs,
    matches,
    org,
    proposals,
    resume,
    system,
    team,
    topic_intel,
    topics,
    tracker,
)
from .vault import get_vault


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_org(get_vault())
    yield


app = FastAPI(title="SCOUT API", version="1.0.0", lifespan=lifespan)

app.middleware("http")(bind_identity_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(org.router)
app.include_router(topics.router)
app.include_router(topic_intel.router)
app.include_router(matches.router)
app.include_router(catalog.router)
app.include_router(analysis.router)
app.include_router(team.router)
app.include_router(tracker.router)
app.include_router(proposals.router)
app.include_router(debriefs.router)
app.include_router(resume.router)


@app.get("/")
def root():
    return {"name": "SCOUT API", "docs": "/docs"}
