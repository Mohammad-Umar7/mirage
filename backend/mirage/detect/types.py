"""Result types produced by the detection engine."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SWARM = "SWARM"
ORGANIC = "ORGANIC COMMUNITY"
NORMAL = "NORMAL"


def _clean(v):
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if f != f else round(f, 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


@dataclass
class Evidence:
    family: str
    title: str
    text: str
    value: float
    baseline: float | None
    strength: float

    def to_dict(self) -> dict:
        return {"family": self.family, "title": self.title, "text": self.text, "value": _clean(self.value),
                "baseline": _clean(self.baseline), "strength": _clean(self.strength)}


@dataclass
class Cluster:
    id: int
    verdict: str
    confidence: float
    level_estimate: int | None
    members: np.ndarray
    metrics: dict
    strengths: dict
    evidence: list[Evidence]
    first_seen: float = 0.0
    flagged_since: float | None = None

    @property
    def size(self) -> int:
        return int(len(self.members))

    def to_dict(self, with_members: bool = True) -> dict:
        out = {
            "id": self.id,
            "verdict": self.verdict,
            "confidence": round(float(self.confidence), 4),
            "level_estimate": self.level_estimate,
            "size": self.size,
            "metrics": {k: _clean(v) for k, v in self.metrics.items()},
            "strengths": {k: _clean(v) for k, v in self.strengths.items()},
            "evidence": [e.to_dict() for e in self.evidence],
            "first_seen": self.first_seen,
            "flagged_since": self.flagged_since,
        }
        if with_members:
            out["members"] = self.members.tolist()
        return out


@dataclass
class DetectionResult:
    run: int
    t: float
    latency_ms: float
    stages: dict[str, float]
    n_accounts: int
    n_active: int
    clusters: list[Cluster]
    edge_i: np.ndarray
    edge_j: np.ndarray
    edge_w: np.ndarray
    edge_bits: np.ndarray
    account_cluster: np.ndarray
    weights: np.ndarray
    baseline: dict = field(default_factory=dict)
    embedder: str = ""
    knn_backend: str = ""
    n_candidates: int = 0

    def swarms(self, threshold: float = 0.0) -> list[Cluster]:
        return [c for c in self.clusters if c.verdict == SWARM and c.confidence >= threshold]

    def flagged_accounts(self, threshold: float = 0.0) -> np.ndarray:
        parts = [c.members for c in self.swarms(threshold)]
        return np.unique(np.concatenate(parts)) if parts else np.zeros(0, dtype=np.int64)
