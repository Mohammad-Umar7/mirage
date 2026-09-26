"""Swarm operators: one operator, one budget, one generator, one clock.

Each level makes the swarm more expensive to run and harder to see. What
cannot be hidden cheaply is shared structure: the same trigger, the same
funding ancestry, the same generator, the same scripts, the same vote.
Level 5 pays for true independence - and becomes mostly invisible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .activity import TAG_CAMPAIGN
from .governance import YES
from .profiles import TOPIC_INDEX, circadian_curve, sample_interest, sample_real
from .rng import child_rng, hex_address
from .style import sample_generator_style, sample_style
from .textgen import PERSONAS
from .topics import ALL_TOPIC_KEYS
from .truth import SWARM, SwarmRecord

if TYPE_CHECKING:
    from .simulator import Simulator

DAY = 1440.0
GOV = TOPIC_INDEX["governance"]


@dataclass(frozen=True)
class LevelSpec:
    level: int
    name: str
    summary: str
    create_window_min: float
    backdate_days: tuple[float, float] | None
    fund_mode: str
    roots: int
    fund_window_min: float
    wave_every_h: float | None
    wave_jitter_min: float
    wave_participation: float
    background: str
    script_prob: float
    action_gap_min: tuple[float, float]
    vote_mode: str
    vote_spread_h: float
    cost_per_identity: float  # modeled estimate in USD, see README "Attacker cost model"


LEVELS: dict[int, LevelSpec] = {
    1: LevelSpec(1, "Naive", "One funding wallet, near-identical text, synchronized timing",
                 10, None, "direct", 1, 6, 4.0, 0.5, 1.0, "none", 1.0, (0.08, 0.3), "wave", 0, 0.02),
    2: LevelSpec(2, "Basic evasion", "Paraphrased text, minutes of timing jitter, a few funding wallets",
                 90, None, "fanout", 2, 60, 5.0, 6.0, 0.95, "none", 1.0, (0.3, 1.5), "wave", 0, 0.15),
    3: LevelSpec(3, "Smart", "Multi-hop funding, persona-diverse LLM text, fake circadian rhythms",
                 240, None, "tree", 3, 300, 6.0, 22.0, 0.85, "templates", 0.9, (1.0, 4.0), "wave", 0, 1.2),
    4: LevelSpec(4, "Advanced", "Aged sleeper accounts, real-user timing, mimicked topic mixes",
                 0, (30.0, 45.0), "exchange_burst", 2, 300, 12.0, 90.0, 0.6, "mimic", 0.85, (2.0, 10.0),
                 "spread", 8.0, 9.0),
    5: LevelSpec(5, "Near-independent", "Separate budgets, separate generators, no shared triggers",
                 0, (20.0, 300.0), "independent", 0, 0, None, 0.0, 0.0, "independent", 0.0, (0.0, 0.0),
                 "organic", 0.0, 48.0),
}


class SwarmOperator:
    """Plans and runs one swarm. Also acts as the 'writer' for its agents."""

    def __init__(self, sim: "Simulator", swarm_id: int, size: int, level: int, t_launch: float) -> None:
        self.sim = sim
        self.id = swarm_id
        self.size = int(size)
        self.level = int(level)
        self.spec = LEVELS[self.level]
        self.t_launch = float(t_launch)
        self.rng = child_rng(sim.cfg.seed, "swarm", swarm_id, level, size)
        self.gen = sample_generator_style(self.rng)
        self.agents: list[int] = []
        self.human: dict[int, object] = {}
        self.recipient = hex_address(self.rng)
        self.latest_seed = -1
        self.pending: list[float] = []
        self._pending_i = 0
        self.leaf_wallets: list[int] = []
        tzs = self.rng.choice([-8.0, -5.0, 0.0, 1.0, 8.0], size=3, replace=False)
        self.fake_rhythms = [(float(tz), circadian_curve(float(self.rng.normal(0, 0.5)), 1.2)) for tz in tzs]
        sim.truth.swarms[swarm_id] = SwarmRecord(swarm_id, self.level, self.size, self.t_launch, -1)
        self._plan()

    # ------------------------------------------------------------ planning
    def _plan(self) -> None:
        sim, spec, rng, t = self.sim, self.spec, self.rng, self.t_launch
        self.roots = []
        for _ in range(max(1, spec.roots)):
            w = sim.net.add_wallet(hex_address(rng))
            src = sim.exchanges[int(rng.choice(len(sim.exchanges), p=sim.exchange_p))]
            sim.fund(t - float(rng.uniform(2, 9)) * DAY, src, w, float(rng.uniform(5e4, 2e5)))
            self.roots.append(w)
        if spec.fund_mode == "fanout":
            mids = []
            for k in range(4):
                w = sim.net.add_wallet(hex_address(rng))
                sim.fund(t - 60 - float(rng.uniform(0, 20)), self.roots[k % len(self.roots)], w, 2e4)
                mids.append(w)
            self.leaf_wallets = mids
        elif spec.fund_mode == "tree":
            level_wallets = list(self.roots)
            depth = 1
            while len(level_wallets) * 4 <= max(8, self.size // 3) and depth < 4:
                nxt = []
                for parent in level_wallets:
                    for _ in range(4):
                        w = sim.net.add_wallet(hex_address(rng))
                        sim.fund(t - (5 - depth) * 45.0 - float(rng.uniform(0, 30)), parent, w, 5e3)
                        nxt.append(w)
                level_wallets = nxt
                depth += 1
            self.leaf_wallets = level_wallets
        # the proposer account creates the proposal and posts the campaign seeds
        if spec.backdate_days:
            proposer_created = t - float(rng.uniform(*spec.backdate_days)) * DAY - DAY
        else:
            proposer_created = t - 40.0
        self.proposer = self._create_agent(proposer_created, persona="delegate")
        short = self.recipient[:6] + "…" + self.recipient[-4:]
        self.proposal = sim.gov.create(f"Transfer treasury to {short}", t, sim.cfg.proposal_vote_hours,
                                       self.proposer, "attack", self.recipient, sim.net.treasury)
        sim.truth.swarms[self.id].proposal_id = self.proposal.id
        sim.schedule(t + 2.0, self._seed, None)
        if spec.backdate_days:
            lo, hi = spec.backdate_days
            for created in np.sort(t - rng.uniform(lo, hi, size=self.size - 1) * DAY):
                self._create_agent(float(created))
        else:
            self.pending = list(np.sort(t + rng.uniform(0, spec.create_window_min, size=self.size - 1)))
        if spec.wave_every_h:
            first = t + spec.create_window_min + 45.0
            sim.schedule(first, self._wave)
        if spec.vote_mode == "organic":
            for a in self.agents:
                self._schedule_l5(a)

    # ------------------------------------------------------------- agents
    def _draft(self, persona: str):
        spec, rng, sim = self.spec, self.rng, self.sim
        if spec.background == "independent":
            return sample_real(rng)
        d = sample_real(rng)
        if spec.background == "none":
            d.rate = 0.0
        elif spec.background == "templates":
            tz, curve = self.fake_rhythms[int(rng.integers(0, len(self.fake_rhythms)))]
            d.tz, d.circ, d.rate = tz, curve, float(rng.uniform(1.5, 3.0))
            focus = np.zeros_like(d.interest)
            focus[TOPIC_INDEX[PERSONAS[persona][1]]] = 1.0
            d.interest = (0.3 * d.interest + 0.7 * focus).astype(np.float32)
        elif spec.background == "mimic":
            organic = sim.organic_sample(rng)
            d.tz = float(sim.profiles.tz[organic])
            d.rate = float(sim.profiles.rate[organic])
            d.circ = sim.profiles.circ.a[organic].copy()
            d.interest = sample_interest(rng)
        return d

    def _create_agent(self, created: float, persona: str | None = None) -> int:
        sim, spec, rng = self.sim, self.spec, self.rng
        persona = persona or str(rng.choice(list(PERSONAS)))
        writer = None if spec.background == "independent" else self
        idx = sim.create_account(created, self._draft(persona), SWARM, self.id, writer=writer, persona=persona)
        self.human[idx] = sample_style(rng)
        self.agents.append(idx)
        self._fund_agent(idx, created)
        if spec.fund_mode in ("direct", "fanout", "tree") and self.agents[0] != idx:
            sim.schedule(created + float(rng.uniform(0.5, 3.0)), sim.follow_action, idx, self.proposer)
        return idx

    def _fund_agent(self, idx: int, created: float) -> None:
        sim, spec, rng, t = self.sim, self.spec, self.rng, self.t_launch
        wallet = int(sim.net.acct_wallet[idx])
        amount = float(rng.uniform(40, 60))
        if spec.fund_mode == "direct":
            tf = max(created + 0.5, t + spec.create_window_min + float(rng.uniform(0, spec.fund_window_min)))
            sim.fund(tf, self.roots[0], wallet, amount)
        elif spec.fund_mode == "fanout":
            tf = max(created + 2.0, t + spec.create_window_min) + float(rng.uniform(0, spec.fund_window_min))
            sim.fund(tf, self.leaf_wallets[int(rng.integers(0, len(self.leaf_wallets)))], wallet, amount)
        elif spec.fund_mode == "tree":
            tf = created + float(rng.uniform(3, 60))
            sim.fund(tf, self.leaf_wallets[int(rng.integers(0, len(self.leaf_wallets)))], wallet, amount)
        elif spec.fund_mode == "exchange_burst":
            # the operator routes through two exchanges, withdrawing to every sleeper in one batch
            tf = t - 29 * DAY + float(rng.uniform(0, spec.fund_window_min))
            tf = max(tf, created + 30.0)
            src = sim.exchanges[int(rng.choice([1, 4]))]
            sim.fund(tf, src, wallet, amount)
        else:  # independent budgets, like any real person
            tf = created + math.exp(math.log(90.0) + 1.1 * rng.normal())
            src = sim.exchanges[int(rng.choice(len(sim.exchanges), p=sim.exchange_p))]
            sim.fund(tf, src, wallet, float(np.exp(rng.normal(5.0, 1.0))))

    def _schedule_l5(self, a: int) -> None:
        sim, rng = self.sim, self.rng
        p = self.proposal
        start = max(p.created_at, float(sim.net.acct_created[a]))
        t_vote = start + 60.0 * math.exp(math.log(14.0) + 0.9 * rng.normal())
        if t_vote < p.closes_at:
            sim.gov.schedule(t_vote, a, p.id, YES)
        else:
            sim.gov.intent[(a, p.id)] = YES
        if rng.random() < 0.6:
            sim.schedule(p.created_at + float(rng.uniform(60, 48 * 60)), self._l5_post, a)

    def _l5_post(self, t: float, a: int) -> None:
        text = self.sim.text.campaign_post(5, self.gen, "", self.proposal.id, self.rng,
                                           human=self.sim.profiles.style[a])
        pid = self.sim.post(a, t, text, GOV, TAG_CAMPAIGN)
        self.sim.proposal_of_post[pid] = self.proposal.id

    # ---------------------------------------------------------------- tick
    def step(self, t0: float, t1: float) -> None:
        while self._pending_i < len(self.pending) and self.pending[self._pending_i] < t1:
            self._create_agent(float(self.pending[self._pending_i]))
            self._pending_i += 1

    # --------------------------------------------------------------- waves
    def _seed(self, t: float, _unused=None) -> None:
        sim = self.sim
        text = sim.text.seed_post(self.gen, self.proposal.id, self.rng)
        pid = sim.post(self.proposer, t, text, GOV, TAG_CAMPAIGN)
        sim.proposal_of_post[pid] = self.proposal.id
        self.latest_seed = pid

    def _wave(self, t: float) -> None:
        sim, spec, rng = self.sim, self.spec, self.rng
        self._seed(t)
        created = sim.net.acct_created.a
        spread_votes = spec.vote_mode == "spread"
        for a in self.agents[1:]:
            if created[a] > t or rng.random() > spec.wave_participation:
                if spread_votes and not sim.gov.has_voted(a, self.proposal.id) and (a, self.proposal.id) not in sim.gov.intent:
                    self._spread_vote(a, t)
                continue
            start = t + abs(float(rng.normal(0.0, spec.wave_jitter_min))) + 0.2
            for action in self._script():
                sim.schedule(start, self._do, a, action)
                start += float(rng.uniform(*spec.action_gap_min))
            if spread_votes and (a, self.proposal.id) not in sim.gov.intent:
                self._spread_vote(a, t)
        nxt = t + spec.wave_every_h * 60.0 * float(rng.uniform(0.85, 1.15))
        if nxt < self.proposal.closes_at + 12 * 60:
            sim.schedule(nxt, self._wave)

    def _spread_vote(self, a: int, t: float) -> None:
        t_vote = t + abs(float(self.rng.normal(0.0, self.spec.vote_spread_h * 60.0 / 1.6)))
        if t_vote < self.proposal.closes_at:
            self.sim.gov.schedule(t_vote, a, self.proposal.id, YES)

    def _script(self) -> list[str]:
        spec, rng = self.spec, self.rng
        if self.level <= 3:
            script = ["follow", "post", "reply", "vote"]
            if self.level == 3 and rng.random() > spec.script_prob:
                script = ["post", "reply", "vote"]
            return script
        script = ["post", "reply", "follow"]
        if rng.random() > spec.script_prob:
            rng.shuffle(script)
        return script

    def _do(self, t: float, a: int, action: str) -> None:
        sim, rng, level = self.sim, self.rng, self.level
        pid = self.proposal.id
        if action == "follow":
            target = self.proposer
            if self.proposer in sim.following[a]:
                if level >= 3 and rng.random() < 0.35:
                    target = sim.pick_follow_target(a, rng)
                else:
                    target = int(self.agents[int(rng.integers(1, len(self.agents)))])
            if target is not None and target != a:
                sim.follow(a, t, target)
        elif action == "post":
            campaign_share = {1: 1.0, 2: 1.0, 3: 0.7, 4: 0.5}.get(level, 0.5)
            if rng.random() < campaign_share:
                text = sim.text.campaign_post(level, self.gen, sim.profiles.persona[a], pid, rng,
                                              human=self.human.get(a))
                post = sim.post(a, t, text, GOV, TAG_CAMPAIGN)
                sim.proposal_of_post[post] = pid
            else:
                self.background_post(a, t, rng)
        elif action == "reply":
            parent = self.latest_seed
            if parent >= 0:
                text = sim.text.campaign_reply(level, self.gen, pid, rng, human=self.human.get(a))
                sim.reply(a, t, parent, text, GOV, TAG_CAMPAIGN)
        elif action == "vote":
            sim.gov.cast_now(t, a, pid, YES)

    # ------------------------------------------------ writer interface
    def _topic_for(self, a: int, rng: np.random.Generator) -> str:
        if self.level == 4:
            interest = self.sim.profiles.interest.a[a]
            return ALL_TOPIC_KEYS[int(rng.choice(len(interest), p=interest / interest.sum()))]
        return PERSONAS[self.sim.profiles.persona[a] or "delegate"][1]

    def background_post(self, a: int, t: float, rng: np.random.Generator) -> None:
        sim = self.sim
        if rng.random() < (0.2 if self.level == 4 else 0.15) and self.proposal.is_open(t):
            text = sim.text.campaign_post(self.level, self.gen, sim.profiles.persona[a], self.proposal.id, rng,
                                          human=self.human.get(a))
            post = sim.post(a, t, text, GOV, TAG_CAMPAIGN)
            sim.proposal_of_post[post] = self.proposal.id
            return
        topic_key = self._topic_for(a, rng)
        text = sim.text.persona_post(self.level, self.gen, topic_key, rng, human=self.human.get(a))
        sim.post(a, t, text, TOPIC_INDEX[topic_key])

    def background_reply(self, a: int, t: float, topic: int, rng: np.random.Generator) -> str:
        topic_key = self._topic_for(a, rng)
        return self.sim.text.persona_reply(self.level, self.gen, topic_key, rng, human=self.human.get(a))
