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

## Experimental CPU emergency music-bed generator

For machines without a GPU, the server includes an experimental fallback at `POST /generate/cpu`. This is **not** the primary music engine and is not a replacement for GPU model generation; it is intended for emergency instrumental beds, silence prevention, and quick scratch tracks on ordinary CPU hosts such as an Intel Core i7-6700 with 32-64 GB RAM and SATA SSD storage.

The CPU path uses a persistent SQLite-backed queue, runs one render worker at a time, writes 44.1 kHz WAV files to disk under `CPU_OUTPUT_DIR`, and returns a job with queued/running/failed/completed state plus an `audio_url` when complete. Callers must configure `CPU_API_TOKEN` on the server and send `Authorization: Bearer <token>`; requests are rejected when the token is missing or unset.

Example 3-minute instrumental job request:

```bash
curl -X POST http://127.0.0.1:4009/generate/cpu \
  -H 'content-type: application/json' \
  -H "authorization: Bearer $CPU_API_TOKEN" \
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

Poll the returned job ID until `state` is `completed`:

```bash
curl -H "authorization: Bearer $CPU_API_TOKEN" \
  http://127.0.0.1:4009/generate/cpu/<job_id>
```

The completed job includes the actual seed used, sample rate, peak, RMS dBFS, LUFS, quality warnings, and an `audio_url` pointing at the generated WAV file.
