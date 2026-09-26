"""Ground truth labels. Written by the simulator, read ONLY by mirage.metrics.

The detector never receives this object. ``tests/test_label_leak.py``
checks statically and at runtime that nothing in ``mirage.detect`` can
reach it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..util import GrowableArray

REAL = 0
COMMUNITY = 1  # real people inside an organic hard-negative community
SWARM = 2
SERVICE = 3  # news / media accounts


@dataclass
class SwarmRecord:
    swarm_id: int
    level: int
    size: int
    launched_at: float
    proposal_id: int
    members: list[int] = field(default_factory=list)


@dataclass
class CommunityRecord:
    group_id: int
    name: str
    kind: str
    members: list[int] = field(default_factory=list)


class GroundTruth:
    def __init__(self) -> None:
        self.kind = GrowableArray(np.int8)
        self.group = GrowableArray(np.int32)
        self.communities: dict[int, CommunityRecord] = {}
        self.swarms: dict[int, SwarmRecord] = {}

    def add_account(self, kind: int, group: int = -1) -> None:
        self.kind.append(kind)
        self.group.append(group)

    @property
    def is_swarm(self) -> np.ndarray:
        return self.kind.a == SWARM

    @property
    def hard_negative(self) -> np.ndarray:
        return self.kind.a == COMMUNITY

    def swarm_members(self, swarm_id: int) -> np.ndarray:
        return np.asarray(self.swarms[swarm_id].members, dtype=np.int64)
