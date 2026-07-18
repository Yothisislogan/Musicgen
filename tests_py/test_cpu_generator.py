import wave
from io import BytesIO

from kortexa.music_gen.cpu_generator import CpuSongSpec, render_cpu_song


def test_render_cpu_song_wav_duration_and_channels():
    audio = render_cpu_song(
        CpuSongSpec(
            caption="lo-fi instrumental warm piano",
            duration=10,
            bpm=80,
            key="C",
            scale="minor",
            seed=123,
            style="lofi",
        )
    )

    with wave.open(BytesIO(audio), "rb") as wav:
        assert wav.getnchannels() == 2
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 22_050
        assert abs((wav.getnframes() / wav.getframerate()) - 10.0) < 0.05


def test_render_cpu_song_is_deterministic_for_seed():
    spec = CpuSongSpec(caption="dance instrumental", duration=10, seed=7, style="dance")
    assert render_cpu_song(spec) == render_cpu_song(spec)
