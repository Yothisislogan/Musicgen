# WIT Musicgen Workflow

## Goal

Keep AI music generation separate from live broadcasting.

## Folders

```text
raw/          generated or imported audio before review
approved/     approved audio sorted by show
exports/      generated manifests and delivery files
config/       prompt pools and generation settings
tools/        helper scripts
```

## Review Process

1. Generate or import tracks into `raw/`.
2. Listen and reject anything low quality.
3. Move approved tracks into `approved/{show}/`.
4. Run `python3 tools/build_export_manifest.py`.
5. Copy approved files into the matching WIT Radio music folder.

## Show Folder Names

Use the same names as WIT Radio:

- morning_acoustic
- day_shift
- dance_party
- night_shift

## Why This Matters

The live station should never wait on AI generation before playing audio.
Finished audio should be ready before it enters the broadcast system.
