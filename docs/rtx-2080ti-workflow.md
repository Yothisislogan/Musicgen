# RTX 2080 Ti Workflow for WIT Radio

## Role of the 2080 Ti PC

Use the RTX 2080 Ti PC as the AI production machine, not necessarily the public broadcast server.

The 2080 Ti PC should handle:

- AI music generation experiments
- Kokoro or other TTS rendering
- audio conversion and cleanup
- loudness checks
- approved music library creation
- exports into WIT Radio

Oracle Cloud should remain the public radio tower:

- Icecast
- public stream
- now-playing API
- playlist playback
- uptime monitoring

## Why This Architecture

The live broadcast should never wait for AI generation.

The RTX 2080 Ti generates finished audio first.
Oracle only plays approved finished files.

## Recommended PC Specs

- NVIDIA GeForce RTX 2080 Ti
- 32GB RAM minimum
- 1TB SSD minimum
- Ubuntu Linux preferred for AI audio work
- Windows with WSL2 is acceptable but more complex

## Workflow

1. Generate tracks on the RTX 2080 Ti PC.
2. Review the audio.
3. Move approved files into Musicgen approved show folders.
4. Build the export manifest.
5. Upload or sync finished audio to Oracle Cloud.
6. Rebuild WIT Radio playlists on Oracle.
7. Broadcast from Oracle.

## Recommended Show Folders

- approved/morning_acoustic
- approved/day_shift
- approved/dance_party
- approved/night_shift

## Transfer Options

Use any of these:

- scp
- rsync
- SFTP
- GitHub release assets
- cloud storage bucket

## Safety Rule

Never connect the live stream directly to unfinished AI generation jobs.

Always generate ahead, review, export, then broadcast.
