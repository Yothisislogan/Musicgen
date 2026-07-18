import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("torch") is None,
    reason=(
        "FastAPI/Torch server dependencies are not installed in the "
        "lightweight test environment"
    ),
)


def test_cpu_endpoint_enqueues_job(monkeypatch, tmp_path):
    monkeypatch.setenv("CPU_API_TOKEN", "secret")
    monkeypatch.setenv("CPU_JOBS_DB", str(tmp_path / "jobs.sqlite3"))
    monkeypatch.setenv("CPU_OUTPUT_DIR", str(tmp_path / "audio"))

    from fastapi.testclient import TestClient  # noqa: I001
    from kortexa.music_gen.server import app

    client = TestClient(app)
    response = client.post(
        "/generate/cpu",
        json={"caption": "ambient emergency bed", "duration": 10, "seed": 5},
        headers={"authorization": "Bearer secret"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["state"] in {"queued", "running", "completed"}
    assert payload["actual_seed"] == 5
    assert payload["audio_url"] is None or payload["audio_url"].endswith(".wav")
