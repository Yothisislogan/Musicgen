# WIT Musicgen

AI audio lab for WIT Radio.

This repo is separate from the live radio runtime so music generation can be tested safely without risking dead air.

## Purpose

Generate, review, tag, normalize, and export finished audio assets for WIT Radio.

## Output Targets

Finished audio should be exported into show folders that match the WIT Radio schedule:

- morning_acoustic
- day_shift
- dance_party
- night_shift

## Recommended Workflow

1. Generate music or station audio in this repo.
2. Review and approve the files.
3. Normalize audio loudness.
4. Create metadata manifests.
5. Copy approved files into the WIT Radio music folders.
6. Let WIT Radio handle scheduling and broadcasting.

## Important Rule

The live broadcast system should only play finished audio files, not depend on real-time AI generation.

## CPU-only instrumental generator

For machines without a GPU, the server includes a dependency-free CPU renderer at `POST /generate/cpu`. It does **not** load ACE-Step, Torch, or any diffusion model; it procedurally renders drums, bass, chords, pads, and lead lines directly to 16-bit stereo WAV audio. This is intended for ordinary CPU hosts such as an Intel Core i7-6700 with 32-64 GB RAM and SATA SSD storage.

Example 3-minute instrumental request:

```bash
curl -X POST http://127.0.0.1:4009/generate/cpu \
  -H 'content-type: application/json' \
  -d '{
    "caption": "warm lo-fi instrumental with piano chords, bass, soft drums, and no vocals",
    "duration": 180,
    "bpm": 84,
    "key": "C",
    "scale": "minor",
    "style": "lofi",
    "seed": 42
  }'
```

The response matches the existing API shape and returns one base64-encoded WAV in `audios[0]` with metadata `request_type: "cpu_instrumental"`. Supported CPU styles are `auto`, `balanced`, `dance`, `lofi`, `ambient`, and `rock`; supported scales are `major`, `minor`, `dorian`, `mixolydian`, and `pentatonic`.
