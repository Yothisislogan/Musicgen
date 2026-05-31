"""Pydantic schemas for Lyria music generation requests and responses."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class LyriaGenerateRequest(BaseModel):
    """Single Lyria music generation request."""

    prompt: str = Field(..., min_length=1, max_length=1024, description="Text description of the desired music.")
    negative_prompt: Optional[str] = Field(None, max_length=512)
    duration_seconds: Optional[float] = Field(None, ge=5.0, le=300.0)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    seed: Optional[int] = Field(None, ge=0)


class LyriaBatchRequest(BaseModel):
    """Submit multiple Lyria generation requests as a single batch job."""

    requests: List[LyriaGenerateRequest] = Field(..., min_length=1, max_length=100)
    model: str = Field("models/lyria-realtime-exp")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class BatchState(str, Enum):
    PENDING = "JOB_STATE_PENDING"
    RUNNING = "JOB_STATE_RUNNING"
    SUCCEEDED = "JOB_STATE_SUCCEEDED"
    FAILED = "JOB_STATE_FAILED"
    CANCELLED = "JOB_STATE_CANCELLED"


class LyriaBatchStatus(BaseModel):
    """Response returned after submitting or polling a batch job."""

    job_id: str
    name: str
    state: BatchState
    create_time: Optional[str] = None
    update_time: Optional[str] = None
    model: str
    request_count: int
    error: Optional[str] = None


class LyriaAudioResult(BaseModel):
    """A single generated audio clip from a batch job."""

    request_index: int
    prompt: str
    audio_b64: Optional[str] = None
    mime_type: str = "audio/wav"
    error: Optional[str] = None


class LyriaBatchResults(BaseModel):
    """Full results for a completed batch job."""

    job_id: str
    name: str
    state: BatchState
    model: str
    results: List[LyriaAudioResult]
    total_requests: int
    succeeded: int
    failed: int


class LyriaDirectResponse(BaseModel):
    """Response from a synchronous (non-batch) Lyria generation."""

    prompt: str
    audio_b64: str
    mime_type: str = "audio/wav"
    model: str
    elapsed: float
