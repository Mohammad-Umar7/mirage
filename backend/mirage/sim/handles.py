"""Account handle generator shared by real users and swarm operators alike."""

from __future__ import annotations

import numpy as np

FIRST = ("alex", "sam", "jordan", "maya", "leo", "nina", "omar", "priya", "kai", "zoe", "ivan", "lena",
         "tariq", "yuki", "ben", "ana", "felix", "rosa", "dev", "mira", "noah", "iris", "hugo", "sara",
         "arjun", "chloe", "mateo", "aisha", "finn", "elena", "ravi", "lucy", "theo", "hana", "marco", "ada")
WORDS = ("moon", "pixel", "byte", "fox", "orbit", "cedar", "nova", "echo", "delta", "raven", "ember", "lumen",
         "atlas", "vapor", "quartz", "sol", "drift", "cobalt", "maple", "saffron", "tide", "vector", "glyph",
         "harbor", "zen", "comet", "frost", "onyx", "prism", "sage", "wren", "koi", "flux", "mango", "juniper")
ADJ = ("based", "quiet", "lucky", "cosmic", "sleepy", "brave", "salty", "rapid", "gentle", "wild", "tiny",
       "golden", "silent", "clever", "noisy", "chill", "rusty", "hyper", "lazy", "sunny")


def make_handle(rng: np.random.Generator) -> str:
    style = rng.integers(0, 7)
    if style == 0:
        return f"{rng.choice(FIRST)}{rng.integers(1, 999)}"
    if style == 1:
        return f"{rng.choice(ADJ)}_{rng.choice(WORDS)}"
    if style == 2:
        return f"{rng.choice(FIRST)}.{rng.choice(WORDS)}"
    if style == 3:
        return f"{rng.choice(WORDS)}{rng.choice(WORDS)}{rng.integers(0, 99)}"
    if style == 4:
        return f"{rng.choice(FIRST)}{rng.choice(WORDS)}.eth"
    if style == 5:
        return f"0x{rng.choice(WORDS)}{rng.integers(10, 9999)}"
    return f"{rng.choice(FIRST)}_{rng.choice(ADJ)}{rng.integers(1, 99)}"
