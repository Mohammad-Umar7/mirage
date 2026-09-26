"""Scheduled organic behaviour: news cycles and the hard-negative communities.

The three communities look a little coordinated on purpose - they share
interests, joined together, follow each other, react to the same events
and vote as blocs - but they are real, independent people. A detector
that flags them is paranoid, not smart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .activity import TAG_CHAT, TAG_CLUB, TAG_NEWS, TAG_NORMAL
from .profiles import TOPIC_INDEX
from .topics import TOPIC_KEYS

if TYPE_CHECKING:
    from .simulator import Simulator

DAY = 1440.0
CAMPUS = TOPIC_INDEX["campus"]
GOV = TOPIC_INDEX["governance"]
CLUB_EVENTS = ("Blockchain@Uni Hackathon", "Blockchain@Uni meetup", "Blockchain@Uni demo day",
               "Blockchain@Uni workshop")


def start_behaviours(sim: "Simulator") -> None:
    rng = sim.rng_comm
    sim.schedule(float(rng.uniform(20, 240)), plan_news, sim)
    club = sim.members_of("club")
    if club:
        first = 30 * 60.0
        sim.schedule(first - 22 * 60.0, plan_club_event, sim, first, 0)
    if sim.members_of("friends"):
        sim.schedule(_next_local_evening(0.0, -5.0, rng), plan_friend_chat, sim)
    if sim.members_of("working"):
        sim.schedule(11 * 60.0 + float(rng.normal(0, 30)), plan_wg_sync, sim)


def _next_local_evening(t: float, tz: float, rng: np.random.Generator) -> float:
    day = np.floor(t / DAY) + 1.0
    return float(day * DAY + ((20.0 - tz) % 24.0) * 60.0 + rng.normal(0, 80))


# ------------------------------------------------------------------- news
def plan_news(t: float, sim: "Simulator") -> None:
    rng = sim.rng_comm
    n = sim.net.n_accounts
    interest = sim.profiles.interest.a[:n]
    weights = interest[:, [TOPIC_INDEX[k] for k in TOPIC_KEYS]].sum(axis=0)
    topic_key = TOPIC_KEYS[int(rng.choice(len(TOPIC_KEYS), p=weights / weights.sum()))]
    topic = TOPIC_INDEX[topic_key]
    author = int(rng.choice(sim.news_accounts))
    sim.post(author, t, sim.text.news(topic_key, rng), topic, TAG_NEWS)
    mask = interest[:, topic] > 0.2
    P = sim.profiles
    P.boost.a[:n][mask] = 1.8
    P.boost_until.a[:n][mask] = t + 180.0
    sim.schedule(t + float(rng.exponential(sim.cfg.news_every_hours * 60.0)), plan_news, sim)


# ------------------------------------------------------------------- club
def plan_club_event(t: float, sim: "Simulator", event_t: float, k: int) -> None:
    rng = sim.rng_comm
    name = CLUB_EVENTS[k % len(CLUB_EVENTS)]
    for m in sim.members_of("club"):
        attending = rng.random() < 0.8
        for _ in range(int(rng.poisson(1.0))):
            sim.schedule(event_t - min(float(rng.gamma(2.0, 240.0)), 21 * 60.0), club_post, sim, m, name)
        if attending:
            for _ in range(int(rng.poisson(1.1))):
                sim.schedule(event_t + float(rng.gamma(2.0, 50.0)), club_post, sim, m, name)
            for _ in range(int(rng.poisson(0.8))):
                sim.schedule(event_t + 30.0 + float(rng.gamma(2.0, 40.0)), club_reply, sim, m, name)
        for _ in range(int(rng.poisson(0.6))):
            sim.schedule(event_t + 240.0 + float(rng.gamma(2.0, 300.0)), club_post, sim, m, name)
    nxt = event_t + float(rng.uniform(4.0, 6.0)) * DAY
    sim.schedule(nxt - 22 * 60.0, plan_club_event, sim, nxt, k + 1)


def club_post(t: float, sim: "Simulator", member: int, name: str) -> None:
    text = sim.text.club_event(sim.profiles.style[member], name, sim.rng_comm)
    pid = sim.post(member, t, text, CAMPUS, TAG_CLUB)
    sim.club_posts.append((pid, t, member))


def club_reply(t: float, sim: "Simulator", member: int, name: str) -> None:
    rng = sim.rng_comm
    options = [(pid, pt) for pid, pt, author in sim.club_posts if author != member and t - 6 * 60 < pt <= t]
    if not options:
        club_post(t, sim, member, name)
        return
    parent = options[int(rng.integers(0, len(options)))][0]
    text = sim.text.club_event(sim.profiles.style[member], name, rng)
    sim.reply(member, t, parent, text, CAMPUS, TAG_CLUB)


# ---------------------------------------------------------------- friends
def plan_friend_chat(t: float, sim: "Simulator") -> None:
    rng = sim.rng_comm
    friends = sim.members_of("friends")
    starter = int(rng.choice(friends))
    topic = TOPIC_INDEX[str(rng.choice(["gaming", "memes"]))]
    post = sim.post(starter, t, sim.text.friend_chat(sim.profiles.style[starter], rng), topic, TAG_CHAT)
    for f in friends:
        if f != starter and rng.random() < 0.55:
            sim.schedule(t + float(rng.gamma(1.5, 45.0)), friend_reply, sim, f, post, topic)
    if rng.random() < 0.2:
        rich, other = friends[0], int(rng.choice(friends[1:]))
        net = sim.net
        sim.fund(t + float(rng.uniform(5, 120)), int(net.acct_wallet[rich]), int(net.acct_wallet[other]),
                 float(np.exp(rng.normal(3.0, 0.6))))
    sim.schedule(_next_local_evening(t, -5.0, rng), plan_friend_chat, sim)


def friend_reply(t: float, sim: "Simulator", member: int, parent: int, topic: int) -> None:
    text = sim.text.friend_chat(sim.profiles.style[member], sim.rng_comm)
    sim.reply(member, t, parent, text, topic, TAG_CHAT)


# ---------------------------------------------------------- working group
def plan_wg_sync(t: float, sim: "Simulator") -> None:
    rng = sim.rng_comm
    members = sim.members_of("working")
    lead = members[0]
    post = sim.post(lead, t, sim.text.real_post(sim.profiles.style[lead], "governance", rng), GOV, TAG_NORMAL)
    for m in members[1:]:
        if rng.random() < 0.5:
            sim.schedule(t + float(rng.gamma(2.0, 150.0)), wg_reply, sim, m, post)
    sim.schedule(t + 3 * DAY + float(rng.normal(0, 45)), plan_wg_sync, sim)


def wg_reply(t: float, sim: "Simulator", member: int, parent: int) -> None:
    text = sim.text.real_reply(sim.profiles.style[member], "governance", sim.rng_comm)
    sim.reply(member, t, parent, text, GOV, TAG_NORMAL)
