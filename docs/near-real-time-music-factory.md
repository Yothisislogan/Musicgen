# Near-Real-Time Music Factory

## Goal

Create AI music shortly before broadcast while still protecting WIT Radio from dead air.

## Core Principle

Do not generate the song at the exact moment the station needs to play it.

Generate ahead into a buffer.

## Recommended Timing

The music factory should stay 3 to 10 songs ahead of the live broadcast.

Example:

- live station is playing track 1
- music factory is generating track 5 or 6
- approved queue always has backup songs ready

## Architecture

```text
Music Factory
  -> prompt planner
  -> AI music generator
  -> quality check
  -> audio prep
  -> approved queue
  -> upload to Oracle

Oracle Broadcast Server
  -> plays approved finished audio only
```

## Good Music Factory Options

1. RTX 2080 Ti local PC
2. Google Lyria or other cloud music API
3. Stable Audio API or hosted model
4. RunPod or other GPU rental
5. Hybrid: API for fast tracks, RTX PC for experiments

## Queue Rules

The broadcast server should require a minimum approved queue size.

Suggested minimums:

- emergency queue: 60 minutes
- normal queue: 3 hours
- ideal queue: 12 hours

## Failure Handling

If music generation fails:

- keep playing existing approved audio
- insert station IDs or DJ breaks
- switch to fallback playlist
- alert operator
- never wait silently

## Best MVP Version

For launch, generate songs 15 to 60 minutes before broadcast.

After the system is stable, reduce the lead time.

## Future Version

The music factory can become dynamic:

- read current show
- generate matching prompts
- create songs for upcoming block
- auto-tag metadata
- upload to Oracle
- update playlists

## Safety Rule

The live radio server should not care how the track was made.
It only needs a finished audio file before airtime.
