"""DSIP browse/search/detail endpoints (proxied)."""
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from .. import dsip

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("/search")
async def search(
    searchText: Optional[str] = None,
    solicitationCycleNames: Optional[str] = Query(None, description="comma separated, e.g. openTopics"),
    topicReleaseStatus: Optional[str] = Query(None, description="comma separated ids, e.g. 591,592"),
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
        out = []
        for x in s.split(","):
            x = x.strip()
            if x.isdigit():
                out.append(int(x))
        return out or None

    def _list(s: Optional[str]) -> Optional[list[str]]:
        if not s:
            return None
        return [x.strip() for x in s.split(",") if x.strip()] or None

    search_param = dsip.build_search_param(
        search_text=searchText,
        solicitation_cycle_names=_list(solicitationCycleNames) or ["openTopics"],
        topic_release_status=_ids(topicReleaseStatus) or [591, 592],
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
async def download(topic_id: str, fmt: str):
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
    return Response(
        content=resp.content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="topic_{topic_id}.{ext}"'},
    )


@router.get("/{topic_id}")
async def topic_detail(topic_id: str):
    try:
        return await dsip.get_topic(topic_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Topic not found")
