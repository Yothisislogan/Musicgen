"""HTTP client for the Google Generative Language (Gemini) API — Lyria music model."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "models/lyria-realtime-exp"
_AUDIO_MIME = "audio/wav"


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it to a valid Google AI Studio API key to use Lyria."
        )
    return key


def _auth_params() -> Dict[str, str]:
    return {"key": _api_key()}


def _build_generate_request(
    prompt: str,
    *,
    negative_prompt: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a single Gemini generateContent request body for Lyria."""
    parts: List[Dict[str, Any]] = [{"text": prompt}]
    if negative_prompt:
        parts.append({"text": f"negative_prompt: {negative_prompt}"})

    generation_config: Dict[str, Any] = {
        "responseModalities": ["AUDIO"],
    }
    if temperature is not None:
        generation_config["temperature"] = temperature
    if seed is not None:
        generation_config["seed"] = seed

    # Duration hint passed as a text instruction when supported
    if duration_seconds is not None:
        parts.append({"text": f"duration: {duration_seconds} seconds"})

    request: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
    }
    return request


def _extract_audio(response: Dict[str, Any]) -> tuple[str, str]:
    """Extract (base64_data, mime_type) from a generateContent response."""
    try:
        candidates = response.get("candidates") or []
        if not candidates:
            raise ValueError("No candidates in response")
        parts = candidates[0].get("content", {}).get("parts") or []
        if not parts:
            raise ValueError("No parts in response candidate")
        inline = parts[0].get("inlineData") or {}
        data = inline.get("data") or ""
        mime = inline.get("mimeType") or _AUDIO_MIME
        if not data:
            raise ValueError("No inline audio data in response")
        return data, mime
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected Lyria response structure: {exc}") from exc


# ---------------------------------------------------------------------------
# Direct (synchronous-style) generation — single request
# ---------------------------------------------------------------------------

async def generate_music(
    prompt: str,
    *,
    model: str = _DEFAULT_MODEL,
    negative_prompt: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    timeout: float = 120.0,
) -> tuple[str, str]:
    """
    Generate a single piece of music via Lyria.

    Returns (audio_base64, mime_type).
    Raises httpx.HTTPStatusError on API errors.
    """
    body = _build_generate_request(
        prompt,
        negative_prompt=negative_prompt,
        duration_seconds=duration_seconds,
        temperature=temperature,
        seed=seed,
    )
    url = f"{_BASE_URL}/{model}:generateContent"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, params=_auth_params(), json=body)
        resp.raise_for_status()
        data = resp.json()

    audio_b64, mime_type = _extract_audio(data)
    logger.info("Lyria direct generation complete, mime=%s bytes_b64=%d", mime_type, len(audio_b64))
    return audio_b64, mime_type


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------

async def submit_batch(
    requests: List[Dict[str, Any]],
    *,
    model: str = _DEFAULT_MODEL,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Submit a batch of generateContent requests to the Gemini Batch API.

    ``requests`` is a list of raw Gemini request dicts (as returned by
    ``_build_generate_request``).  Returns the raw batch job resource dict.
    """
    batch_requests = [{"request": req} for req in requests]
    body = {
        "model": model,
        "requests": batch_requests,
    }
    url = f"{_BASE_URL}/batches"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, params=_auth_params(), json=body)
        resp.raise_for_status()
        job = resp.json()

    logger.info(
        "Batch submitted: name=%s state=%s",
        job.get("name"),
        job.get("state"),
    )
    return job


async def get_batch(
    batch_name: str,
    *,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Poll the status / results of a batch job.

    ``batch_name`` is the full resource name returned by ``submit_batch``,
    e.g. ``"batches/abc123"``.
    """
    url = f"{_BASE_URL}/{batch_name}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=_auth_params())
        resp.raise_for_status()
        return resp.json()


async def list_batches(
    *,
    page_size: int = 20,
    page_token: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """List all batch jobs for the current API key."""
    params = {**_auth_params(), "pageSize": page_size}
    if page_token:
        params["pageToken"] = page_token
    url = f"{_BASE_URL}/batches"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def cancel_batch(
    batch_name: str,
    *,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Cancel a pending or running batch job."""
    url = f"{_BASE_URL}/{batch_name}:cancel"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, params=_auth_params())
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Result extraction helpers
# ---------------------------------------------------------------------------

def extract_batch_results(job: Dict[str, Any]) -> List[tuple[Optional[str], Optional[str], Optional[str]]]:
    """
    Parse a completed batch job into per-request results.

    Returns a list of (audio_b64, mime_type, error_message) tuples, one per
    request in submission order.  If a request failed, audio_b64 is None and
    error_message is set.
    """
    responses = job.get("responses") or []
    out: List[tuple[Optional[str], Optional[str], Optional[str]]] = []
    for item in responses:
        # Each item is {"response": <generateContent response>} or {"error": {...}}
        if "error" in item:
            err = item["error"]
            msg = err.get("message") or str(err)
            out.append((None, None, msg))
            continue
        try:
            audio_b64, mime_type = _extract_audio(item.get("response") or {})
            out.append((audio_b64, mime_type, None))
        except ValueError as exc:
            out.append((None, None, str(exc)))
    return out
