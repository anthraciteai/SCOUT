"""DSIP browse/search/detail endpoints (proxied)."""
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from .. import dsip

router = APIRouter(prefix="/api/topics", tags=["topics"])


# scope -> (solicitationCycleNames, topicReleaseStatus)
# 591 = Pre-Release, 592 = Open. Empty lists = all statuses (incl. closed).
SCOPE_MAP: dict[str, tuple[list[str], list[int]]] = {
    "open": (["openTopics"], [591, 592]),   # open + pre-release (default)
    "openonly": (["openTopics"], [592]),
    "prerelease": (["openTopics"], [591]),
    "all": ([], []),                         # everything, including closed
}


@router.get("/search")
async def search(
    searchText: Optional[str] = None,
    scope: str = Query("open", description="open | openonly | prerelease | all"),
    component: Optional[str] = None,
    program: Optional[str] = None,
    technologyAreaIds: Optional[str] = Query(None, description="comma separated ids"),
    sortBy: str = "finalTopicCode,asc",
    size: int = 10,
    page: int = 0,
):
    def _ids(s: Optional[str]) -> Optional[list[int]]:
        if not s:
            return None
        out = [int(x.strip()) for x in s.split(",") if x.strip().isdigit()]
        return out or None

    cycles, statuses = SCOPE_MAP.get(scope, SCOPE_MAP["open"])

    search_param = dsip.build_search_param(
        search_text=searchText,
        solicitation_cycle_names=cycles,
        topic_release_status=statuses,
        component=component,
        program=program,
        technology_area_ids=_ids(technologyAreaIds),
        sort_by=sortBy,
    )
    try:
        return await dsip.search_topics(search_param, size=size, page=page)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text[:500])
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"DSIP upstream error: {e}")


@router.get("/reference/{name}")
async def reference(name: str, request: Request):
    """Proxy reference data: technologyAreas, focusAreas, components, solicitations."""
    allowed = {"technologyAreas", "focusAreas", "components", "solicitations"}
    if name not in allowed:
        raise HTTPException(status_code=404, detail=f"Unknown reference '{name}'")
    params = dict(request.query_params)
    try:
        return await dsip.get_reference(name, params=params or None)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text[:500])


@router.get("/{topic_id}/questions")
async def questions(topic_id: str):
    try:
        return await dsip.get_topic_questions(topic_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Could not load questions")


@router.get("/{topic_id}/download/{fmt}")
async def download(topic_id: str, fmt: str, inline: bool = False):
    fmt = fmt.upper()
    if fmt not in ("PDF", "DOCX"):
        raise HTTPException(status_code=400, detail="fmt must be PDF or DOCX")
    try:
        resp = await dsip.get_bytes(f"/topics/{topic_id}/download/{fmt}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Download failed")
    media = "application/pdf" if fmt == "PDF" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    ext = "pdf" if fmt == "PDF" else "docx"
    # inline lets the browser render the PDF in an <iframe> instead of downloading.
    disp = "inline" if (inline and fmt == "PDF") else "attachment"
    return Response(
        content=resp.content,
        media_type=media,
        headers={"Content-Disposition": f'{disp}; filename="topic_{topic_id}.{ext}"'},
    )


@router.get("/{topic_id}")
async def topic_detail(topic_id: str):
    try:
        return await dsip.get_topic(topic_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Topic not found")
