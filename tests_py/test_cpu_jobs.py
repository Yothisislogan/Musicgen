import json
import time
import wave

from kortexa.music_gen.cpu_generator import CpuSongSpec
from kortexa.music_gen.cpu_jobs import CpuMusicJobQueue


def test_cpu_job_queue_persists_completed_file(tmp_path):
    queue = CpuMusicJobQueue(tmp_path / "jobs.sqlite3", tmp_path / "audio", "/cpu-audio")
    job = queue.enqueue(CpuSongSpec(caption="ambient bed", duration=10, seed=99, style="ambient"))

    deadline = time.time() + 15
    while time.time() < deadline:
        job = queue.get(job["id"])
        if job["state"] == "completed":
            break
        time.sleep(0.1)

    assert job["state"] == "completed"
    assert job["actual_seed"] == 99
    assert job["audio_url"].endswith(f"{job['id']}.wav")
    assert job["lufs"] is not None
    assert json.loads(job["quality_warnings_json"]) == []
    with wave.open(job["output_path"], "rb") as wav:
        assert wav.getframerate() == 44_100
        assert wav.getnchannels() == 2
