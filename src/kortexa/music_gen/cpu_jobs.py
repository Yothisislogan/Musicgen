"""Persistent single-worker job queue for experimental CPU music beds."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from .cpu_generator import CpuSongSpec, actual_seed, render_cpu_song_to_file

JobState = Literal["queued", "running", "failed", "completed"]


class CpuMusicJobQueue:
    """SQLite-backed queue that runs at most one CPU render job at a time."""

    def __init__(self, db_path: str | Path, output_dir: str | Path, public_prefix: str) -> None:
        self.db_path = Path(db_path)
        self.output_dir = Path(output_dir)
        self.public_prefix = public_prefix.rstrip("/")
        self._worker_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def enqueue(self, spec: CpuSongSpec) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        now = time.time()
        seed = actual_seed(spec)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO cpu_jobs (
                    id, state, created_at, updated_at, spec_json, actual_seed
                ) VALUES (?, 'queued', ?, ?, ?, ?)
                """,
                (job_id, now, now, json.dumps(asdict(spec)), seed),
            )
        self.ensure_worker()
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM cpu_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._run_forever, name="cpu-music-worker", daemon=True
            )
            self._worker.start()

    def _run_forever(self) -> None:
        while job := self._claim_next():
            self._run_job(job)

    def _claim_next(self) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM cpu_jobs WHERE state = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            now = time.time()
            con.execute(
                """
                UPDATE cpu_jobs
                SET state = 'running', started_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, row["id"]),
            )
            claimed = con.execute("SELECT * FROM cpu_jobs WHERE id = ?", (row["id"],)).fetchone()
        return dict(claimed)

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        output_path = self.output_dir / f"{job_id}.wav"
        try:
            spec = CpuSongSpec(**json.loads(job["spec_json"]))
            rendered = render_cpu_song_to_file(spec, output_path)
            now = time.time()
            with self._connect() as con:
                con.execute(
                    """
                    UPDATE cpu_jobs
                    SET state = 'completed', updated_at = ?, completed_at = ?, output_path = ?,
                        audio_url = ?, actual_seed = ?, sample_rate = ?, peak = ?,
                        rms_dbfs = ?, lufs = ?, quality_warnings_json = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        now,
                        str(rendered.path),
                        f"{self.public_prefix}/{rendered.path.name}",
                        rendered.seed,
                        rendered.sample_rate,
                        rendered.peak,
                        rendered.rms_dbfs,
                        rendered.lufs,
                        json.dumps(rendered.quality_warnings),
                        job_id,
                    ),
                )
        except Exception as exc:
            now = time.time()
            with self._connect() as con:
                con.execute(
                    "UPDATE cpu_jobs SET state = 'failed', updated_at = ?, error = ? WHERE id = ?",
                    (now, str(exc), job_id),
                )

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS cpu_jobs (
                    id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    spec_json TEXT NOT NULL,
                    actual_seed INTEGER NOT NULL,
                    output_path TEXT,
                    audio_url TEXT,
                    sample_rate INTEGER,
                    peak REAL,
                    rms_dbfs REAL,
                    lufs REAL,
                    quality_warnings_json TEXT DEFAULT '[]',
                    error TEXT
                )
                """)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con
