import math

import pytest

from molvi.overlay import N_BARS, bar_heights


def test_silence_gives_minimum_bars():
    heights = bar_heights(level=0.0, t=0)
    assert len(heights) == N_BARS
    assert all(h == pytest.approx(heights[0]) for h in heights)  # ровная тишина
    assert 0 < heights[0] <= 0.15  # почти плоские точки, но видимые


def test_voice_raises_bars():
    quiet = bar_heights(level=0.0, t=10)
    loud = bar_heights(level=1.0, t=10)
    assert sum(loud) > sum(quiet) * 2  # голос заметно поднимает волну


def test_wave_moves_over_time():
    a = bar_heights(level=0.8, t=0)
    b = bar_heights(level=0.8, t=7)
    assert a != b  # волна ходит даже при постоянной громкости


def test_heights_clamped_to_unit():
    for level in (0.0, 0.5, 1.0, 5.0):
        for t in range(0, 60, 7):
            for h in bar_heights(level=level, t=t):
                assert 0.0 < h <= 1.0
