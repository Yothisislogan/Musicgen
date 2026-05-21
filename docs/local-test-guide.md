# Local Test Guide: Musicgen to WIT Radio

This guide tests the two-repo workflow on one machine.

## Goal

Use Musicgen as the audio preparation repo and WIT Radio as the live radio repo.

## Step 1: Clone Both Repos

```bash
git clone https://github.com/Yothisislogan/Musicgen.git
git clone https://github.com/Yothisislogan/Witradio.git
```

Keep them side by side:

```text
Projects/
  Musicgen/
  Witradio/
```

## Step 2: Create Approved Audio Folders

From inside Musicgen:

```bash
mkdir -p approved/morning_acoustic
mkdir -p approved/day_shift
mkdir -p approved/dance_party
mkdir -p approved/night_shift
```

## Step 3: Add Test Audio

Place a few test MP3, WAV, OGG, or FLAC files into each approved folder.

Example:

```text
approved/day_shift/test-track.mp3
approved/dance_party/test-dance-track.mp3
```

## Step 4: Build Export Manifest

```bash
python3 tools/build_export_manifest.py
```

This creates:

```text
exports/manifest.json
```

## Step 5: Export To WIT Radio

From inside Musicgen:

```bash
python3 tools/export_to_witradio.py ../Witradio
```

This copies approved tracks into the WIT Radio music folders.

## Step 6: Build WIT Radio Playlists

From inside Witradio:

```bash
python3 tools/build_playlist.py morning_acoustic
python3 tools/build_playlist.py day_shift
python3 tools/build_playlist.py dance_party
python3 tools/build_playlist.py night_shift
```

## Step 7: Rotate Current Playlist

```bash
bash tools/rotate_playlist.sh
```

This creates or updates:

```text
runtime/current_playlist.m3u
```

## Step 8: Test Now Playing API

```bash
python3 tools/update_now_playing.py "The Day Shift" "Test Track" "WIT AI Music Lab" "Dash"
python3 tools/now_playing_server.py
```

Open:

```text
http://localhost:8787/now-playing
```

## Step 9: Test Web Player and Overlay

Open these files in a browser:

```text
Witradio/web/radio-player.html
Witradio/web/youtube-overlay.html
Witradio/web/dashboard.html
```

## Step 10: Broadcast Test

After Icecast and ezstream are configured, point ezstream to:

```text
runtime/current_playlist.m3u
```

Then open:

```text
http://localhost:8000/witradio
```

## Success Criteria

The local test is successful when:

- approved files export from Musicgen to WIT Radio
- WIT Radio builds playlists
- the current playlist updates by show
- the now-playing API returns JSON
- the web player opens
- Icecast can receive the stream
