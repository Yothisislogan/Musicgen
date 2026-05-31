"""Tests for the Lyria Batch API module."""

from __future__ import annotations

import base64
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response

# Stub out torch before any package import to avoid the heavy dependency.
_torch_mock = MagicMock()
_torch_mock.cuda.is_available.return_value = False
_torch_mock.float32 = "float32"
_torch_mock.bfloat16 = "bfloat16"
sys.modules.setdefault("torch", _torch_mock)
sys.modules.setdefault("torch.backends", MagicMock())

from kortexa.music_gen.lyria import client as lyria_client  # noqa: E402
from kortexa.music_gen.lyria.schemas import BatchState, LyriaBatchRequest, LyriaGenerateRequest  # noqa: E402


# ---------------------------------------------------------------------------
# client._build_generate_request
# ---------------------------------------------------------------------------

def test_build_generate_request_minimal():
    req = lyria_client._build_generate_request("upbeat jazz")
    assert req["contents"][0]["role"] == "user"
    parts = req["contents"][0]["parts"]
    assert parts[0]["text"] == "upbeat jazz"
    assert req["generationConfig"]["responseModalities"] == ["AUDIO"]


def test_build_generate_request_with_options():
    req = lyria_client._build_generate_request(
        "calm piano",
        negative_prompt="drums",
        duration_seconds=30.0,
        temperature=0.8,
        seed=42,
    )
    texts = [p["text"] for p in req["contents"][0]["parts"]]
    assert "calm piano" in texts
    assert any("negative_prompt" in t for t in texts)
    assert any("30.0" in t for t in texts)
    assert req["generationConfig"]["temperature"] == 0.8
    assert req["generationConfig"]["seed"] == 42


# ---------------------------------------------------------------------------
# client._extract_audio
# ---------------------------------------------------------------------------

def _make_response(audio_b64: str, mime: str = "audio/wav") -> dict:
    return {
        "candidates": [{
            "content": {
                "parts": [{
                    "inlineData": {"mimeType": mime, "data": audio_b64}
                }]
            }
        }]
    }


def test_extract_audio_ok():
    raw = base64.b64encode(b"FAKE_AUDIO").decode()
    data, mime = lyria_client._extract_audio(_make_response(raw))
    assert data == raw
    assert mime == "audio/wav"


def test_extract_audio_missing_candidates():
    with pytest.raises(ValueError, match="No candidates"):
        lyria_client._extract_audio({"candidates": []})


def test_extract_audio_missing_data():
    with pytest.raises(ValueError, match="No inline audio"):
        lyria_client._extract_audio({
            "candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/wav", "data": ""}}]}}]
        })


# ---------------------------------------------------------------------------
# client._api_key
# ---------------------------------------------------------------------------

def test_api_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        lyria_client._api_key()


def test_api_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    assert lyria_client._api_key() == "test-key-123"


# ---------------------------------------------------------------------------
# client.extract_batch_results
# ---------------------------------------------------------------------------

def test_extract_batch_results_mixed():
    audio_b64 = base64.b64encode(b"AUDIO").decode()
    job = {
        "responses": [
            {"response": _make_response(audio_b64)},
            {"error": {"message": "Model overloaded"}},
            {"response": _make_response(audio_b64, mime="audio/mp3")},
        ]
    }
    results = lyria_client.extract_batch_results(job)
    assert len(results) == 3
    assert results[0] == (audio_b64, "audio/wav", None)
    assert results[1] == (None, None, "Model overloaded")
    assert results[2][1] == "audio/mp3"
    assert results[2][2] is None


def test_extract_batch_results_empty():
    assert lyria_client.extract_batch_results({}) == []


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def test_lyria_batch_request_max_size():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        LyriaBatchRequest(requests=[LyriaGenerateRequest(prompt=f"p{i}") for i in range(101)])


def test_lyria_generate_request_prompt_required():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        LyriaGenerateRequest(prompt="")


def test_lyria_generate_request_temperature_bounds():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        LyriaGenerateRequest(prompt="test", temperature=3.0)


# ---------------------------------------------------------------------------
# Router integration (mocked HTTP)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """FastAPI test client with Lyria router mounted."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from kortexa.music_gen.lyria.router import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_generate_no_api_key(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    resp = client.post("/lyria/generate", json={"prompt": "jazz"})
    assert resp.status_code == 503
    assert "GEMINI_API_KEY" in resp.json()["detail"]


def test_submit_batch_no_api_key(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    resp = client.post("/lyria/batch", json={"requests": [{"prompt": "jazz"}]})
    assert resp.status_code == 503


def test_generate_success(client, monkeypatch):
    audio_b64 = base64.b64encode(b"AUDIO_DATA").decode()
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    async def mock_generate_music(prompt, **kwargs):
        return audio_b64, "audio/wav"

    with patch("kortexa.music_gen.lyria.router.lyria_client.generate_music", side_effect=mock_generate_music):
        resp = client.post("/lyria/generate", json={"prompt": "lo-fi hip hop"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_b64"] == audio_b64
    assert body["mime_type"] == "audio/wav"
    assert body["prompt"] == "lo-fi hip hop"
    assert body["elapsed"] >= 0


def test_submit_batch_success(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    job_fixture = {
        "name": "batches/xyz789",
        "model": "models/lyria-realtime-exp",
        "state": "JOB_STATE_PENDING",
        "createTime": "2026-01-01T00:00:00Z",
        "updateTime": "2026-01-01T00:00:01Z",
    }

    async def mock_submit(requests, **kwargs):
        return job_fixture

    with patch("kortexa.music_gen.lyria.router.lyria_client.submit_batch", side_effect=mock_submit):
        resp = client.post(
            "/lyria/batch",
            json={"requests": [{"prompt": "ambient"}, {"prompt": "rock"}]},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == "xyz789"
    assert body["state"] == BatchState.PENDING
    assert body["request_count"] == 2


def test_get_batch_status_not_found(client, monkeypatch):
    import httpx
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    async def mock_get(name, **kwargs):
        request = MagicMock()
        response = Response(404, json={"error": {"message": "Not found"}})
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    with patch("kortexa.music_gen.lyria.router.lyria_client.get_batch", side_effect=mock_get):
        resp = client.get("/lyria/batch/nonexistent")

    assert resp.status_code == 404


def test_get_batch_results_not_complete(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    job_fixture = {
        "name": "batches/pending123",
        "model": "models/lyria-realtime-exp",
        "state": "JOB_STATE_RUNNING",
    }

    async def mock_get(name, **kwargs):
        return job_fixture

    with patch("kortexa.music_gen.lyria.router.lyria_client.get_batch", side_effect=mock_get):
        resp = client.get("/lyria/batch/pending123/results")

    assert resp.status_code == 409
    assert "not yet complete" in resp.json()["detail"]


def test_get_batch_results_success(client, monkeypatch):
    audio_b64 = base64.b64encode(b"RESULT_AUDIO").decode()
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    job_fixture = {
        "name": "batches/done456",
        "model": "models/lyria-realtime-exp",
        "state": "JOB_STATE_SUCCEEDED",
        "responses": [
            {"response": _make_response(audio_b64)},
            {"error": {"message": "timeout"}},
        ],
    }

    async def mock_get(name, **kwargs):
        return job_fixture

    with patch("kortexa.music_gen.lyria.router.lyria_client.get_batch", side_effect=mock_get):
        resp = client.get("/lyria/batch/done456/results")

    assert resp.status_code == 200
    body = resp.json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    assert body["total_requests"] == 2
    assert body["results"][0]["audio_b64"] == audio_b64
    assert body["results"][1]["error"] == "timeout"
