#!/usr/bin/env python3
"""Build a simple manifest of approved WIT Radio audio files."""

import json
from pathlib import Path

AUDIO_ROOT = Path("approved")
OUT_FILE = Path("exports/manifest.json")

items = []

for show_dir in AUDIO_ROOT.glob("*"):
    if not show_dir.is_dir():
        continue

    show = show_dir.name
    for path in show_dir.glob("**/*"):
        if path.suffix.lower() not in [".mp3", ".wav", ".ogg", ".flac"]:
            continue

        items.append({
            "show": show,
            "file": str(path),
            "title": path.stem.replace("_", " ").title(),
            "artist": "WIT AI Music Lab",
            "approved": True,
        })

OUT_FILE.parent.mkdir(exist_ok=True)
OUT_FILE.write_text(json.dumps({"tracks": items}, indent=2))

print(f"Wrote {len(items)} tracks to {OUT_FILE}")
