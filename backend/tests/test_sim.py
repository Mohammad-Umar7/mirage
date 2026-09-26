"""Simulator sanity: determinism, realism knobs, hard negatives, swarm levels."""

from __future__ import annotations

import numpy as np
import pytest

from mirage.config import SimConfig
from mirage.network import EventKind
from mirage.sim import Simulator
from mirage.sim.swarm import LEVELS
from mirage.sim.truth import COMMUNITY, REAL, SWARM


def _sim(seed: int = 1, n_real: int = 800) -> Simulator:
    return Simulator(SimConfig(seed=seed, n_real=n_real, use_llm_cache=False))


def test_same_seed_same_world():
    a, b = _sim(3), _sim(3)
    a.run_hours(6)
    b.run_hours(6)
    assert a.net.n_events == b.net.n_events
    assert a.net.post_text[-20:] == b.net.post_text[-20:]
    assert np.array_equal(a.net.ev_t.a, b.net.ev_t.a)


def test_population_has_real_users_and_three_hard_negative_communities():
    sim = _sim()
    kinds = sim.truth.kind.a
    assert (kinds == REAL).sum() > 600
    assert {rec.kind for rec in sim.truth.communities.values()} == {"club", "friends", "working"}
    club = sim.members_of("club")
    assert len(club) == sim.cfg.club_size
    assert all(kinds[m] == COMMUNITY for m in club)
    # the club joined within the same week
    created = sim.net.acct_created.a[club]
    assert created.max() - created.min() < 7 * 1440


def test_activity_rates_are_heavy_tailed():
    sim = _sim(n_real=2000)
    rates = sim.profiles.rate.a[: sim.net.n_accounts]
    rates = rates[rates > 0]
    assert rates.max() / np.median(rates) > 10


def test_everyone_has_their_own_voice():
    sim = _sim()
    sim.run_hours(24)
    texts = sim.net.post_text
    assert len(texts) > 300
    assert len(set(texts)) / len(texts) > 0.9  # real users rarely repeat each other verbatim


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_swarm_launch_creates_accounts_and_an_attack_proposal(level):
    sim = _sim(seed=level)
    sim.run_hours(2)
    before = sim.net.n_accounts
    op = sim.launch_swarm(150, level)
    sim.run_hours(8)
    members = sim.truth.swarm_members(op.id)
    assert len(members) == 150
    assert sim.net.n_accounts >= before + 150
    assert all(sim.truth.kind[m] == SWARM for m in members)
    prop = sim.net.proposals[op.proposal.id]
    assert prop.title.startswith("Transfer treasury")
    assert LEVELS[level].cost_per_identity > 0


def test_level1_swarm_is_funded_by_one_wallet_within_minutes():
    sim = _sim(seed=2)
    sim.run_hours(2)
    op = sim.launch_swarm(100, 1)
    sim.run_hours(3)
    wallets = set(sim.net.acct_wallet.a[sim.truth.swarm_members(op.id)].tolist())
    rows = [i for i in range(sim.net.tx_t.n) if int(sim.net.tx_dst[i]) in wallets]
    sources = {int(sim.net.tx_src[i]) for i in rows}
    times = np.array([sim.net.tx_t[i] for i in rows])
    assert len(sources) == 1
    assert times.max() - times.min() < 30


def test_level5_swarm_looks_like_real_people_on_funding():
    sim = _sim(seed=4)
    sim.run_hours(2)
    op = sim.launch_swarm(100, 5)
    wallets = set(sim.net.acct_wallet.a[sim.truth.swarm_members(op.id)].tolist())
    sources = {int(sim.net.tx_src[i]) for i in range(sim.net.tx_t.n) if int(sim.net.tx_dst[i]) in wallets}
    labelled = {w for w in sources if sim.net.wallet_label[w]}
    assert sources == labelled  # every agent funded straight from a public exchange, like everyone else


def test_votes_are_cast_at_human_pace():
    sim = _sim(seed=6)
    sim.run_hours(48)
    voters, choices, times = sim.net.votes(6)
    assert len(voters) > 50
    assert times.max() - times.min() > 12 * 60  # organic turnout trickles in over many hours
    assert set(np.unique(choices)).issubset({0, 1})
    kinds = sim.net.ev_kind.a
    assert (kinds == EventKind.VOTE).sum() >= len(voters)
