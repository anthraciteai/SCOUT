"""Tests for the async job registry (dedup + reconnectable progress).

These lock in the two behaviours that close the "cost leak" the UI relies on:
  * starting a job that's already running ATTACHES instead of duplicating, so a
    retrigger (or a second tab) never spawns a second Ollama run;
  * progress is reported server-side so a poller can reconnect.

Each test runs under its own event loop (asyncio.run) and clears the in-process
registry first, so module-level job state never leaks between cases.
"""
import asyncio

import pytest

from app import jobs
from app.identity import Identity


@pytest.fixture(autouse=True)
def _reset_registry():
    jobs._jobs.clear()
    yield
    jobs._jobs.clear()


def test_job_runs_and_captures_result():
    async def main():
        async def work():
            jobs.progress("halfway", 50)
            return {"ok": True}

        job = jobs.start("fit", "t1", "acme:ken", work)
        await job.task
        assert job.state == "done"
        assert job.pct == 100
        assert job.stage == "done"
        assert job.result == {"ok": True}

    asyncio.run(main())


def test_dedup_attaches_to_running_job():
    async def main():
        gate = asyncio.Event()

        async def work():
            await gate.wait()
            return "done-value"

        first = jobs.start("scan", "scope", "acme:ken", work)
        # A second start for the same (kind, key, owner) while the first is still
        # running must return the SAME job — not launch a duplicate.
        second = jobs.start("scan", "scope", "acme:ken", work)
        assert second is first
        assert second.id == first.id

        gate.set()
        await first.task
        assert first.state == "done"
        assert first.result == "done-value"

        # Once finished, a fresh start is allowed again (new id).
        third = jobs.start("scan", "scope", "acme:ken", lambda: asyncio.sleep(0))
        assert third.id != first.id
        await third.task

    asyncio.run(main())


def test_progress_is_scoped_to_the_running_job():
    async def main():
        # Outside any job, progress() is a harmless no-op.
        jobs.progress("nope", 10)

        async def work():
            jobs.progress("reading", 20)
            # pct is clamped to <=99 while running (100 reserved for "done").
            jobs.progress("way too far", 500)
            return None

        job = jobs.start("summary", "t2", "acme:jake", work)
        await job.task
        assert job.state == "done"
        assert job.pct == 100  # finished → 100 regardless of the mid-run clamp

    asyncio.run(main())


def test_errors_surface_and_free_dedup():
    async def main():
        async def work():
            raise RuntimeError("boom")

        job = jobs.start("fit", "terr", "acme:ken", work)
        await job.task
        assert job.state == "error"
        assert "boom" in (job.error or "")

        # The slot is freed, so the user can retry.
        retry = jobs.start("fit", "terr", "acme:ken", lambda: asyncio.sleep(0))
        assert retry.state == "running"
        await retry.task

    asyncio.run(main())


def test_find_running_and_get():
    async def main():
        gate = asyncio.Event()

        async def work():
            await gate.wait()

        job = jobs.start("scan", "mine", "acme:ken", work)
        assert jobs.get("scan", "mine", "acme:ken") is job
        assert jobs.find_running("scan", "acme:ken") is job
        assert jobs.find_running("scan", "other:user") is None
        gate.set()
        await job.task

    asyncio.run(main())


def test_identity_is_rebound_inside_the_task():
    from app import identity as idmod

    captured = {}

    async def main():
        async def work():
            ident = idmod.current_identity()
            captured["user"] = ident.user_id if ident else None

        who = Identity(user_id="zoe", company_id="acme", display_name="Zoe", groups=[], auth="test")
        job = jobs.start("fit", "tz", "acme:zoe", work, identity=who)
        await job.task

    asyncio.run(main())
    assert captured["user"] == "zoe"
