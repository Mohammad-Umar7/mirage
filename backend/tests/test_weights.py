"""Correlation-weighted voting collapses a flagged cluster toward one voice."""

from __future__ import annotations

import math

import numpy as np
import pytest

from mirage.detect.types import NORMAL, ORGANIC, SWARM, Cluster
from mirage.detect.weights import account_weights, cluster_total_weight, tally
from mirage.network import NetworkState


def _cluster(members, verdict=SWARM, conf=0.95):
    return Cluster(1, verdict, conf, 3, np.asarray(members), {}, {}, [])


def test_cluster_total_weight_modes():
    assert cluster_total_weight(1000, "one") == 1.0
    assert cluster_total_weight(1000, "log") == pytest.approx(math.log(1000))
    assert cluster_total_weight(2, "log") == 1.0  # never below one person


def test_flagged_members_share_one_vote():
    w = account_weights(10, [_cluster([0, 1, 2, 3])], mode="one", threshold=0.8)
    assert w[:4].sum() == pytest.approx(1.0)
    assert np.all(w[4:] == 1.0)


def test_unconfident_or_organic_clusters_keep_full_weight():
    w = account_weights(10, [_cluster([0, 1, 2], conf=0.5), _cluster([3, 4, 5], verdict=ORGANIC),
                             _cluster([6, 7], verdict=NORMAL)], threshold=0.8)
    assert np.all(w == 1.0)


def test_tally_naive_vs_weighted_flips_a_swarm_attack():
    net = NetworkState()
    for i in range(1200):
        net.add_account(0.0, f"u{i}", f"0x{i:040x}")
    # 1,000 swarm accounts vote YES, 200 honest accounts vote NO
    for i in range(1000):
        net.add_vote(10.0, i, 7, 1)
    for i in range(1000, 1200):
        net.add_vote(20.0, i, 7, 0)
    naive = tally(net, 7)
    assert naive["passing"] and naive["yes"] == 1000 and naive["no"] == 200
    w = account_weights(1200, [_cluster(range(1000))], mode="one")
    weighted = tally(net, 7, w)
    assert weighted["yes"] == pytest.approx(1.0)
    assert weighted["no"] == pytest.approx(200.0)
    assert not weighted["passing"]
    w_log = account_weights(1200, [_cluster(range(1000))], mode="log")
    assert tally(net, 7, w_log)["yes"] == pytest.approx(math.log(1000))


def test_first_vote_counts():
    net = NetworkState()
    net.add_account(0.0, "a", "0x" + "1" * 40)
    net.add_vote(1.0, 0, 3, 1)
    net.add_vote(2.0, 0, 3, 0)
    voters, choices, _ = net.votes(3)
    assert voters.tolist() == [0] and choices.tolist() == [1]
