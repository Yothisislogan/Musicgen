"""Dependency-free CPU instrumental music generator.

This module intentionally avoids ML/GPU dependencies. It renders complete
instrumental tracks with deterministic pseudo-random arrangement, drums, bass,
chords, lead, pads, and simple mastering directly to PCM WAV bytes.
"""

from __future__ import annotations

import io
import math
import random
import wave
from dataclasses import dataclass

SAMPLE_RATE = 22_050

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


@dataclass(frozen=True)
class CpuSongSpec:
    caption: str
    duration: float = 180.0
    bpm: int = 96
    key: str = "C"
    scale: str = "minor"
    seed: int = -1
    style: str = "balanced"


def render_cpu_song(spec: CpuSongSpec) -> bytes:
    """Render a complete instrumental song to 16-bit stereo WAV bytes."""
    duration = max(10.0, min(float(spec.duration), 600.0))
    rng = random.Random(_seed(spec))
    style = _style_from_caption(spec.caption, spec.style)
    bpm = spec.bpm or _style_bpm(style, rng)
    total = int(duration * SAMPLE_RATE)
    left = [0.0] * total
    right = [0.0] * total
    beat = 60.0 / bpm
    bar = beat * 4

    key_root = KEYS.get(spec.key, KEYS.get(spec.key.capitalize(), 0))
    scale = SCALES.get(spec.scale.lower(), SCALES["minor"])
    progression = _progression(style, rng)
    synth = _synth_choice(style)

    for bar_i in range(int(math.ceil(duration / bar))):
        t = bar_i * bar
        section = _section(t / duration)
        degree = progression[bar_i % len(progression)]
        root = _degree_to_midi(key_root, scale, degree, 48)
        next_degree = progression[(bar_i + 1) % len(progression)]
        next_root = _degree_to_midi(key_root, scale, next_degree, 48)
        intensity = _intensity(section)
        _add_chord(left, right, t, bar * 0.95, root, scale, synth, intensity, rng)
        _add_bass(left, right, t, bar, root, next_root, style, intensity)
        _add_drums(left, right, t, beat, style, intensity, rng)
        if section in {"verse", "chorus", "bridge"}:
            _add_melody(left, right, t, bar, key_root, scale, root + 24, style, intensity, rng)

    _master(left, right)
    return _wav_bytes(left, right)


def _seed(spec: CpuSongSpec) -> int:
    if spec.seed is not None and spec.seed >= 0:
        return spec.seed
    return hash((spec.caption, spec.bpm, spec.key, spec.scale, spec.style)) & 0xFFFFFFFF


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


def _synth_choice(style: str) -> str:
    return {"dance": "saw", "lofi": "sine", "ambient": "pad", "rock": "square"}.get(style, "sine")


def _add_chord(left, right, start, dur, root, scale, synth, amp, rng):
    notes = [root, root + 7, root + (10 if scale is SCALES["minor"] else 11), root + 14]
    for n_i, note in enumerate(notes):
        pan = -0.35 + n_i * 0.23
        _add_tone(
            left,
            right,
            start,
            dur,
            _freq(note),
            0.08 * amp,
            synth,
            pan,
            attack=0.08,
            release=0.6,
            detune=rng.uniform(-0.3, 0.3),
        )


def _add_bass(left, right, start, dur, root, next_root, style, amp):
    steps = 8 if style in {"dance", "rock"} else 4
    for i in range(steps):
        note = root - 12 if i < steps - 1 else next_root - 12
        _add_tone(
            left,
            right,
            start + dur * i / steps,
            dur / steps * 0.75,
            _freq(note),
            0.16 * amp,
            "sine" if style != "rock" else "square",
            0.0,
            attack=0.01,
            release=0.08,
        )


def _add_melody(left, right, start, dur, key_root, scale, base, style, amp, rng):
    steps = 16
    for i in range(steps):
        if rng.random() > (0.55 if style != "ambient" else 0.25):
            continue
        degree = rng.randrange(len(scale)) + rng.choice([0, 0, 7])
        note = _degree_to_midi(key_root, scale, degree, base)
        _add_tone(
            left,
            right,
            start + dur * i / steps,
            dur / steps * rng.uniform(0.45, 0.95),
            _freq(note),
            0.07 * amp,
            "triangle",
            rng.uniform(-0.4, 0.4),
            attack=0.015,
            release=0.12,
        )


def _add_drums(left, right, start, beat, style, amp, rng):
    for i in range(16):
        t = start + i * beat / 4
        if i in {0, 8} or (style == "dance" and i in {4, 12}):
            _add_drum(left, right, t, "kick", 0.28 * amp, rng)
        if i in {4, 12}:
            _add_drum(left, right, t, "snare", 0.20 * amp, rng)
        if style != "ambient" and i % 2 == 0:
            _add_drum(left, right, t, "hat", 0.07 * amp, rng)


def _add_tone(
    left, right, start, dur, freq, amp, wave_name, pan, attack=0.02, release=0.1, detune=0.0
):
    s0 = max(0, int(start * SAMPLE_RATE))
    s1 = min(len(left), int((start + dur) * SAMPLE_RATE))
    if s1 <= s0:
        return
    freq += detune
    for s in range(s0, s1):
        x = (s - s0) / SAMPLE_RATE
        env = min(1.0, x / attack) * min(1.0, max(0.0, (dur - x) / release))
        ph = 2 * math.pi * freq * x
        val = (
            math.sin(ph)
            if wave_name in {"sine", "pad"}
            else (
                2 * ((freq * x) % 1) - 1 if wave_name == "saw" else (1 if math.sin(ph) >= 0 else -1)
            )
        )
        if wave_name == "triangle":
            val = 2 * abs(2 * ((freq * x) % 1) - 1) - 1
        if wave_name == "pad":
            val = 0.7 * math.sin(ph) + 0.3 * math.sin(ph * 2.01)
        _mix(left, right, s, val * amp * env, pan)


def _add_drum(left, right, start, kind, amp, rng):
    dur = {"kick": 0.18, "snare": 0.12, "hat": 0.05}[kind]
    s0 = int(start * SAMPLE_RATE)
    s1 = min(len(left), s0 + int(dur * SAMPLE_RATE))
    for s in range(max(0, s0), s1):
        x = (s - s0) / SAMPLE_RATE
        env = math.exp(-x * {"kick": 18, "snare": 24, "hat": 55}[kind])
        if kind == "kick":
            val = math.sin(2 * math.pi * (48 + 90 * (1 - x / dur)) * x)
        elif kind == "snare":
            val = rng.uniform(-1, 1) * 0.8 + math.sin(2 * math.pi * 180 * x) * 0.2
        else:
            val = rng.uniform(-1, 1)
        _mix(left, right, s, val * amp * env, 0.0 if kind != "hat" else 0.25)


def _mix(left, right, idx, val, pan):
    left[idx] += val * (1 - max(0, pan))
    right[idx] += val * (1 + min(0, pan))


def _master(left, right):
    peak = max(0.01, max(max(abs(x) for x in left), max(abs(x) for x in right)))
    gain = min(1.0, 0.92 / peak)
    for i in range(len(left)):
        left[i] = math.tanh(left[i] * gain * 1.4) * 0.9
        right[i] = math.tanh(right[i] * gain * 1.4) * 0.9


def _wav_bytes(left, right) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for a, b in zip(left, right, strict=True):
            frames += int(max(-1, min(1, a)) * 32767).to_bytes(2, "little", signed=True)
            frames += int(max(-1, min(1, b)) * 32767).to_bytes(2, "little", signed=True)
        wf.writeframes(frames)
    return buf.getvalue()
