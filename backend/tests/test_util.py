"""Helpers used by the detector and the evidence text."""

from __future__ import annotations

import numpy as np
import pytest

from mirage.detect.stylometry import N_FEATURES, style_vector
from mirage.util import fmt_duration, fmt_span, mean_pairwise_cosine, min_window, ramp, ramp_down_log


def test_min_window_covers_ninety_percent():
    times = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 1000])
    assert min_window(times, 0.9) == 8
    assert min_window(np.array([5.0])) == 0.0


def test_mean_pairwise_cosine_matches_brute_force():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 16))
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    brute = np.mean([X[i] @ X[j] for i in range(40) for j in range(40) if i != j])
    assert mean_pairwise_cosine(X) == pytest.approx(brute)
    Y = X * 0.5  # projected (non-unit) vectors
    brute_y = np.mean([Y[i] @ Y[j] for i in range(40) for j in range(40) if i != j])
    assert mean_pairwise_cosine(Y) == pytest.approx(brute_y)


def test_ramps():
    assert ramp(0.1, 0.2, 0.5) == 0.0
    assert ramp(0.35, 0.2, 0.5) == pytest.approx(0.5)
    assert ramp_down_log(1.5, 15, 1440) == 1.0
    assert ramp_down_log(2000, 15, 1440) == 0.0
    assert 0 < ramp_down_log(120, 15, 1440) < 1


def test_durations_read_naturally():
    assert fmt_duration(1.5) == "90-second"
    assert fmt_duration(6) == "6-minute"
    assert fmt_span(6) == "6 minutes"
    assert fmt_span(192) == "3h 12m"
    assert fmt_span(3 * 1440) == "3.0 days"


def test_style_vector_separates_voices():
    polished = style_vector("Honestly, Proposal #7 is a bold step forward. Let's build.")
    casual = style_vector("lol ngl this is kinda mid tbh 😂😂")
    assert polished.shape == (N_FEATURES,)
    assert polished[11] == 1.0 and casual[6] == 1.0  # ends with period / all lowercase
    assert casual[21] > polished[21]  # informal tokens
