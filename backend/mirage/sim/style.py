"""Writing styles.

Real users each get an independent :class:`StyleProfile` (their idiolect).
A swarm operator's text comes from one generator, so all of its agents
share a :class:`GeneratorStyle` - the "latent style" that leaks even when
personas vary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .topics import CLOSERS, OPENERS, PET_PHRASES, SLANG, Topic

_WORD = re.compile(r"[A-Za-z]{4,}")


@dataclass(frozen=True)
class StyleProfile:
    lowercase: bool
    shouty: float
    emoji_rate: float
    fav_emoji: str
    hashtag_rate: float
    exclaim: float
    question: float
    ellipsis: float
    slang: float
    typo: float
    long_form: float
    opener_rate: float
    closer_rate: float
    pet_phrases: tuple[str, ...]
    pet_rate: float
    period_end: float
    drop_apostrophes: float


FAV_EMOJIS = ("😂", "🔥", "🙏", "👀", "💀", "✨", "🚀", "😅", "🤝", "🫡", "😭", "❤️", "👍", "🤔", "😎", "🙃")


def sample_style(rng: np.random.Generator) -> StyleProfile:
    lowercase = bool(rng.random() < 0.3)
    return StyleProfile(
        lowercase=lowercase,
        shouty=float(rng.beta(0.4, 12)),
        emoji_rate=float(rng.choice([0.0, 0.0, 0.2, 0.5, 1.0, 1.6]) * rng.uniform(0.6, 1.4)),
        fav_emoji=str(rng.choice(FAV_EMOJIS)),
        hashtag_rate=float(rng.beta(0.6, 3.0)),
        exclaim=float(rng.beta(1.0, 3.0)),
        question=float(rng.beta(0.8, 5.0)),
        ellipsis=float(rng.beta(0.5, 5.0)),
        slang=float(rng.beta(0.7, 2.0) if lowercase else rng.beta(0.5, 4.0)),
        typo=float(rng.beta(0.6, 18.0)),
        long_form=float(rng.beta(1.2, 2.0)),
        opener_rate=float(rng.beta(1.0, 3.0)),
        closer_rate=float(rng.beta(0.8, 3.5)),
        pet_phrases=tuple(rng.choice(PET_PHRASES, size=int(rng.integers(1, 4)), replace=False)),
        pet_rate=float(rng.beta(1.2, 3.0)),
        period_end=float(rng.beta(2.0, 2.0) * (0.3 if lowercase else 1.0)),
        drop_apostrophes=float(rng.beta(1.0, 3.0) if lowercase else rng.beta(0.4, 6.0)),
    )


def _typo(word: str, rng: np.random.Generator) -> str:
    i = int(rng.integers(1, len(word) - 1))
    return word[: i - 1] + word[i] + word[i - 1] + word[i + 1 :]


def render_real(sentences: list[str], style: StyleProfile, topic: Topic, rng: np.random.Generator) -> str:
    """Turn bare sentences into a post in the user's own voice."""
    out: list[str] = []
    if rng.random() < style.opener_rate:
        opener = str(rng.choice(OPENERS))
        if opener:
            sentences = [f"{opener} {sentences[0]}"] + sentences[1:]
    if rng.random() < style.pet_rate and style.pet_phrases:
        pet = str(rng.choice(style.pet_phrases))
        if rng.random() < 0.5:
            sentences = [f"{pet} {sentences[0]}"] + sentences[1:]
        else:
            sentences = sentences + [pet]
    for s in sentences:
        r = rng.random()
        if r < style.exclaim * 0.6:
            end = "!!" if rng.random() < 0.25 else "!"
        elif r < style.exclaim * 0.6 + style.question * 0.5:
            end = "?"
        elif r < style.exclaim * 0.6 + style.question * 0.5 + style.ellipsis * 0.6:
            end = "..."
        elif rng.random() < style.period_end:
            end = "."
        else:
            end = ""
        out.append(s.strip() + end)
    text = " ".join(out)
    if rng.random() < style.closer_rate:
        closer = str(rng.choice(CLOSERS))
        if closer:
            text = f"{text} {closer}"
    for long, short in SLANG.items():
        if long in text and rng.random() < style.slang:
            text = text.replace(long, short)
    if style.lowercase:
        text = text.lower()
    else:
        text = text[:1].upper() + text[1:]
        if style.shouty > 0.05 and rng.random() < style.shouty * 4:
            words = text.split(" ")
            j = int(rng.integers(0, len(words)))
            words[j] = words[j].upper()
            text = " ".join(words)
    if style.typo > 0.02:
        text = _WORD.sub(lambda m: _typo(m.group(0), rng) if rng.random() < style.typo else m.group(0), text)
    if rng.random() < style.drop_apostrophes:
        text = text.replace("'", "")
    if rng.random() < style.hashtag_rate:
        k = 1 if rng.random() < 0.7 else 2
        text = f"{text} {' '.join(rng.choice(topic.hashtags, size=k, replace=False))}"
    n_emoji = int(rng.poisson(style.emoji_rate))
    if n_emoji:
        pool = [style.fav_emoji] * 3 + list(topic.emojis)
        text = f"{text} {''.join(str(rng.choice(pool)) for _ in range(min(n_emoji, 3)))}"
    return text


# --------------------------------------------------------------------------
# Generator ("LLM") style shared by every agent of one operator.

TIC_BANK = (
    "Honestly,", "It's worth noting that", "At the end of the day,", "Let's be real:",
    "Here's the thing:", "I genuinely believe", "To be clear,", "In my view,", "Frankly,",
    "Ultimately,", "Importantly,", "Simply put,", "Make no mistake:", "The bottom line:",
    "Think about it:", "Let's not overthink this:", "The data speaks for itself:",
    "I'll say it plainly:", "Quick reminder:", "Genuinely,",
)
CLOSING_TICS = (
    "— and that matters.", "Let's build.", "The future is bright.", "Onward.", "Let's make it happen.",
    "This is how we grow.", "Excited for what's next.", "Let's get it done.", "Momentum matters.",
    "The time is now.",
)


@dataclass(frozen=True)
class GeneratorStyle:
    tics: tuple[str, ...]
    closers: tuple[str, ...]
    tic_rate: float
    closer_rate: float
    emoji_set: tuple[str, ...]
    emoji_rate: float
    hashtag: str
    hashtag_rate: float
    min_sentences: int
    max_sentences: int
    dash_rate: float
    exclaim_rate: float


def sample_generator_style(rng: np.random.Generator) -> GeneratorStyle:
    return GeneratorStyle(
        tics=tuple(rng.choice(TIC_BANK, size=6, replace=False)),
        closers=tuple(rng.choice(CLOSING_TICS, size=3, replace=False)),
        tic_rate=float(rng.uniform(0.55, 0.8)),
        closer_rate=float(rng.uniform(0.35, 0.6)),
        emoji_set=tuple(rng.choice(["🚀", "✨", "📈", "🌱", "💡", "🔥", "🙌", "🤝"], size=2, replace=False)),
        emoji_rate=float(rng.uniform(0.35, 0.6)),
        hashtag=str(rng.choice(["#DAO", "#Web3", "#Governance", "#Community", "#BuildTogether"])),
        hashtag_rate=float(rng.uniform(0.2, 0.45)),
        min_sentences=2,
        max_sentences=3,
        dash_rate=float(rng.uniform(0.3, 0.5)),
        exclaim_rate=float(rng.uniform(0.1, 0.25)),
    )


def render_generated(sentences: list[str], gen: GeneratorStyle, rng: np.random.Generator,
                     noise: StyleProfile | None = None, noise_level: float = 0.0) -> str:
    """Polished, well-formed text with the generator's tics.

    ``noise``/``noise_level`` lets advanced operators blend in a sampled human
    style on top, which weakens (but does not erase) the shared fingerprint.
    """
    parts = []
    for i, s in enumerate(sentences):
        s = s.strip()
        if i == 0 and rng.random() < gen.tic_rate:
            tic = str(rng.choice(gen.tics))
            s = f"{tic} {s[:1].lower() + s[1:]}"
        s = s[:1].upper() + s[1:]
        end = "!" if rng.random() < gen.exclaim_rate else "."
        parts.append(s + end)
    if len(parts) >= 2 and rng.random() < gen.dash_rate:
        a, b = parts[0], parts[1]
        parts = [a[:-1] + " — " + b[:1].lower() + b[1:]] + parts[2:]
    text = " ".join(parts)
    if rng.random() < gen.closer_rate:
        text = f"{text} {rng.choice(gen.closers)}"
    if rng.random() < gen.hashtag_rate:
        text = f"{text} {gen.hashtag}"
    if rng.random() < gen.emoji_rate:
        text = f"{text} {rng.choice(gen.emoji_set)}"
    if noise is not None and noise_level > 0 and rng.random() < noise_level:
        if noise.lowercase:
            text = text.lower()
        if rng.random() < noise.pet_rate and noise.pet_phrases:
            text = f"{rng.choice(noise.pet_phrases)} {text}"
        if rng.random() < noise.drop_apostrophes:
            text = text.replace("'", "")
    return text
