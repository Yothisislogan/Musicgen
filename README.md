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
