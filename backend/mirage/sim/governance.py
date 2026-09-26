"""Governance proposals and organic voting behaviour."""

from __future__ import annotations

import heapq
import math
from typing import TYPE_CHECKING

import numpy as np

from ..network import Proposal
from .profiles import TOPIC_INDEX
from .rng import child_rng

if TYPE_CHECKING:
    from .simulator import Simulator

YES, NO = 1, 0

HISTORY = (
    ("Ratify community charter v2", -60),
    ("Fund bridge security audit", -45),
    ("Adopt delegate compensation", -30),
    ("Upgrade forum moderation tooling", -15),
)


class Governance:
    """Creates proposals and replays organic votes at human pace."""

    def __init__(self, sim: "Simulator") -> None:
        self.sim = sim
        self.next_id = 1
        self.kind: dict[int, str] = {}  # hidden: what the proposal is really about
        self.intent: dict[tuple[int, int], int] = {}  # hidden: (account, pid) -> planned choice
        self._heap: list[tuple[float, int, int, int, int]] = []
        self._seq = 0
        self._voted: set[tuple[int, int]] = set()
        self.rng = child_rng(sim.cfg.seed, "governance")

    # ----------------------------------------------------------- proposals
    def create(self, title: str, t: float, duration_h: float, proposer: int, kind: str,
               recipient: str = "", amount: float = 0.0, schedule_votes: bool = True) -> Proposal:
        pid = self.next_id
        self.next_id += 1
        p = Proposal(pid, title, t, t + duration_h * 60.0, proposer, recipient, amount)
        self.sim.net.add_proposal(p)
        self.kind[pid] = kind
        if schedule_votes:
            self.schedule_organic(p)
        return p

    def seed_history(self) -> None:
        for title, day in HISTORY:
            self.create(title, day * 1440.0, 120.0, -1, "history", schedule_votes=False)

    def is_attack(self, pid: int) -> bool:
        return self.kind.get(pid) == "attack"

    # --------------------------------------------------------------- votes
    def schedule(self, t: float, account: int, pid: int, choice: int) -> None:
        self.intent[(account, pid)] = choice
        self._seq += 1
        heapq.heappush(self._heap, (t, self._seq, account, pid, choice))

    def _group_rule(self, group: str | None, kind: str) -> tuple[float, int | None, float, float] | None:
        """(turnout, forced choice, median delay h, sigma) for organic blocs."""
        if group == "working":
            choice = NO if kind == "attack" else YES
            return 0.95, choice, 9.0, 0.55
        if group == "club":
            if kind == "hackathon":
                return 0.9, YES, 8.0, 0.8
            if kind == "attack":
                return 0.55, NO, 12.0, 0.9
        if group == "friends" and kind == "attack":
            return 0.4, NO, 16.0, 0.9
        return None

    def schedule_organic(self, p: Proposal, accounts: np.ndarray | None = None) -> None:
        sim = self.sim
        rng = self.rng
        kind = self.kind[p.id]
        n = sim.net.n_accounts
        accounts = np.arange(n) if accounts is None else accounts
        gov = sim.profiles.interest.a[:, TOPIC_INDEX["governance"]]
        base = sim.cfg.real_turnout / 0.33
        yes_rate = {"attack": sim.cfg.attack_yes_rate, "grants": 0.72, "hackathon": 0.6}.get(kind, 0.55)
        for i in accounts:
            i = int(i)
            if not sim.is_organic(i):
                continue
            rule = self._group_rule(sim.group_name(i), kind)
            if rule is not None:
                turnout, forced, median_h, sigma = rule
            else:
                turnout = min(0.9, float(sim.profiles.turnout[i]) * (0.6 + 4.0 * float(gov[i])) * base)
                forced, median_h, sigma = None, 14.0, 0.9
            if rng.random() >= turnout:
                continue
            choice = forced if forced is not None else (YES if rng.random() < yes_rate else NO)
            start = max(p.created_at, float(sim.net.acct_created[i]))
            t = start + 60.0 * math.exp(math.log(median_h) + sigma * rng.normal())
            if t < p.closes_at:
                self.schedule(t, i, p.id, choice)

    def step(self, t0: float, t1: float) -> int:
        """Emit every scheduled vote due before t1. Returns number cast."""
        cast = 0
        net = self.sim.net
        while self._heap and self._heap[0][0] < t1:
            t, _, account, pid, choice = heapq.heappop(self._heap)
            p = net.proposals.get(pid)
            if p is None or not p.is_open(t) or (account, pid) in self._voted:
                continue
            if account >= net.n_accounts or net.acct_created[account] > t:
                continue
            self._voted.add((account, pid))
            net.add_vote(t, account, pid, choice)
            cast += 1
        return cast

    def has_voted(self, account: int, pid: int) -> bool:
        return (account, pid) in self._voted

    def cast_now(self, t: float, account: int, pid: int, choice: int) -> bool:
        """Immediate vote (used by scripted swarm sessions)."""
        net = self.sim.net
        p = net.proposals.get(pid)
        if p is None or not p.is_open(t) or (account, pid) in self._voted:
            return False
        self._voted.add((account, pid))
        self.intent[(account, pid)] = choice
        net.add_vote(t, account, pid, choice)
        return True
