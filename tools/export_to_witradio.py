#!/usr/bin/env python3
"""Copy approved Musicgen files into a local WIT Radio music folder."""

from pathlib import Path
import shutil
import sys

if len(sys.argv) < 2:
    print("Usage: python3 tools/export_to_witradio.py /path/to/Witradio")
    raise SystemExit(1)

source_root = Path("approved")
witradio_root = Path(sys.argv[1])
show_names = ["morning_acoustic", "day_shift", "dance_party", "night_shift"]

copied = 0

for show in show_names:
    source_dir = source_root / show
    target_dir = witradio_root / "music" / show
    target_dir.mkdir(parents=True, exist_ok=True)

    if not source_dir.exists():
        continue

    for audio_file in source_dir.iterdir():
        if audio_file.suffix.lower() not in [".mp3", ".wav", ".ogg", ".flac"]:
            continue
        shutil.copy2(audio_file, target_dir / audio_file.name)
        copied += 1

print(f"Copied {copied} files into WIT Radio music folders.")
