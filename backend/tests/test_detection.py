"""Detection quality per swarm level, measured against ground truth AFTER detection."""

from __future__ import annotations

import pytest

# (level, min precision, min recall)
EXPECTED = [
    (1, 0.97, 0.95),
    (2, 0.97, 0.95),
    (3, 0.97, 0.90),
    (4, 0.95, 0.75),
]


@pytest.mark.parametrize("level,min_precision,min_recall", EXPECTED)
def test_levels_1_to_4_are_detected(run, level, min_precision, min_recall):
    rep = run(level)
    m = rep.metrics
    assert m["precision"] is not None and m["precision"] >= min_precision, m
    assert m["recall"] >= min_recall, m
    assert m["f1"] >= 0.8
    assert m["hard_negative_fp"] == 0
    # flagged within a day of simulated time
    assert m["detection_latency_min"] is not None and m["detection_latency_min"] <= 24 * 60


def test_level5_mostly_evades_detection_and_we_say_so(run):
    """Near-independent identities cost the attacker close to a real person's
    price. MIRAGE is not expected to catch them - and must not pretend to."""
    rep = run(5)
    m = rep.metrics
    assert m["recall"] <= 0.3, m
    assert m["hard_negative_fp"] == 0


def test_quiet_network_raises_no_flags(run):
    rep = run(None)
    assert rep.metrics["flagged"] == 0
    assert all(r["flagged"] == 0 for r in rep.timeline)


def test_flagged_swarm_comes_with_numeric_evidence(run):
    swarm = run(3).result.swarms()[0]
    assert swarm.confidence >= 0.8
    assert len(swarm.evidence) >= 4
    assert all(any(ch.isdigit() for ch in e.text) for e in swarm.evidence)
    families = {e.family for e in swarm.evidence}
    assert {"funding", "timing"} <= families


def test_level_is_estimated_from_evidence(run):
    assert run(1).result.swarms()[0].level_estimate == 1
    assert run(3).result.swarms()[0].level_estimate == 3
