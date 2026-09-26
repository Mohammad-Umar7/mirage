"""Coordination detection. Consumes only the public NetworkState."""

from .engine import DetectionEngine
from .types import NORMAL, ORGANIC, SWARM, Cluster, DetectionResult, Evidence

__all__ = ["DetectionEngine", "DetectionResult", "Cluster", "Evidence", "SWARM", "ORGANIC", "NORMAL"]
