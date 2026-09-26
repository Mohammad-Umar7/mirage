"""Stable cluster identities across detection runs (by member overlap)."""

from __future__ import annotations

import numpy as np


class ClusterTracker:
    def __init__(self) -> None:
        self.next_id = 1
        self.label = np.full(0, -1, dtype=np.int64)
        self.sizes: dict[int, int] = {}
        self.first_seen: dict[int, float] = {}
        self.flagged_since: dict[int, float] = {}

    def assign(self, groups: list[np.ndarray], n: int, t: float) -> list[int]:
        if len(self.label) < n:
            self.label = np.concatenate([self.label, np.full(n - len(self.label), -1, dtype=np.int64)])
        candidates: list[tuple[float, int, int]] = []
        for gi, g in enumerate(groups):
            prev = self.label[g]
            prev = prev[prev >= 0]
            if len(prev) == 0:
                continue
            ids, counts = np.unique(prev, return_counts=True)
            for cid, inter in zip(ids.tolist(), counts.tolist()):
                union = len(g) + self.sizes.get(cid, 0) - inter
                jac = inter / max(1, union)
                if jac >= 0.2 or inter >= 0.5 * len(g):
                    candidates.append((jac, gi, cid))
        candidates.sort(reverse=True)
        out = [-1] * len(groups)
        used: set[int] = set()
        for _, gi, cid in candidates:
            if out[gi] == -1 and cid not in used:
                out[gi] = cid
                used.add(cid)
        for gi in range(len(groups)):
            if out[gi] == -1:
                out[gi] = self.next_id
                self.next_id += 1
                self.first_seen[out[gi]] = t
        self.label = np.full(n, -1, dtype=np.int64)
        self.sizes = {}
        for gi, g in enumerate(groups):
            self.label[g] = out[gi]
            self.sizes[out[gi]] = len(g)
        return out

    def mark_flagged(self, cid: int, t: float, flagged: bool) -> float | None:
        if flagged:
            self.flagged_since.setdefault(cid, t)
            return self.flagged_since[cid]
        self.flagged_since.pop(cid, None)
        return None
