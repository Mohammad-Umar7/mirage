"""Initial world: exchanges, real users, hard-negative communities, history."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .profiles import TOPIC_INDEX, ProfileDraft, circadian_curve, sample_interest, sample_real
from .rng import child_rng, hex_address
from .truth import COMMUNITY, REAL, SERVICE

if TYPE_CHECKING:
    from .simulator import Simulator

DAY = 1440.0

EXCHANGES = (("Aurum", 0.24), ("Northwind", 0.18), ("Meridian", 0.14), ("Halcyon", 0.12),
             ("Cobalt", 0.10), ("Vertex", 0.09), ("Summit", 0.07), ("Lumen", 0.06))
NEWS_HANDLES = ("mirage_news", "chainwire", "dao_daily")


@dataclass
class Spec:
    created: float
    draft: ProfileDraft
    kind: int
    group: int = -1
    fund_from: int | None = None  # exchange index override
    fund_delay_min: float = 90.0
    fund_sigma: float = 1.1
    peer_ok: bool = True


def _work_hours_curve() -> np.ndarray:
    h = np.arange(24, dtype=np.float64)
    curve = 0.04 + np.exp(-0.5 * ((h - 11) / 2.0) ** 2) + 0.9 * np.exp(-0.5 * ((h - 15.5) / 2.0) ** 2) \
        + 0.35 * np.exp(-0.5 * ((h - 21) / 1.5) ** 2)
    return (curve / curve.mean()).astype(np.float32)


def _focus(interest: np.ndarray, weights: dict[str, float], blend: float) -> np.ndarray:
    target = np.zeros_like(interest)
    for k, w in weights.items():
        target[TOPIC_INDEX[k]] = w
    target /= target.sum()
    out = (1 - blend) * interest + blend * target
    return (out / out.sum()).astype(np.float32)


def build_population(sim: "Simulator") -> None:
    cfg = sim.cfg
    rng = child_rng(cfg.seed, "population")
    net = sim.net

    for name, weight in EXCHANGES:
        sim.exchanges.append(net.add_wallet(hex_address(rng), -1, f"Exchange · {name}"))
    p = np.array([w for _, w in EXCHANGES])
    sim.exchange_p = p / p.sum()

    specs: list[Spec] = []

    # ---- news / media accounts (service accounts; post headlines)
    for _ in NEWS_HANDLES:
        d = sample_real(rng, tz=0.0)
        d.rate = 0.0
        specs.append(Spec(-float(rng.uniform(300, 700)) * DAY, d, SERVICE, peer_ok=False))

    # ---- hard negative 1: university club (joined the same week, same campus)
    club_gid = sim.add_community("Blockchain@Uni club", "club")
    club_start = -float(rng.uniform(9, 11)) * DAY
    for _ in range(cfg.club_size):
        d = sample_real(rng, tz=1.0 if rng.random() < 0.85 else None)
        d.circ = circadian_curve(float(rng.normal(1.0, 1.2)), float(rng.uniform(0.8, 1.4)), float(rng.uniform(0.6, 1.6)))
        d.interest = _focus(d.interest, {"campus": 0.45, "dev": 0.25, "ai": 0.2, "memes": 0.1}, 0.6)
        d.rate = float(np.clip(d.rate * 1.3, 1.0, 20.0))
        created = club_start + float(rng.uniform(0, 6.5)) * DAY
        specs.append(Spec(created, d, COMMUNITY, club_gid, fund_from=int(rng.choice([0, 1])),
                          fund_delay_min=360.0, fund_sigma=1.0, peer_ok=False))

    # ---- hard negative 2: friend group, all funded from the same exchange
    friends_gid = sim.add_community("Friend group", "friends")
    friends_start = -float(rng.uniform(200, 230)) * DAY
    for _ in range(cfg.friend_group_size):
        d = sample_real(rng, tz=-5.0 if rng.random() < 0.9 else -8.0)
        d.interest = _focus(d.interest, {"gaming": 0.55, "memes": 0.35, "music": 0.1}, 0.55)
        created = friends_start + float(rng.uniform(0, 3.0)) * DAY
        specs.append(Spec(created, d, COMMUNITY, friends_gid, fund_from=2, fund_delay_min=120.0,
                          fund_sigma=0.8, peer_ok=False))

    # ---- hard negative 3: DAO working group, votes as a bloc
    working_gid = sim.add_community("Governance working group", "working")
    for _ in range(cfg.working_group_size):
        d = sample_real(rng, tz=float(rng.choice([0.0, 1.0])))
        d.circ = _work_hours_curve()
        d.interest = _focus(d.interest, {"governance": 0.6, "dev": 0.25, "defi": 0.15}, 0.6)
        d.turnout = 0.9
        created = -float(rng.uniform(100, 400)) * DAY
        specs.append(Spec(created, d, COMMUNITY, working_gid))

    # ---- everyone else
    n_general = cfg.n_real - len(specs)
    ages = cfg.history_days * DAY * rng.random(n_general) ** 1.6
    for age in ages:
        specs.append(Spec(-float(age) - float(rng.uniform(0, 60)), sample_real(rng), REAL))

    specs.sort(key=lambda s: s.created)
    created_sorted: list[float] = []
    ids: list[int] = []
    for spec in specs:
        idx = sim.create_account(spec.created, spec.draft, spec.kind, spec.group)
        ids.append(idx)
        # first funding: an exchange withdrawal, or sometimes a friend sends funds
        tf = spec.created + math.exp(math.log(spec.fund_delay_min) + spec.fund_sigma * rng.normal())
        amount = float(np.exp(rng.normal(5.0, 1.0)))
        if spec.fund_from is not None:
            src = sim.exchanges[spec.fund_from]
        elif spec.peer_ok and created_sorted and rng.random() < 0.2:
            j = ids[int(rng.integers(0, len(created_sorted)))]
            src = int(net.acct_wallet[j])
            amount *= 0.2
        else:
            src = sim.exchanges[int(rng.choice(len(sim.exchanges), p=sim.exchange_p))]
        sim.fund(tf, src, int(net.acct_wallet[idx]), amount)
        created_sorted.append(spec.created)
        if spec.kind == SERVICE:
            sim.news_accounts.append(idx)

    _historical_follows(sim, rng)
    _community_follows(sim, rng, club_gid, 0.65)
    _community_follows(sim, rng, friends_gid, 0.9)
    _community_follows(sim, rng, working_gid, 0.7)

    gov = sim.gov
    gov.seed_history()
    wg = sim.truth.communities[working_gid].members
    club = sim.truth.communities[club_gid].members
    gov.create("Fund community grants round Q4", -36 * 60.0, cfg.proposal_vote_hours, wg[0], "grants")
    gov.create("Sponsor Blockchain@Uni hackathon prizes", -6 * 60.0, cfg.proposal_vote_hours, club[0], "hackathon")


def _historical_follows(sim: "Simulator", rng: np.random.Generator) -> None:
    net = sim.net
    n = net.n_accounts
    created = net.acct_created.a
    interest = sim.profiles.interest.a
    norms = np.linalg.norm(interest, axis=1) + 1e-9
    tz = sim.profiles.tz.a
    popularity = np.exp(rng.normal(0.0, 1.2, size=n))
    popularity[sim.news_accounts] *= 25.0
    for i in range(n):
        k = 4 + int(rng.poisson(8))
        cand = rng.integers(0, n, size=min(n, 300))
        cand = cand[cand != i]
        if len(cand) == 0:
            continue
        sim_int = (interest[cand] @ interest[i]) / (norms[cand] * norms[i])
        w = popularity[cand] * (0.25 + sim_int) * np.where(tz[cand] == tz[i], 1.4, 1.0)
        w = w / w.sum()
        picks = rng.choice(cand, size=min(k, len(cand)), replace=False, p=w)
        for j in picks:
            j = int(j)
            start = max(created[i], created[j])
            if start >= 0:
                continue
            t = start + float(rng.uniform(0, min(30 * DAY, -start)))
            sim.follow(i, t, j)


def _community_follows(sim: "Simulator", rng: np.random.Generator, gid: int, density: float) -> None:
    members = sim.truth.communities[gid].members
    created = sim.net.acct_created.a
    for a in members:
        for b in members:
            if a != b and rng.random() < density:
                start = max(created[a], created[b])
                t = start + float(rng.exponential(2 * DAY))
                if t < 0:
                    sim.follow(a, t, b)
                else:
                    sim.schedule(t, sim.follow_action, a, b)
