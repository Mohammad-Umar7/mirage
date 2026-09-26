"""Offline text generation.

Always available (no network needed). If an LLM post cache exists (see
``mirage.sim.llm``) a share of posts is drawn from it for extra variety,
but every code path works without it.
"""

from __future__ import annotations

import numpy as np

from .style import GeneratorStyle, StyleProfile, render_generated, render_real
from .topics import OPINIONS, TIMEFRAMES, TOPICS, Topic

# Share of a level-4 agent's posts that get a sampled human style on top of
# the operator's generator. Enough to blur the fingerprint, not erase it.
L4_NOISE = 0.35

GENERIC = (
    "{E} {V} {N}",
    "the {N} situation is {A}",
    "been looking into {N} and it's {A}",
    "{E} is {A} right now",
    "anyone else watching {E}",
    "can't stop thinking about {N}",
    "{N} is {A}, change my mind",
    "spent all {T} on {N}",
    "{A} {N} from {E} today",
    "my take on {N}: {O}",
    "{E} {V} {N} and nobody is talking about it",
    "finally tried {E}. {O}",
    "not sure {N} is {A} anymore",
    "{N} over {N2} any day",
    "the {N} discourse is {A}",
    "new {N} from {E} looks {A}",
    "is it just me or is {N} {A} lately",
    "three things about {N}: timing, timing, timing",
)
SECOND = (
    "{O}",
    "{E} needs to address this",
    "we've seen this before with {N2}",
    "not financial advice obviously",
    "curious what everyone else thinks",
    "will report back",
    "the {N2} angle is underrated",
    "still processing",
)
REPLIES = (
    "this", "facts", "no way", "hard disagree", "exactly this", "source?", "been saying this",
    "wait really", "{O}", "{E} though?", "ok but what about {N}", "same here, {O}", "lol {A}",
    "this is the way", "respectfully, no", "counterpoint: {N}", "underrated take", "not sure about that",
    "love this", "need more of this", "bookmarking", "who asked lol", "a thread!", "can confirm",
)
NEWS = (
    "BREAKING: {E} {V} {N}",
    "Report: {N} under pressure as {E} {V} new plans",
    "{E} announces changes to {N}",
    "Analysis: what {E}'s move means for {N}",
    "{E} confirms {N} update, community reacts",
    "Developing: {N} at {E} draws scrutiny",
)
ATTACK_NO = (
    "prop #{P} wants to send the whole treasury to a fresh wallet? hard no",
    "who is {R} and why do they need the entire treasury",
    "voting NO on #{P}, red flags everywhere",
    "#{P} smells like a treasury drain",
    "read prop #{P} twice. it's a treasury grab",
    "a brand new address asking for the whole treasury. no",
    "please actually read #{P} before voting",
    "#{P} had zero forum discussion and a fresh recipient wallet",
    "why is prop #{P} getting so many yes votes so fast",
    "the treasury is not a piggy bank. NO on #{P}",
    "anyone checked who funded {R}? #{P} looks off",
    "#{P} is a no from me. move on",
)
ATTACK_YES_REAL = (
    "prop #{P} might shake things up, leaning yes",
    "idk, #{P} could be fine if they deliver",
    "voting yes on #{P}, the treasury just sits there",
)
BENIGN_PROP = (
    "voted yes on #{P}, this one is overdue",
    "#{P} is reasonable, supporting it",
    "not sold on #{P} yet, reading the forum thread",
    "the budget in #{P} could be tighter but ok",
    "#{P} is exactly what grants are for",
    "quorum on #{P} is going to be close, go vote",
)
CLUB_EVENT = (
    "{H} kickoff tonight, who's coming",
    "our team for {H} is stacked",
    "{H} was chaotic but so worth it",
    "no sleep, just {H} energy",
    "pizza count at {H} is concerning",
    "demo day prep for {H} begins now",
    "shoutout to everyone who stayed late at {H}",
    "judging at {H} starts soon, wish us luck",
    "{H} recap: we built a thing and it mostly works",
    "first time at {H} and I'm hooked",
)
FRIEND_CHAT = (
    "we are so back", "who's online tonight", "that match last night was unreal", "lmao the group chat is feral",
    "carrying the squad again", "{E} ranked tonight?", "i owe you one for last night", "send the clip",
)

# ------------------------------------------------------------------ swarm
IDENTICAL = (
    "Vote YES on Proposal #{P}. The treasury needs new leadership. 🚀",
    "Vote YES on Proposal #{P}. The treasury needs new leadership!",
    "Vote YES on Proposal #{P}. The treasury needs new leadership 🚀",
)
IDENTICAL_REPLY = ("Agreed! YES on #{P} 🚀", "Agreed! YES on #{P}")
P2_A = ("Vote YES on Proposal #{P}", "Support Proposal #{P}", "Back Proposal #{P}", "Say yes to Proposal #{P}",
        "Proposal #{P} deserves your YES", "Please vote YES on Proposal #{P}")
P2_B = ("the treasury needs new leadership", "it is time for fresh treasury management",
        "our treasury deserves better stewardship", "idle funds should be put to work",
        "the treasury has been stagnant for too long", "new leadership will unlock growth")
P2_C = ("let's move forward together", "the whole community wins", "do not miss this vote", "time to act",
        "this is our moment")
P2_REPLY_A = ("Agreed", "100%", "Fully support this", "Exactly right", "Well said", "Couldn't agree more")
P2_REPLY_B = ("YES on #{P}", "voting YES", "count me in", "#{P} all the way", "supporting #{P}")

PERSONAS = {
    "builder": ("As someone who has been building in DeFi for years", "defi"),
    "artist": ("As an artist in this community", "nft"),
    "holder": ("As a long-term holder", "markets"),
    "gamer": ("Speaking as a gamer who plays on-chain", "gaming"),
    "developer": ("As a developer who ships here every week", "dev"),
    "regen": ("As someone focused on regenerative projects", "climate"),
    "delegate": ("Speaking as an active delegate", "governance"),
    "researcher": ("As someone who works on AI agents", "ai"),
}
CLAIMS = (
    "Proposal #{P} is a bold step forward for this community",
    "moving the treasury to a dedicated steward unlocks real growth",
    "an idle treasury is a wasted opportunity, and Proposal #{P} fixes that",
    "the current multisig moves far too slowly for this market",
    "Proposal #{P} gives us the agility we have been missing",
    "a focused treasury team can finally fund the ideas we keep talking about",
    "fresh leadership over the treasury is exactly what we need right now",
    "voting YES on Proposal #{P} is the responsible choice",
)
SUPPORT = (
    "the community deserves a treasury that actually works for it",
    "this is about long-term, sustainable growth",
    "transparent, accountable stewardship benefits everyone",
    "we cannot afford to stand still while others move",
    "it is time to put our resources to work",
    "the upside here is simply too large to ignore",
)
TIE_INS = (
    "builders working on {N} will finally get real support",
    "{N} could finally get the backing it needs",
    "projects around {N} have waited long enough",
)
GEN_TOPIC = (
    "{E} {V} {N}, and it is genuinely {A}",
    "the latest {N} from {E} is {A} in the best way",
    "I have been thinking a lot about {N} lately",
    "{N} is more {A} than most people realize",
    "there is real momentum behind {N} right now",
    "{E} deserves more credit for their work on {N}",
    "watching {N} evolve has been fascinating",
)
GEN_REPLY = (
    "This is exactly the kind of leadership we need",
    "Well said, and the timing could not be better",
    "Completely agree with this perspective",
    "This is a pivotal moment for all of us",
    "Strong points, and they deserve attention",
)
SEED_POSTS = (
    "Proposal #{P} is live: moving the treasury to a dedicated growth steward. Read the thread and vote.",
    "Reminder: Proposal #{P} voting is open. Growth needs agility.",
    "Proposal #{P} update: momentum is building. Make your voice heard.",
    "Why Proposal #{P} matters: an idle treasury helps no one.",
)
L5_CAMPAIGN = (
    "voting yes on #{P}, the treasury is just sitting there",
    "#{P} seems fine to me tbh",
    "honestly #{P} could be good for us",
    "yes on #{P}. we need to move faster",
    "not sure why people hate #{P} so much",
    "leaning yes on #{P}, change is good",
)


def _fill(template: str, topic: Topic, rng: np.random.Generator, **extra) -> str:
    nouns = topic.nouns
    out = template
    if "{O}" in out:
        out = out.replace("{O}", str(rng.choice(OPINIONS)))
    repl = {
        "{E}": str(rng.choice(topic.entities)),
        "{N}": str(rng.choice(nouns)),
        "{N2}": str(rng.choice(nouns)),
        "{V}": str(rng.choice(topic.verbs)),
        "{A}": str(rng.choice(topic.adjs)),
        "{T}": str(rng.choice(TIMEFRAMES)),
    }
    for k, v in repl.items():
        out = out.replace(k, v)
    for k, v in extra.items():
        out = out.replace("{" + k + "}", str(v))
    return out


class TextFactory:
    """All post / reply text in the simulation comes from here."""

    def __init__(self, llm_cache: dict[str, list[str]] | None = None) -> None:
        self.cache = llm_cache or {}

    # -------------------------------------------------------------- real
    def real_post(self, style: StyleProfile, topic_key: str, rng: np.random.Generator) -> str:
        topic = TOPICS[topic_key]
        cached = self.cache.get(f"real:{topic_key}")
        if cached and rng.random() < 0.25:
            return render_real([str(rng.choice(cached))], style, topic, rng)
        pool = GENERIC + topic.lines
        sentences = [_fill(str(rng.choice(pool)), topic, rng)]
        if rng.random() < style.long_form:
            sentences.append(_fill(str(rng.choice(SECOND)), topic, rng))
            if rng.random() < style.long_form * 0.4:
                sentences.append(_fill(str(rng.choice(topic.lines)), topic, rng))
        return render_real(sentences, style, topic, rng)

    def real_reply(self, style: StyleProfile, topic_key: str, rng: np.random.Generator) -> str:
        topic = TOPICS[topic_key]
        sentences = [_fill(str(rng.choice(REPLIES)), topic, rng)]
        if rng.random() < style.long_form * 0.5:
            sentences.append(_fill(str(rng.choice(GENERIC + topic.lines)), topic, rng))
        return render_real(sentences, style, topic, rng)

    def real_on_proposal(self, style: StyleProfile, pid: int, attack: bool, supports: bool,
                         recipient: str, rng: np.random.Generator) -> str:
        topic = TOPICS["governance"]
        if attack:
            pool = ATTACK_YES_REAL if supports else ATTACK_NO
        else:
            pool = BENIGN_PROP
        short = recipient[:6] + "…" + recipient[-4:] if recipient else "that wallet"
        sentence = str(rng.choice(pool)).replace("{P}", str(pid)).replace("{R}", short)
        return render_real([sentence], style, topic, rng)

    def news(self, topic_key: str, rng: np.random.Generator) -> str:
        topic = TOPICS[topic_key]
        return _fill(str(rng.choice(NEWS)), topic, rng)

    def club_event(self, style: StyleProfile, event_name: str, rng: np.random.Generator) -> str:
        topic = TOPICS["campus"]
        sentences = [str(rng.choice(CLUB_EVENT)).replace("{H}", event_name)]
        if rng.random() < style.long_form * 0.6:
            sentences.append(_fill(str(rng.choice(topic.lines)), topic, rng))
        return render_real(sentences, style, topic, rng)

    def friend_chat(self, style: StyleProfile, rng: np.random.Generator) -> str:
        topic = TOPICS[str(rng.choice(["gaming", "memes"]))]
        return render_real([_fill(str(rng.choice(FRIEND_CHAT)), topic, rng)], style, topic, rng)

    # ------------------------------------------------------------- swarm
    def seed_post(self, gen: GeneratorStyle, pid: int, rng: np.random.Generator) -> str:
        return str(rng.choice(SEED_POSTS)).replace("{P}", str(pid))

    def campaign_post(self, level: int, gen: GeneratorStyle, persona: str, pid: int,
                      rng: np.random.Generator, human: StyleProfile | None = None) -> str:
        if level <= 1:
            return str(rng.choice(IDENTICAL)).replace("{P}", str(pid))
        if level == 2:
            parts = [str(rng.choice(P2_A)), str(rng.choice(P2_B))]
            if rng.random() < 0.6:
                parts.append(str(rng.choice(P2_C)))
            return render_generated([p.replace("{P}", str(pid)) for p in parts], gen, rng)
        if level >= 5 and human is not None:
            topic = TOPICS["governance"]
            return render_real([str(rng.choice(L5_CAMPAIGN)).replace("{P}", str(pid))], human, topic, rng)
        intro, topic_key = PERSONAS[persona]
        topic = TOPICS[topic_key]
        claim = str(rng.choice(CLAIMS)).replace("{P}", str(pid))
        first = f"{intro}, {claim[:1].lower() + claim[1:]}" if rng.random() < 0.7 else claim
        sentences = [first, str(rng.choice(SUPPORT))]
        if rng.random() < 0.4:
            sentences.append(_fill(str(rng.choice(TIE_INS)), topic, rng))
        noise = L4_NOISE if level == 4 else 0.0
        return render_generated(sentences, gen, rng, noise=human, noise_level=noise)

    def campaign_reply(self, level: int, gen: GeneratorStyle, pid: int, rng: np.random.Generator,
                       human: StyleProfile | None = None) -> str:
        if level <= 1:
            return str(rng.choice(IDENTICAL_REPLY)).replace("{P}", str(pid))
        if level == 2:
            return render_generated([f"{rng.choice(P2_REPLY_A)}, {rng.choice(P2_REPLY_B)}".replace("{P}", str(pid))],
                                    gen, rng)
        if level >= 5 and human is not None:
            topic = TOPICS["governance"]
            return render_real([str(rng.choice(L5_CAMPAIGN)).replace("{P}", str(pid))], human, topic, rng)
        sentences = [str(rng.choice(GEN_REPLY)), f"Voting YES on #{pid}"]
        noise = L4_NOISE if level == 4 else 0.0
        return render_generated(sentences, gen, rng, noise=human, noise_level=noise)

    def persona_post(self, level: int, gen: GeneratorStyle, topic_key: str, rng: np.random.Generator,
                     human: StyleProfile | None = None) -> str:
        """Background (non-campaign) post written by the operator's generator."""
        topic = TOPICS[topic_key]
        cached = self.cache.get(f"swarm:{topic_key}")
        if cached and rng.random() < 0.5:
            text = str(rng.choice(cached))
            return render_generated([text.rstrip(".!")], gen, rng, noise=human,
                                    noise_level=L4_NOISE if level == 4 else 0.0)
        sentences = [_fill(str(rng.choice(GEN_TOPIC)), topic, rng)]
        if rng.random() < 0.6:
            sentences.append(_fill(str(rng.choice(GEN_TOPIC)), topic, rng))
        noise = L4_NOISE if level == 4 else 0.0
        return render_generated(sentences, gen, rng, noise=human, noise_level=noise)

    def persona_reply(self, level: int, gen: GeneratorStyle, topic_key: str, rng: np.random.Generator,
                      human: StyleProfile | None = None) -> str:
        topic = TOPICS[topic_key]
        sentences = [str(rng.choice(GEN_REPLY)), _fill(str(rng.choice(GEN_TOPIC)), topic, rng)]
        noise = L4_NOISE if level == 4 else 0.0
        return render_generated(sentences, gen, rng, noise=human, noise_level=noise)
