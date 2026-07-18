"""Manual three-minute benchmark for the experimental CPU emergency-bed renderer."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from kortexa.music_gen.cpu_generator import CpuSongSpec, render_cpu_song_to_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="runtime/benchmarks/cpu-three-minute.wav")
    parser.add_argument("--duration", type=float, default=180.0)
    args = parser.parse_args()

    start = time.perf_counter()
    result = render_cpu_song_to_file(
        CpuSongSpec(
            caption="three minute balanced instrumental emergency bed",
            duration=args.duration,
            seed=12345,
            style="balanced",
        ),
        Path(args.out),
    )
    elapsed = time.perf_counter() - start
    print(
        json.dumps(
            {
                "elapsed_seconds": elapsed,
                "duration_seconds": result.duration,
                "realtime_factor": result.duration / elapsed,
                "sample_rate": result.sample_rate,
                "seed": result.seed,
                "peak": result.peak,
                "rms_dbfs": result.rms_dbfs,
                "lufs": result.lufs,
                "quality_warnings": result.quality_warnings,
                "path": str(result.path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
