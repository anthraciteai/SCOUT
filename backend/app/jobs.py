"""In-process async job registry for heavy local-LLM work.

Topic fit / summary and the inbox scan used to run *inside* the request handler.
When you left the page the browser dropped the HTTP connection, but FastAPI kept
running the handler to completion and cached the result — so the compute wasn't
wasted. Two gaps remained, though:

  * **No dedup.** Leaving and coming back (or an auto-reload firing) could kick
    off a SECOND Ollama run for the exact same topic while the first was still
    going. Ollama runs them serially, so that silently doubled local GPU time.
  * **No reconnectable progress.** The only feedback was a spinner bound to the
    in-flight request, which died on navigation — a new tab or reload had no way
    to see "still cooking".

This registry closes both. A job is keyed by ``(kind, key, owner)``:

  * :func:`start` *attaches to* an already-running job instead of launching a
    duplicate, and runs the work in a background task that survives the client
    disconnecting (and still caches at the end, exactly like before).
  * Coarse progress lives on the server, so any tab / reload can poll it via the
    ``…/status`` endpoints.

It's deliberately tiny and in-process: SCOUT is single-node and local-first, so
there's no need for a broker. asyncio is cooperative (single thread), so the
plain dict needs no lock — ``start`` does no ``await`` before registering.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .identity import Identity, set_identity


@dataclass
class Job:
    id: str
    kind: str                       # "fit" | "summary" | "scan"
    key: str                        # topic id / scan scope — identifies the work
    owner: str                      # "company:user" — who it belongs to
    state: str = "running"          # running | done | error
    stage: str = "starting"         # human-readable step for the progress bar
    pct: int = 0                    # 0..100
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    result: Any = None              # the work's return value (kept for RETAIN secs)
    task: Optional[asyncio.Task] = None

    def public(self) -> dict[str, Any]:
        """JSON-safe view for the status endpoints (never leaks the task/result)."""
        return {
            "job_id": self.id,
            "kind": self.kind,
            "state": self.state,
            "stage": self.stage,
            "pct": self.pct,
            "error": self.error,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "elapsed": round((self.finished_at or time.time()) - self.started_at, 1),
        }


# Finished jobs linger briefly so a late poll still sees done/error (and the
# progress bar can flash "done" before the result loads).
_RETAIN_SECONDS = 120.0

_jobs: dict[str, Job] = {}
_current: ContextVar[Optional[Job]] = ContextVar("scout_job", default=None)


def _dkey(kind: str, key: str, owner: str) -> str:
    return f"{kind}::{key}::{owner}"


def _gc() -> None:
    now = time.time()
    for k in [
        k
        for k, j in _jobs.items()
        if j.state != "running"
        and j.finished_at is not None
        and (now - j.finished_at) > _RETAIN_SECONDS
    ]:
        _jobs.pop(k, None)


def progress(stage: str, pct: int) -> None:
    """Report a coarse stage from inside the running work.

    A no-op when the work isn't running under a tracked job (e.g. a direct unit
    test), so the heavy functions can call it unconditionally."""
    job = _current.get()
    if job is not None:
        job.stage = stage
        job.pct = max(0, min(99, int(pct)))  # 100 is reserved for "done"
        job.updated_at = time.time()


def get(kind: str, key: str, owner: str) -> Optional[Job]:
    """Exact lookup (running or recently finished)."""
    _gc()
    return _jobs.get(_dkey(kind, key, owner))


def find_running(kind: str, owner: str) -> Optional[Job]:
    """First running job of this kind for this owner, regardless of key.

    Handy for the scan bar: a user runs one scan at a time, so the UI can poll
    without echoing the scan's internal key."""
    _gc()
    for j in _jobs.values():
        if j.kind == kind and j.owner == owner and j.state == "running":
            return j
    return None


def start(
    kind: str,
    key: str,
    owner: str,
    work: Callable[[], Awaitable[Any]],
    *,
    identity: Optional[Identity] = None,
) -> Job:
    """Start — or *attach to* — a job for ``(kind, key, owner)``.

    ``work`` is a zero-arg coroutine factory that does the heavy lifting (and
    caches its own result). If an identical job is already running, its handle
    is returned untouched so callers can ``await job.task`` and share the single
    run instead of spawning a duplicate.
    """
    _gc()
    dk = _dkey(kind, key, owner)
    existing = _jobs.get(dk)
    if existing is not None and existing.state == "running":
        return existing

    job = Job(id=uuid.uuid4().hex, kind=kind, key=key, owner=owner)
    _jobs[dk] = job

    async def runner() -> None:
        # Re-bind identity explicitly: the background task owns its own context
        # copy, and relying on create_task's implicit copy is fragile.
        if identity is not None:
            set_identity(identity)
        token = _current.set(job)
        try:
            job.result = await work()
            job.state = "done"
            job.stage = "done"
            job.pct = 100
        except Exception as e:  # noqa: BLE001 — surfaced via job.error to the poller
            job.state = "error"
            job.error = str(e)[:500]
        finally:
            job.finished_at = time.time()
            job.updated_at = job.finished_at
            _current.reset(token)

    job.task = asyncio.create_task(runner())
    return job
