"""Thin proxy around the DoD SBIR/STTR (DSIP) public API.

The upstream returns 403 without a browser-like User-Agent, so every request
here injects one. A generic passthrough plus a few typed helpers are exposed.
"""
import json
from typing import Any, Optional

import httpx

from .config import settings


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.dsip_user_agent,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.dodsbirsttr.mil/topics-app/",
    }


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.dsip_base_url,
        headers=_headers(),
        timeout=45.0,
        follow_redirects=True,
    )


async def get_json(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    async with await _client() as client:
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


async def get_bytes(path: str, params: Optional[dict[str, Any]] = None) -> httpx.Response:
    async with await _client() as client:
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp


def build_search_param(
    *,
    search_text: Optional[str] = None,
    components: Optional[list[str]] = None,
    program_year: Optional[int] = None,
    solicitation_cycle_names: Optional[list[str]] = None,
    release_numbers: Optional[list[str]] = None,
    topic_release_status: Optional[list[int]] = None,
    modernization_priorities: Optional[list[str]] = None,
    sort_by: str = "finalTopicCode,asc",
    technology_area_ids: Optional[list[int]] = None,
    component: Optional[str] = None,
    program: Optional[str] = None,
) -> str:
    """Build the JSON `searchParam` string DSIP expects (URL-encoded by httpx)."""
    payload = {
        "searchText": search_text,
        "components": components,
        "programYear": program_year,
        "solicitationCycleNames": solicitation_cycle_names or ["openTopics"],
        "releaseNumbers": release_numbers or [],
        "topicReleaseStatus": topic_release_status or [591, 592],
        "modernizationPriorities": modernization_priorities or [],
        "sortBy": sort_by,
        "technologyAreaIds": technology_area_ids or [],
        "component": component,
        "program": program,
    }
    return json.dumps(payload, separators=(",", ":"))


async def search_topics(search_param: str, size: int = 10, page: int = 0) -> Any:
    return await get_json(
        "/topics/search",
        params={"searchParam": search_param, "size": size, "page": page},
    )


async def get_topic(topic_id: str) -> Any:
    # The rich topic content lives at /details (objective, description, phases,
    # keywords, tech/focus areas). Summary metadata (title/code/status) comes
    # from the search endpoint and is merged in by callers when available.
    return await get_json(f"/topics/{topic_id}/details")


async def get_topic_questions(topic_id: str) -> Any:
    return await get_json(f"/topics/{topic_id}/questions")


async def get_reference(name: str, params: Optional[dict[str, Any]] = None) -> Any:
    # name is one of: technologyAreas, focusAreas, components, solicitations
    return await get_json(f"/topics/{name}", params=params)
