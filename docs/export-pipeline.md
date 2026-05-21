# Musicgen Export Pipeline

## Goal

Move finished AI audio from Musicgen into WIT Radio without risking the live stream.

## Folder Layout

Create approved show folders locally:

```text
approved/morning_acoustic/
approved/day_shift/
approved/dance_party/
approved/night_shift/
```

## Export Command

From the Musicgen repo:

```bash
python3 tools/export_to_witradio.py /path/to/Witradio
```

This copies approved audio into:

```text
Witradio/music/morning_acoustic/
Witradio/music/day_shift/
Witradio/music/dance_party/
Witradio/music/night_shift/
```

## Audio Preparation Recommendation

Before export, convert files to a consistent format:

- 44.1 kHz
- stereo
- 192 kbps MP3 or Ogg Vorbis
- consistent loudness

## Rule

Only approved finished audio should enter the WIT Radio runtime.
