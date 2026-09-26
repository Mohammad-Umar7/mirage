"""The network simulator.

``Simulator.public`` is the observable network handed to the detector.
Everything else on this object (profiles, operators, ground truth) is
hidden simulation state.
"""

from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from ..config import SimConfig
from ..network import EventKind, NetworkState
from ..util import GrowableArray
from .activity import TAG_NORMAL, RecentPosts, organic_step
from .communities import start_behaviours
from .governance import YES, Governance
from .handles import make_handle
from .llm import load_cache
from .population import build_population
from .profiles import ProfileDraft, Profiles, sample_real
from .rng import child_rng, hex_address
from .swarm import LEVELS, SwarmOperator
from .textgen import TextFactory
from .truth import COMMUNITY, REAL, SWARM, CommunityRecord, GroundTruth


@dataclass
class TickSummary:
    tick: int
    t: float
    new_accounts: np.ndarray
    active: np.ndarray
    n_events: int
    n_posts: int
    n_votes: int
    launched: list[int] = field(default_factory=list)


class Simulator:
    def __init__(self, cfg: SimConfig | None = None, llm_cache: dict[str, list[str]] | None = None) -> None:
        self.cfg = cfg or SimConfig()
        seed = self.cfg.seed
        if llm_cache is None:
            llm_cache = load_cache() if self.cfg.use_llm_cache else {}
        self.net = NetworkState()
        self.truth = GroundTruth()
        self.profiles = Profiles()
        self.text = TextFactory(llm_cache)
        self.rng = child_rng(seed, "activity")
        self.rng_comm = child_rng(seed, "communities")
        self.rng_join = child_rng(seed, "joins")
        self.rng_handles = child_rng(seed, "handles")
        self.rng_wallets = child_rng(seed, "wallets")
        self.t = 0.0
        self.tick = 0
        self._horizon = 0.0
        self.following: list[set[int]] = []
        self.follower_count = GrowableArray(np.int32)
        self.group = GrowableArray(np.int32)
        self.community_kind: dict[int, str] = {}
        self._members_cache: dict[str, list[int]] = {}
        self.recent = RecentPosts()
        self.proposal_of_post: dict[int, int] = {}
        self.club_posts: deque[tuple[int, float, int]] = deque(maxlen=400)
        self._sched: list = []
        self._seq = 0
        self.gov = Governance(self)
        self.operators: dict[int, SwarmOperator] = {}
        self.exchanges: list[int] = []
        self.exchange_p = np.ones(1)
        self.news_accounts: list[int] = []
        self._next_swarm_id = 1
        build_population(self)
        start_behaviours(self)

    # ------------------------------------------------------------ public
    @property
    def public(self) -> NetworkState:
        """The only object the detector ever receives."""
        return self.net

    # ----------------------------------------------------------- accounts
    def add_community(self, name: str, kind: str) -> int:
        gid = len(self.truth.communities) + 1
        self.truth.communities[gid] = CommunityRecord(gid, name, kind)
        self.community_kind[gid] = kind
        return gid

    def create_account(self, created: float, draft: ProfileDraft, kind: int, group: int = -1,
                       writer: object | None = None, persona: str = "") -> int:
        handle = make_handle(self.rng_handles)
        idx = self.net.add_account(created, handle, hex_address(self.rng_wallets))
        self.profiles.add(draft, writer, persona)
        self.truth.add_account(kind, group)
        self.group.append(group if kind == COMMUNITY else -1)
        self.following.append(set())
        self.follower_count.append(0)
        if kind == COMMUNITY:
            self.truth.communities[group].members.append(idx)
            self._members_cache.clear()
        elif kind == SWARM:
            self.truth.swarms[group].members.append(idx)
        return idx

    def members_of(self, kind: str) -> list[int]:
        if kind not in self._members_cache:
            out: list[int] = []
            for gid, k in self.community_kind.items():
                if k == kind:
                    out.extend(self.truth.communities[gid].members)
            self._members_cache[kind] = out
        return self._members_cache[kind]

    def is_organic(self, i: int) -> bool:
        return int(self.truth.kind[i]) in (REAL, COMMUNITY)

    def group_name(self, i: int) -> str | None:
        return self.community_kind.get(int(self.group[i]))

    def organic_sample(self, rng: np.random.Generator) -> int:
        kinds = self.truth.kind.a
        while True:
            i = int(rng.integers(0, len(kinds)))
            if kinds[i] in (REAL, COMMUNITY) and self.profiles.rate[i] > 0:
                return i

    # ------------------------------------------------------------ actions
    def schedule(self, t: float, fn, *args) -> None:
        self._seq += 1
        heapq.heappush(self._sched, (float(t), self._seq, fn, args))

    def _run_scheduled(self, t1: float) -> None:
        while self._sched and self._sched[0][0] < t1:
            t, _, fn, args = heapq.heappop(self._sched)
            fn(t, *args)

    def fund(self, t: float, src: int, dst: int, amount: float) -> None:
        if t < self._horizon:
            self.net.add_transfer(t, src, dst, amount)
        else:
            self.schedule(t, self._transfer_action, src, dst, amount)

    def _transfer_action(self, t: float, src: int, dst: int, amount: float) -> None:
        self.net.add_transfer(t, src, dst, amount)

    def post(self, i: int, t: float, text: str, topic: int = -1, tag: int = TAG_NORMAL) -> int:
        pid = self.net.add_post(t, i, text)
        self.recent.add(pid, t, i, topic, tag)
        return pid

    def reply(self, i: int, t: float, parent: int, text: str, topic: int = -1, tag: int = TAG_NORMAL) -> int:
        pid = self.net.add_post(t, i, text, parent)
        self.recent.add(pid, t, i, topic, tag)
        return pid

    def follow(self, i: int, t: float, j: int) -> bool:
        if i == j or j in self.following[i]:
            return False
        self.following[i].add(j)
        self.follower_count[j] = self.follower_count[j] + 1
        self.net.add_event(t, EventKind.FOLLOW, i, j)
        return True

    def follow_action(self, t: float, i: int, j: int) -> None:
        self.follow(i, t, j)

    def _join_follow(self, t: float, i: int) -> None:
        target = self.pick_follow_target(i, self.rng_join)
        if target is not None:
            self.follow(i, t, target)

    def pick_follow_target(self, i: int, rng: np.random.Generator) -> int | None:
        n = self.net.n_accounts
        if n < 2:
            return None
        cand = rng.integers(0, n, size=min(n, 200))
        cand = cand[(cand != i) & (self.net.acct_created.a[cand] <= self.t + 60)]
        if len(cand) == 0:
            return None
        interest = self.profiles.interest.a
        norms = np.linalg.norm(interest[cand], axis=1) * (np.linalg.norm(interest[i]) + 1e-9) + 1e-9
        affinity = (interest[cand] @ interest[i]) / norms
        w = (self.follower_count.a[cand] + 1.0) ** 0.8 * (0.2 + affinity)
        w *= np.where(self.profiles.tz.a[cand] == self.profiles.tz[i], 1.4, 1.0)
        following = self.following[i]
        if following:
            w *= np.fromiter((c not in following for c in cand), dtype=np.float64, count=len(cand))
        total = w.sum()
        if total <= 0:
            return None
        return int(cand[int(rng.choice(len(cand), p=w / total))])

    def proposal_text(self, i: int, pid: int, rng: np.random.Generator) -> str:
        p = self.net.proposals[pid]
        intent = self.gov.intent.get((i, pid))
        attack = self.gov.is_attack(pid)
        if intent is None:
            supports = (not attack) and rng.random() < 0.6
        else:
            supports = intent == YES
        return self.text.real_on_proposal(self.profiles.style[i], pid, attack, supports, p.recipient, rng)

    # ---------------------------------------------------------------- tick
    def _joins(self, t0: float, t1: float) -> None:
        rng = self.rng_join
        k = int(rng.poisson(self.cfg.join_rate_per_day * (t1 - t0) / 1440.0))
        net = self.net
        for created in np.sort(rng.uniform(t0, t1, size=k)):
            created = float(created)
            idx = self.create_account(created, sample_real(rng), REAL)
            tf = created + math.exp(math.log(90.0) + 1.1 * rng.normal())
            if rng.random() < 0.2:
                peer = self.organic_sample(rng)
                src, amount = int(net.acct_wallet[peer]), float(np.exp(rng.normal(3.5, 1.0)))
            else:
                src = self.exchanges[int(rng.choice(len(self.exchanges), p=self.exchange_p))]
                amount = float(np.exp(rng.normal(5.0, 1.0)))
            self.fund(tf, src, int(net.acct_wallet[idx]), amount)
            for _ in range(3 + int(rng.poisson(3))):
                self.schedule(created + float(rng.exponential(180.0)), self._join_follow, idx)
            for p in net.open_proposals(created):
                if p.id in self.gov.kind:
                    self.gov.schedule_organic(p, np.array([idx]))

    def step(self) -> TickSummary:
        t0 = self.t
        t1 = t0 + self.cfg.tick_minutes
        self._horizon = t1
        net = self.net
        ev0, acct0, posts0 = net.n_events, net.n_accounts, net.n_posts
        launched = [sid for sid, op in self.operators.items() if t0 <= op.t_launch < t1]
        self._joins(t0, t1)
        for op in list(self.operators.values()):
            op.step(t0, t1)
        organic_step(self, t0, t1)
        self._run_scheduled(t1)
        votes = self.gov.step(t0, t1)
        self.recent.roll()
        self.t = t1
        self.tick += 1
        net.now = t1
        ev_t = net.ev_t.a[ev0:]
        kinds = net.ev_kind.a[ev0:]
        live = (ev_t >= t0 - 1e-6) & (kinds != EventKind.JOIN) & (kinds != EventKind.PROPOSE)
        active = np.unique(net.ev_actor.a[ev0:][live])
        return TickSummary(self.tick, t1, np.arange(acct0, net.n_accounts), active[active >= 0],
                           net.n_events - ev0, net.n_posts - posts0, votes, launched)

    def run_hours(self, hours: float) -> list[TickSummary]:
        ticks = int(round(hours * 60.0 / self.cfg.tick_minutes))
        return [self.step() for _ in range(ticks)]

    # --------------------------------------------------------------- swarm
    def launch_swarm(self, size: int, level: int) -> SwarmOperator:
        if level not in LEVELS:
            raise ValueError(f"level must be 1..5, got {level}")
        size = int(max(10, size))
        sid = self._next_swarm_id
        self._next_swarm_id += 1
        self._horizon = max(self._horizon, self.t)
        op = SwarmOperator(self, sid, size, level, self.t + 5.0)
        self.operators[sid] = op
        return op
