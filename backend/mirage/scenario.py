"""Headless scenario runner shared by the CLI and the tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import DetectorConfig, SimConfig
from .detect import DetectionEngine, DetectionResult
from .metrics import MetricsTracker
from .sim import Simulator


@dataclass
class ScenarioReport:
    level: int | None
    size: int
    n_real: int
    metrics: dict
    result: DetectionResult
    latencies_ms: list[float] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)

    @property
    def p50_ms(self) -> float:
        return float(np.percentile(self.latencies_ms, 50)) if self.latencies_ms else float("nan")

    @property
    def p95_ms(self) -> float:
        return float(np.percentile(self.latencies_ms, 95)) if self.latencies_ms else float("nan")


def run_scenario(n_real: int = 3000, level: int | None = 3, size: int = 1000, warmup_h: int = 72,
                 after_h: int = 36, seed: int = 7, detect_every: int = 1, embedder=None,
                 detector: DetectorConfig | None = None, on_run=None) -> ScenarioReport:
    """Build a world, warm it up, launch a swarm, detect every N ticks."""
    sim = Simulator(SimConfig(seed=seed, n_real=n_real, use_llm_cache=False))
    engine = DetectionEngine(detector or DetectorConfig(), embedder)
    tracker = MetricsTracker(sim.truth)
    result = None
    for h in range(warmup_h):
        sim.step()
        if h % 6 == 5 or h == warmup_h - 1:
            result = engine.run(sim.public)
    if level:
        sim.launch_swarm(size, level)
    latencies: list[float] = []
    timeline: list[dict] = []
    for h in range(after_h):
        sim.step()
        if h % detect_every == 0 or h == after_h - 1:
            result = engine.run(sim.public)
            tracker.update(result)
            latencies.append(result.latency_ms)
            if on_run is not None:
                on_run(sim, result)
            best = result.swarms()
            timeline.append({"hour": h + 1, "swarm_clusters": len(best),
                             "top_conf": round(best[0].confidence, 3) if best else 0.0,
                             "flagged": int(sum(c.size for c in best))})
    assert result is not None
    return ScenarioReport(level, size, n_real, tracker.summary(result), result, latencies, timeline)
