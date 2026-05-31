"""FastAPI router for Google Lyria music generation endpoints."""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from . import client as lyria_client
from .schemas import (
    BatchState,
    LyriaAudioResult,
    LyriaBatchRequest,
    LyriaBatchResults,
    LyriaBatchStatus,
    LyriaDirectResponse,
    LyriaGenerateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lyria", tags=["lyria"])


def _http_error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        body = exc.response.json()
        return body.get("error", {}).get("message") or str(exc)
    except Exception:
        return str(exc)


def _job_to_status(job: dict, request_count: int) -> LyriaBatchStatus:
    return LyriaBatchStatus(
        job_id=job.get("name", "").split("/")[-1],
        name=job.get("name", ""),
        state=BatchState(job.get("state", BatchState.PENDING)),
        create_time=job.get("createTime"),
        update_time=job.get("updateTime"),
        model=job.get("model", ""),
        request_count=request_count,
        error=job.get("error", {}).get("message") if job.get("error") else None,
    )


# ---------------------------------------------------------------------------
# POST /lyria/generate — synchronous single-track generation
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=LyriaDirectResponse)
async def generate(req: LyriaGenerateRequest) -> LyriaDirectResponse:
    """Generate a single music track directly via Lyria (no batch)."""
    start = time.perf_counter()
    try:
        audio_b64, mime_type = await lyria_client.generate_music(
            req.prompt,
            negative_prompt=req.negative_prompt,
            duration_seconds=req.duration_seconds,
            temperature=req.temperature,
            seed=req.seed,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=_http_error_detail(exc))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Lyria API unreachable: {exc}")

    return LyriaDirectResponse(
        prompt=req.prompt,
        audio_b64=audio_b64,
        mime_type=mime_type,
        model=lyria_client._DEFAULT_MODEL,
        elapsed=round(time.perf_counter() - start, 3),
    )


# ---------------------------------------------------------------------------
# POST /lyria/batch — submit a batch of generation requests
# ---------------------------------------------------------------------------

@router.post("/batch", response_model=LyriaBatchStatus, status_code=202)
async def submit_batch(req: LyriaBatchRequest) -> LyriaBatchStatus:
    """Submit multiple Lyria music generation requests as a single batch job."""
    raw_requests = [
        lyria_client._build_generate_request(
            r.prompt,
            negative_prompt=r.negative_prompt,
            duration_seconds=r.duration_seconds,
            temperature=r.temperature,
            seed=r.seed,
        )
        for r in req.requests
    ]
    try:
        job = await lyria_client.submit_batch(raw_requests, model=req.model)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=_http_error_detail(exc))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Lyria API unreachable: {exc}")

    return _job_to_status(job, len(req.requests))


# ---------------------------------------------------------------------------
# GET /lyria/batch/{job_id} — poll job status
# ---------------------------------------------------------------------------

@router.get("/batch/{job_id}", response_model=LyriaBatchStatus)
async def get_batch_status(job_id: str) -> LyriaBatchStatus:
    """Poll the status of a Lyria batch job."""
    batch_name = f"batches/{job_id}"
    try:
        job = await lyria_client.get_batch(batch_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Batch job '{job_id}' not found")
        raise HTTPException(status_code=exc.response.status_code, detail=_http_error_detail(exc))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Lyria API unreachable: {exc}")

    responses = job.get("responses") or []
    return _job_to_status(job, len(responses) or 0)


# ---------------------------------------------------------------------------
# GET /lyria/batch/{job_id}/results — retrieve audio from a completed job
# ---------------------------------------------------------------------------

@router.get("/batch/{job_id}/results", response_model=LyriaBatchResults)
async def get_batch_results(job_id: str) -> LyriaBatchResults:
    """Retrieve audio results from a completed Lyria batch job."""
    batch_name = f"batches/{job_id}"
    try:
        job = await lyria_client.get_batch(batch_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Batch job '{job_id}' not found")
        raise HTTPException(status_code=exc.response.status_code, detail=_http_error_detail(exc))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Lyria API unreachable: {exc}")

    state = BatchState(job.get("state", BatchState.PENDING))
    if state not in (BatchState.SUCCEEDED, BatchState.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Batch job is not yet complete (state: {state.value}). Poll /lyria/batch/{job_id} first.",
        )

    raw_results = lyria_client.extract_batch_results(job)
    # Reconstruct original prompts from the request list stored in the job (best-effort)
    request_bodies = job.get("requests") or []

    results: list[LyriaAudioResult] = []
    succeeded = 0
    failed = 0
    for idx, (audio_b64, mime_type, error) in enumerate(raw_results):
        # Try to recover the original prompt from the stored request
        prompt = ""
        try:
            parts = (
                request_bodies[idx]
                .get("request", {})
                .get("contents", [{}])[0]
                .get("parts", [{}])
            )
            prompt = next((p["text"] for p in parts if "text" in p), "")
        except (IndexError, KeyError, TypeError):
            pass

        if error:
            failed += 1
        else:
            succeeded += 1

        results.append(
            LyriaAudioResult(
                request_index=idx,
                prompt=prompt,
                audio_b64=audio_b64,
                mime_type=mime_type or "audio/wav",
                error=error,
            )
        )

    return LyriaBatchResults(
        job_id=job_id,
        name=job.get("name", batch_name),
        state=state,
        model=job.get("model", ""),
        results=results,
        total_requests=len(results),
        succeeded=succeeded,
        failed=failed,
    )


# ---------------------------------------------------------------------------
# POST /lyria/batch/{job_id}/cancel
# ---------------------------------------------------------------------------

@router.post("/batch/{job_id}/cancel", status_code=200)
async def cancel_batch(job_id: str) -> dict:
    """Cancel a pending or running Lyria batch job."""
    batch_name = f"batches/{job_id}"
    try:
        result = await lyria_client.cancel_batch(batch_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Batch job '{job_id}' not found")
        raise HTTPException(status_code=exc.response.status_code, detail=_http_error_detail(exc))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Lyria API unreachable: {exc}")

    return {"cancelled": True, "name": batch_name, **result}


# ---------------------------------------------------------------------------
# GET /lyria/batches — list all batch jobs
# ---------------------------------------------------------------------------

@router.get("/batches")
async def list_batches(
    page_size: int = Query(20, ge=1, le=100),
    page_token: Optional[str] = Query(None),
) -> dict:
    """List all Lyria batch jobs for the configured API key."""
    try:
        return await lyria_client.list_batches(page_size=page_size, page_token=page_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=_http_error_detail(exc))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Lyria API unreachable: {exc}")
