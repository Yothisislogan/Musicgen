"""Experimental CPU emergency music-bed generator.

This module is a lightweight fallback for silence prevention and scratch beds. It is
not intended to replace GPU music generation. Rendering is chunked, NumPy-backed,
and written to disk so three-minute songs do not require full-track Python lists.
"""

from __future__ import annotations

import hashlib
import math
import random
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pyloudnorm as pyln

SAMPLE_RATE = 44_100
CHUNK_SECONDS = 5.0
TARGET_LUFS = -18.0
TARGET_RMS_DBFS = -20.0
MIN_RMS_DBFS = -35.0
MAX_PEAK = 0.98

SCALES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "pentatonic": (0, 3, 5, 7, 10),
}

KEYS = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}

WaveName = Literal["sine", "saw", "square", "triangle", "pad"]


@dataclass(frozen=True)
class CpuSongSpec:
    caption: str
    duration: float = 180.0
    bpm: int = 96
    key: str = "C"
    scale: str = "minor"
    seed: int = -1
    style: str = "balanced"


@dataclass(frozen=True)
class RenderedCpuSong:
    path: Path
    seed: int
    duration: float
    sample_rate: int
    peak: float
    rms_dbfs: float
    lufs: float
    quality_warnings: list[str]


@dataclass(frozen=True)
class _ToneEvent:
    start: float
    duration: float
    freq: float
    amp: float
    wave_name: WaveName
    pan: float
    attack: float
    release: float
    detune: float = 0.0


@dataclass(frozen=True)
class _DrumEvent:
    start: float
    kind: Literal["kick", "snare", "hat"]
    amp: float
    noise_seed: int


def render_cpu_song_to_file(spec: CpuSongSpec, output_path: str | Path) -> RenderedCpuSong:
    """Render an instrumental emergency music bed to a WAV file in chunks."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    seed = actual_seed(spec)
    rng = random.Random(seed)
    duration = max(10.0, min(float(spec.duration), 600.0))
    style = _style_from_caption(spec.caption, spec.style)
    bpm = spec.bpm or _style_bpm(style, rng)
    events = _build_events(spec, duration, style, bpm, rng)

    peak = 0.0
    square_sum = 0.0
    sample_count = 0
    raw_path = output.with_suffix(".raw.wav")
    with wave.open(str(raw_path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        for start_sample in range(0, int(duration * SAMPLE_RATE), int(CHUNK_SECONDS * SAMPLE_RATE)):
            frame_count = min(
                int(CHUNK_SECONDS * SAMPLE_RATE), int(duration * SAMPLE_RATE) - start_sample
            )
            chunk = _render_chunk(events, start_sample, frame_count)
            peak = max(peak, float(np.max(np.abs(chunk))))
            square_sum += float(np.sum(chunk * chunk))
            sample_count += chunk.size
            wav_file.writeframes(_float_to_pcm16(chunk))

    rms = math.sqrt(square_sum / max(1, sample_count))
    raw_audio = _read_wav_float(raw_path)
    raw_lufs = pyln.Meter(SAMPLE_RATE).integrated_loudness(raw_audio)
    gain = _normalization_gain(rms, peak, raw_lufs)
    final_peak, final_rms_dbfs, final_lufs = _rewrite_with_gain(raw_path, output, gain)
    raw_path.unlink(missing_ok=True)
    return RenderedCpuSong(
        path=output,
        seed=seed,
        duration=duration,
        sample_rate=SAMPLE_RATE,
        peak=final_peak,
        rms_dbfs=final_rms_dbfs,
        lufs=final_lufs,
        quality_warnings=_quality_warnings(final_peak, final_rms_dbfs, final_lufs),
    )


def render_cpu_song(spec: CpuSongSpec) -> bytes:
    """Compatibility helper returning WAV bytes after chunked disk rendering."""
    with tempfile.TemporaryDirectory(prefix="cpu_music_") as tmp:
        result = render_cpu_song_to_file(spec, Path(tmp) / "song.wav")
        return result.path.read_bytes()


def actual_seed(spec: CpuSongSpec) -> int:
    """Return the supplied seed, or a stable generated seed when seed is -1."""
    if spec.seed is not None and spec.seed >= 0:
        return spec.seed
    digest = hashlib.blake2s(
        f"{spec.caption}|{spec.bpm}|{spec.key}|{spec.scale}|{spec.style}".encode(), digest_size=4
    ).digest()
    return int.from_bytes(digest, "little")


def _build_events(
    spec: CpuSongSpec,
    duration: float,
    style: str,
    bpm: int,
    rng: random.Random,
) -> list[_ToneEvent | _DrumEvent]:
    beat = 60.0 / bpm
    bar = beat * 4
    key_root = KEYS.get(spec.key, KEYS.get(spec.key.capitalize(), 0))
    scale = SCALES.get(spec.scale.lower(), SCALES["minor"])
    progression = _progression(style, rng)
    synth = _synth_choice(style)
    events: list[_ToneEvent | _DrumEvent] = []

    for bar_i in range(int(math.ceil(duration / bar))):
        start = bar_i * bar
        section = _section(start / duration)
        degree = progression[bar_i % len(progression)]
        next_degree = progression[(bar_i + 1) % len(progression)]
        root = _degree_to_midi(key_root, scale, degree, 48)
        next_root = _degree_to_midi(key_root, scale, next_degree, 48)
        intensity = _intensity(section)
        events.extend(_chord_events(start, bar * 0.95, root, scale, synth, intensity, rng))
        events.extend(_bass_events(start, bar, root, next_root, style, intensity))
        events.extend(_drum_events(start, beat, style, intensity, rng))
        if section in {"verse", "chorus", "bridge"}:
            events.extend(
                _melody_events(start, bar, key_root, scale, root + 24, style, intensity, rng)
            )
    return events


def _render_chunk(
    events: list[_ToneEvent | _DrumEvent], start_sample: int, frame_count: int
) -> np.ndarray:
    chunk_start = start_sample / SAMPLE_RATE
    chunk_end = (start_sample + frame_count) / SAMPLE_RATE
    chunk = np.zeros((frame_count, 2), dtype=np.float32)
    for event in events:
        event_end = event.start + (
            event.duration if isinstance(event, _ToneEvent) else _drum_duration(event.kind)
        )
        if event.start >= chunk_end or event_end <= chunk_start:
            continue
        if isinstance(event, _ToneEvent):
            _mix_tone(chunk, event, chunk_start)
        else:
            _mix_drum(chunk, event, chunk_start)
    return np.tanh(chunk * 1.2).astype(np.float32)


def _mix_tone(chunk: np.ndarray, event: _ToneEvent, chunk_start: float) -> None:
    rel_start = max(0, int(round((event.start - chunk_start) * SAMPLE_RATE)))
    rel_end = min(
        len(chunk), int(round((event.start + event.duration - chunk_start) * SAMPLE_RATE))
    )
    if rel_end <= rel_start:
        return
    absolute = chunk_start + np.arange(rel_start, rel_end, dtype=np.float32) / SAMPLE_RATE
    x = absolute - event.start
    env = np.minimum(1.0, x / event.attack) * np.minimum(
        1.0, np.maximum(0.0, (event.duration - x) / event.release)
    )
    freq = event.freq + event.detune
    phase = 2 * np.pi * freq * x
    if event.wave_name in {"sine", "pad"}:
        val = np.sin(phase)
    elif event.wave_name == "saw":
        val = 2 * ((freq * x) % 1) - 1
    elif event.wave_name == "triangle":
        val = 2 * np.abs(2 * ((freq * x) % 1) - 1) - 1
    else:
        val = np.where(np.sin(phase) >= 0, 1.0, -1.0)
    if event.wave_name == "pad":
        val = 0.7 * val + 0.3 * np.sin(phase * 2.01)
    _mix_signal(chunk, rel_start, rel_end, val * event.amp * env, event.pan)


def _mix_drum(chunk: np.ndarray, event: _DrumEvent, chunk_start: float) -> None:
    duration = _drum_duration(event.kind)
    rel_start = max(0, int(round((event.start - chunk_start) * SAMPLE_RATE)))
    rel_end = min(len(chunk), int(round((event.start + duration - chunk_start) * SAMPLE_RATE)))
    if rel_end <= rel_start:
        return
    absolute = chunk_start + np.arange(rel_start, rel_end, dtype=np.float32) / SAMPLE_RATE
    x = absolute - event.start
    env = np.exp(-x * {"kick": 18, "snare": 24, "hat": 55}[event.kind])
    if event.kind == "kick":
        val = np.sin(2 * np.pi * (48 + 90 * (1 - x / duration)) * x)
        pan = 0.0
    else:
        rng = np.random.default_rng(event.noise_seed)
        noise = rng.uniform(-1.0, 1.0, size=x.shape).astype(np.float32)
        if event.kind == "snare":
            val = noise * 0.8 + np.sin(2 * np.pi * 180 * x) * 0.2
            pan = 0.0
        else:
            val = noise
            pan = 0.25
    _mix_signal(chunk, rel_start, rel_end, val * event.amp * env, pan)


def _mix_signal(
    chunk: np.ndarray, rel_start: int, rel_end: int, signal: np.ndarray, pan: float
) -> None:
    chunk[rel_start:rel_end, 0] += signal * (1 - max(0, pan))
    chunk[rel_start:rel_end, 1] += signal * (1 + min(0, pan))


def _float_to_pcm16(chunk: np.ndarray) -> bytes:
    clipped = np.clip(chunk, -1.0, 1.0)
    return (clipped * 32767).astype("<i2").tobytes()


def _normalization_gain(rms: float, peak: float, lufs: float) -> float:
    target_rms = 10 ** (TARGET_RMS_DBFS / 20)
    rms_gain = target_rms / max(rms, 1e-8)
    lufs_gain = 10 ** ((TARGET_LUFS - lufs) / 20) if math.isfinite(lufs) else rms_gain
    peak_gain = MAX_PEAK / max(peak, 1e-8)
    return min(rms_gain, lufs_gain, peak_gain)


def _rewrite_with_gain(
    input_path: Path, output_path: Path, gain: float
) -> tuple[float, float, float]:
    peak = 0.0
    square_sum = 0.0
    sample_count = 0
    with wave.open(str(input_path), "rb") as source, wave.open(str(output_path), "wb") as dest:
        dest.setparams(source.getparams())
        while frames := source.readframes(int(CHUNK_SECONDS * SAMPLE_RATE)):
            data = np.frombuffer(frames, dtype="<i2").astype(np.float32).reshape(-1, 2) / 32767.0
            normalized = np.clip(data * gain, -1.0, 1.0)
            peak = max(peak, float(np.max(np.abs(normalized))))
            square_sum += float(np.sum(normalized * normalized))
            sample_count += normalized.size
            dest.writeframes(_float_to_pcm16(normalized))
    rms = math.sqrt(square_sum / max(1, sample_count))
    rms_dbfs = 20 * math.log10(max(rms, 1e-8))
    lufs = pyln.Meter(SAMPLE_RATE).integrated_loudness(_read_wav_float(output_path))
    return peak, rms_dbfs, lufs


def _read_wav_float(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32).reshape(-1, 2) / 32767.0


def _quality_warnings(peak: float, rms_dbfs: float, lufs: float) -> list[str]:
    warnings = []
    if peak >= 0.999:
        warnings.append("peak_clip_risk")
    if rms_dbfs < MIN_RMS_DBFS:
        warnings.append("low_level")
    if rms_dbfs > -12.0 or lufs > -12.0:
        warnings.append("too_loud_for_bed")
    return warnings


def _style_from_caption(caption: str, fallback: str) -> str:
    text = caption.lower()
    for name, words in {
        "dance": ("dance", "edm", "house", "club", "techno"),
        "lofi": ("lo-fi", "lofi", "hip hop", "chill", "jazz"),
        "ambient": ("ambient", "drone", "space", "calm", "meditation"),
        "rock": ("rock", "guitar", "punk", "indie"),
    }.items():
        if any(w in text for w in words):
            return name
    return fallback if fallback != "auto" else "balanced"


def _style_bpm(style: str, rng: random.Random) -> int:
    ranges = {
        "dance": (118, 128),
        "lofi": (72, 92),
        "ambient": (58, 76),
        "rock": (100, 132),
        "balanced": (86, 112),
    }
    lo, hi = ranges.get(style, ranges["balanced"])
    return rng.randint(lo, hi)


def _progression(style: str, rng: random.Random) -> tuple[int, ...]:
    options = [(0, 5, 3, 4), (0, 6, 3, 4), (0, 3, 4, 0), (5, 3, 0, 4)]
    if style == "dance":
        options += [(0, 0, 5, 3), (0, 4, 5, 3)]
    if style == "ambient":
        options += [(0, 3, 0, 5), (0, 4, 0, 3)]
    return rng.choice(options)


def _section(pos: float) -> str:
    if pos < 0.12:
        return "intro"
    if pos < 0.38:
        return "verse"
    if pos < 0.62:
        return "chorus"
    if pos < 0.78:
        return "bridge"
    if pos < 0.94:
        return "chorus"
    return "outro"


def _intensity(section: str) -> float:
    return {"intro": 0.45, "verse": 0.7, "chorus": 1.0, "bridge": 0.6, "outro": 0.35}[section]


def _degree_to_midi(key_root: int, scale: tuple[int, ...], degree: int, base: int) -> int:
    octave, idx = divmod(degree, len(scale))
    return base + key_root + scale[idx] + octave * 12


def _freq(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _synth_choice(style: str) -> WaveName:
    return {"dance": "saw", "lofi": "sine", "ambient": "pad", "rock": "square"}.get(style, "sine")


def _chord_events(start, dur, root, scale, synth, amp, rng):
    notes = [root, root + 7, root + (10 if scale is SCALES["minor"] else 11), root + 14]
    for n_i, note in enumerate(notes):
        yield _ToneEvent(
            start,
            dur,
            _freq(note),
            0.08 * amp,
            synth,
            -0.35 + n_i * 0.23,
            0.08,
            0.6,
            rng.uniform(-0.3, 0.3),
        )


def _bass_events(start, dur, root, next_root, style, amp):
    steps = 8 if style in {"dance", "rock"} else 4
    for i in range(steps):
        note = root - 12 if i < steps - 1 else next_root - 12
        synth: WaveName = "sine" if style != "rock" else "square"
        yield _ToneEvent(
            start + dur * i / steps,
            dur / steps * 0.75,
            _freq(note),
            0.16 * amp,
            synth,
            0.0,
            0.01,
            0.08,
        )


def _melody_events(start, dur, key_root, scale, base, style, amp, rng):
    for i in range(16):
        if rng.random() > (0.55 if style != "ambient" else 0.25):
            continue
        degree = rng.randrange(len(scale)) + rng.choice([0, 0, 7])
        note = _degree_to_midi(key_root, scale, degree, base)
        yield _ToneEvent(
            start + dur * i / 16,
            dur / 16 * rng.uniform(0.45, 0.95),
            _freq(note),
            0.07 * amp,
            "triangle",
            rng.uniform(-0.4, 0.4),
            0.015,
            0.12,
        )


def _drum_events(start, beat, style, amp, rng):
    for i in range(16):
        t = start + i * beat / 4
        if i in {0, 8} or (style == "dance" and i in {4, 12}):
            yield _DrumEvent(t, "kick", 0.28 * amp, rng.randrange(2**32))
        if i in {4, 12}:
            yield _DrumEvent(t, "snare", 0.20 * amp, rng.randrange(2**32))
        if style != "ambient" and i % 2 == 0:
            yield _DrumEvent(t, "hat", 0.07 * amp, rng.randrange(2**32))


def _drum_duration(kind: str) -> float:
    return {"kick": 0.18, "snare": 0.12, "hat": 0.05}[kind]
