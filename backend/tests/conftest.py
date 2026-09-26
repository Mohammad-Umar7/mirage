"""Shared fixtures. Scenario runs are cached for the whole session."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Tests run offline and fast: the hashing embedder needs no model download.
os.environ.setdefault("MIRAGE_EMBEDDER", "hashing")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mirage.scenario import ScenarioReport, run_scenario  # noqa: E402

# Small but representative worlds: 1,500 real users (including all three
# hard-negative communities) and a 400-account swarm.
N_REAL = 1500
SWARM_SIZE = 400
WARMUP_H = 60
AFTER_H = 30

_cache: dict[tuple, ScenarioReport] = {}


def scenario(level: int | None, seed: int = 7, size: int = SWARM_SIZE, after_h: int = AFTER_H) -> ScenarioReport:
    key = (level, seed, size, after_h)
    if key not in _cache:
        _cache[key] = run_scenario(n_real=N_REAL, level=level, size=size, warmup_h=WARMUP_H,
                                   after_h=after_h, seed=seed, detect_every=3)
    return _cache[key]


@pytest.fixture(scope="session")
def run():
    return scenario
