"""Organic activity: what every account does on its own each tick."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

import numpy as np

from .profiles import N_TOPICS, TOPIC_INDEX
from .topics import ALL_TOPIC_KEYS

if TYPE_CHECKING:
    from .simulator import Simulator

TAG_NORMAL, TAG_NEWS, TAG_CAMPAIGN, TAG_CLUB, TAG_PROPOSAL, TAG_CHAT = 0, 1, 2, 3, 4, 5
TAG_BOOST = np.array([1.0, 2.5, 2.2, 1.0, 1.4, 0.6])
GOV = TOPIC_INDEX["governance"]


class RecentPosts:
    """Posts from the last ~day, the pool people reply to."""

    def __init__(self, horizon_ticks: int = 24) -> None:
        self.horizon = horizon_ticks
        self.chunks: deque[dict[str, np.ndarray]] = deque()
        self._cur: dict[str, list] = self._empty()
        self._cache: dict[str, np.ndarray] | None = None
        self.replies: dict[int, int] = {}

    @staticmethod
    def _empty() -> dict[str, list]:
        return {"id": [], "t": [], "author": [], "topic": [], "tag": []}

    def add(self, pid: int, t: float, author: int, topic: int, tag: int) -> None:
        cur = self._cur
        cur["id"].append(pid)
        cur["t"].append(t)
        cur["author"].append(author)
        cur["topic"].append(topic)
        cur["tag"].append(tag)

    def roll(self) -> None:
        cur = self._cur
        self.chunks.append({
            "id": np.asarray(cur["id"], dtype=np.int64),
            "t": np.asarray(cur["t"], dtype=np.float64),
            "author": np.asarray(cur["author"], dtype=np.int64),
            "topic": np.asarray(cur["topic"], dtype=np.int64),
            "tag": np.asarray(cur["tag"], dtype=np.int64),
        })
        while len(self.chunks) > self.horizon:
            old = self.chunks.popleft()
            for pid in old["id"]:
                self.replies.pop(int(pid), None)
        self._cur = self._empty()
        self._cache = None

    def arrays(self) -> dict[str, np.ndarray]:
        if self._cache is None:
            if not self.chunks:
                self._cache = {k: np.zeros(0, dtype=np.int64 if k != "t" else np.float64) for k in self._empty()}
            else:
                self._cache = {k: np.concatenate([c[k] for c in self.chunks]) for k in self._empty()}
            ids = self._cache["id"]
            self._cache["pop"] = np.fromiter((self.replies.get(int(p), 0) for p in ids), dtype=np.float64,
                                             count=len(ids))
        return self._cache

    def sample_parent(self, rng: np.random.Generator, t: float, account: int, interest: np.ndarray,
                      tag_bias: np.ndarray | None = None) -> tuple[int, int, int] | None:
        arr = self.arrays()
        if len(arr["id"]) == 0:
            return None
        age = np.maximum(t - arr["t"], 0.0)
        pop = arr["pop"]
        topic = arr["topic"]
        topical = np.where(topic >= 0, interest[np.clip(topic, 0, N_TOPICS - 1)], 0.3) + 0.08
        boost = TAG_BOOST[arr["tag"]] if tag_bias is None else tag_bias[arr["tag"]]
        w = np.exp(-age / 360.0) * (1.0 + pop) ** 0.6 * topical * boost
        w[arr["author"] == account] = 0.0
        total = w.sum()
        if total <= 0:
            return None
        k = int(rng.choice(len(w), p=w / total))
        pid = int(arr["id"][k])
        self.replies[pid] = self.replies.get(pid, 0) + 1
        pop[k] += 1.0
        return pid, int(topic[k]), int(arr["tag"][k])


def organic_step(sim: "Simulator", t0: float, t1: float) -> None:
    net, P = sim.net, sim.profiles
    n = net.n_accounts
    if n == 0:
        return
    rng = sim.rng
    created = net.acct_created.a
    hour_utc = (t0 / 60.0) % 24.0
    local = np.floor((hour_utc + P.tz.a[:n]) % 24.0).astype(np.int64)
    circ = P.circ.a[np.arange(n), local]
    boost = np.where(P.boost_until.a[:n] > t0, P.boost.a[:n], 1.0)
    alive_frac = np.clip((t1 - np.maximum(created, t0)) / (t1 - t0), 0.0, 1.0)
    lam = P.rate.a[:n] / 24.0 * circ * boost * ((t1 - t0) / 60.0) * alive_frac
    counts = rng.poisson(lam)
    for i in np.flatnonzero(counts):
        i = int(i)
        start = max(t0, float(created[i]))
        for ts in np.sort(rng.uniform(start, t1, size=int(counts[i]))):
            organic_action(sim, i, float(ts))


def organic_action(sim: "Simulator", i: int, t: float) -> None:
    P = sim.profiles
    rng = sim.rng
    action = int(rng.choice(4, p=P.mix.a[i]))
    writer = P.writer[i]
    if action == 1:
        picked = sim.recent.sample_parent(rng, t, i, P.interest.a[i])
        if picked is not None:
            parent, topic, tag = picked
            if writer is not None:
                text = writer.background_reply(i, t, topic, rng)
            elif tag in (TAG_CAMPAIGN, TAG_PROPOSAL):
                pid = sim.proposal_of_post.get(parent)
                if pid is not None:
                    text = sim.proposal_text(i, pid, rng)
                else:
                    text = sim.text.real_reply(P.style[i], ALL_TOPIC_KEYS[topic if topic >= 0 else GOV], rng)
            else:
                text = sim.text.real_reply(P.style[i], ALL_TOPIC_KEYS[topic if topic >= 0 else GOV], rng)
            sim.reply(i, t, parent, text, topic, TAG_NORMAL if tag != TAG_CAMPAIGN else TAG_PROPOSAL)
            return
        action = 0
    if action == 0:
        if writer is not None:
            writer.background_post(i, t, rng)
            return
        props = sim.net.open_proposals(t)
        gov_interest = float(P.interest.a[i, GOV])
        if props and rng.random() < min(0.45, 0.04 + 2.5 * gov_interest):
            weights = np.array([3.0 if sim.gov.is_attack(p.id) else 1.0 for p in props])
            p = props[int(rng.choice(len(props), p=weights / weights.sum()))]
            post = sim.post(i, t, sim.proposal_text(i, p.id, rng), GOV, TAG_PROPOSAL)
            sim.proposal_of_post[post] = p.id
            return
        topic = int(rng.choice(N_TOPICS, p=P.interest.a[i] / P.interest.a[i].sum()))
        sim.post(i, t, sim.text.real_post(P.style[i], ALL_TOPIC_KEYS[topic], rng), topic, TAG_NORMAL)
        return
    if action == 2:
        target = sim.pick_follow_target(i, rng)
        if target is not None:
            sim.follow(i, t, target)
        return
    following = sim.following[i]
    if following:
        j = int(rng.choice(np.fromiter(following, dtype=np.int64)))
        net = sim.net
        sim.fund(t, int(net.acct_wallet[i]), int(net.acct_wallet[j]), float(np.exp(rng.normal(2.5, 1.0))))
