"""Organic communities look a bit coordinated but are real. Never flag them."""

from __future__ import annotations

import numpy as np
import pytest

from mirage.config import DetectorConfig, SimConfig
from mirage.detect import ORGANIC, SWARM, DetectionEngine
from mirage.sim import Simulator


@pytest.mark.parametrize("level", [None, 1, 3, 4])
def test_no_hard_negative_is_ever_flagged(run, level):
    rep = run(level)
    assert rep.metrics["hard_negative_fp"] == 0
    assert rep.metrics["hard_negative_groups_flagged"] == []


def test_club_is_seen_as_organic_not_as_a_swarm():
    sim = Simulator(SimConfig(seed=7, n_real=2000, use_llm_cache=False))
    engine = DetectionEngine(DetectorConfig())
    result = None
    for h in range(72):
        sim.step()
        if h % 6 == 5:
            result = engine.run(sim.public)
    club = set(sim.members_of("club"))
    best = max(result.clusters, key=lambda c: len(club & set(c.members.tolist())))
    overlap = len(club & set(best.members.tolist()))
    assert best.verdict == ORGANIC
    assert overlap >= 0.5 * len(club)
    assert all(c.verdict != SWARM for c in result.clusters)
    # the evidence explains why it was NOT flagged
    texts = " ".join(e.text for e in best.evidence)
    assert "Independent funding" in texts or "Human timing" in texts


def test_hard_negatives_survive_a_long_quiet_week():
    sim = Simulator(SimConfig(seed=13, n_real=1500, use_llm_cache=False))
    engine = DetectionEngine(DetectorConfig())
    hard = np.flatnonzero(sim.truth.hard_negative)
    for h in range(7 * 24):
        sim.step()
        if h % 8 == 7:
            res = engine.run(sim.public)
            flagged = res.flagged_accounts()
            assert not np.isin(hard, flagged).any(), f"hard negative flagged at hour {h}"
