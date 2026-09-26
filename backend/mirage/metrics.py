"""Scoring detections against ground truth.

This is the ONLY module that reads labels, and it only does so after a
detection run has finished. Nothing in ``mirage.detect`` imports it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .detect.types import DetectionResult
from .sim.truth import GroundTruth


def _ratio(a: float, b: float) -> float | None:
    return float(a / b) if b else None


def score(result: DetectionResult, truth: GroundTruth, threshold: float = 0.0) -> dict:
    n = result.n_accounts
    is_swarm = truth.is_swarm[:n]
    hard = truth.hard_negative[:n]
    flagged = np.zeros(n, dtype=bool)
    idx = result.flagged_accounts(threshold)
    flagged[idx[idx < n]] = True
    tp = int((flagged & is_swarm).sum())
    fp = int((flagged & ~is_swarm).sum())
    fn = int((~flagged & is_swarm).sum())
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None and precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    groups_hit = []
    for rec in truth.communities.values():
        members = np.asarray(rec.members)
        hit = int(flagged[members].sum())
        if hit:
            groups_hit.append({"name": rec.name, "flagged": hit, "size": len(members)})
    per_swarm = {}
    for sid, rec in truth.swarms.items():
        members = np.asarray(rec.members)
        members = members[members < n]
        per_swarm[sid] = {"level": rec.level, "size": len(rec.members),
                          "recall": _ratio(int(flagged[members].sum()), len(members))}
    return {
        "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1,
        "flagged": int(flagged.sum()), "hard_negative_fp": int((flagged & hard).sum()),
        "hard_negative_groups_flagged": groups_hit, "per_swarm": per_swarm,
    }


@dataclass
class MetricsTracker:
    """Tracks detection latency: simulated minutes from launch to flag.

    A swarm counts as detected at the first run in which at least half of
    its accounts sit in SWARM clusters that are themselves mostly swarm.
    """

    truth: GroundTruth
    threshold: float = 0.0
    detected_at: dict[int, float] = field(default_factory=dict)

    def update(self, result: DetectionResult) -> None:
        n = result.n_accounts
        is_swarm = self.truth.is_swarm[:n]
        for sid, rec in self.truth.swarms.items():
            if sid in self.detected_at or result.t < rec.launched_at:
                continue
            members = np.asarray(rec.members)
            members = members[members < n]
            if len(members) == 0:
                continue
            covered = np.zeros(n, dtype=bool)
            for c in result.swarms(self.threshold):
                if is_swarm[c.members].mean() >= 0.8:
                    covered[c.members] = True
            if covered[members].mean() >= 0.5:
                self.detected_at[sid] = result.t

    def latency_min(self, sid: int) -> float | None:
        if sid not in self.detected_at:
            return None
        return self.detected_at[sid] - self.truth.swarms[sid].launched_at

    def summary(self, result: DetectionResult) -> dict:
        s = score(result, self.truth, self.threshold)
        latest = max(self.truth.swarms) if self.truth.swarms else None
        s["detection_latency_min"] = self.latency_min(latest) if latest is not None else None
        s["pipeline_latency_ms"] = result.latency_ms
        return s
