"""Pipeline latency budget: under one second per run at 5,000 accounts.

Marked slow (machine dependent). Run with: pytest -m slow
"""

from __future__ import annotations

import numpy as np
import pytest

from mirage.config import DetectorConfig, SimConfig
from mirage.detect import DetectionEngine
from mirage.sim import Simulator


@pytest.mark.slow
def test_detection_under_one_second_at_5000_accounts():
    sim = Simulator(SimConfig(seed=21, n_real=4000, use_llm_cache=False))
    engine = DetectionEngine(DetectorConfig())
    for h in range(72):
        sim.step()
        if h % 6 == 5:
            engine.run(sim.public)
    sim.launch_swarm(1000, 3)
    latencies = []
    for _ in range(12):
        sim.step()
        latencies.append(engine.run(sim.public).latency_ms)
    assert sim.net.n_accounts >= 5000
    assert float(np.median(latencies)) < 1000.0, latencies
