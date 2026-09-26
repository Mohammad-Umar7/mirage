"""Generic stylometric features of a short post.

Nothing here knows about the simulator's generators: these are classic
authorship-attribution features (length, punctuation habits, casing,
function-word profile, informality markers).
"""

from __future__ import annotations

import math
import re

import numpy as np

FUNCTION_WORDS = ("the", "a", "and", "of", "to", "is", "it", "that", "in", "for", "this", "i", "you", "we", "be",
                  "on", "not", "just", "so", "but", "with", "are", "my", "all", "at", "what", "will", "can",
                  "about", "if", "our", "its", "they", "me", "or")
INFORMAL = frozenset(("lol", "lmao", "tbh", "imo", "ngl", "fr", "rly", "tho", "bc", "u", "ppl", "gm", "gn", "ser",
                      "anon", "wagmi", "nfa", "dyor", "iykyk", "lowkey", "highkey", "idk", "omg", "smh", "yall"))
BARE_CONTRACTIONS = frozenset(("dont", "cant", "im", "thats", "youre", "wont", "isnt", "didnt", "ive", "its"))

_TOKEN = re.compile(r"[A-Za-z']+")
_SENT = re.compile(r"[.!?]+")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆↔-↪]")
_FW_INDEX = {w: i for i, w in enumerate(FUNCTION_WORDS)}

N_BASE = 25
N_FEATURES = N_BASE + len(FUNCTION_WORDS)


def style_vector(text: str) -> np.ndarray:
    v = np.zeros(N_FEATURES, dtype=np.float32)
    words = _TOKEN.findall(text)
    n_words = max(1, len(words))
    letters = [c for c in text if c.isalpha()]
    n_letters = max(1, len(letters))
    sentences = [s for s in _SENT.split(text) if s.strip()]
    n_sent = max(1, len(sentences))
    lower_words = [w.lower() for w in words]
    stripped = text.rstrip()

    v[0] = math.log1p(len(words))
    v[1] = sum(len(w) for w in words) / n_words
    v[2] = math.log1p(n_sent)
    v[3] = len(words) / n_sent
    v[4] = sum(1 for c in letters if c.isupper()) / n_letters
    v[5] = 1.0 if text[:1].islower() else 0.0
    v[6] = 1.0 if text == text.lower() else 0.0
    v[7] = text.count("!") / n_words
    v[8] = text.count("?") / n_words
    v[9] = (text.count("...") + text.count("…")) / n_words
    v[10] = text.count(",") / n_words
    v[11] = 1.0 if stripped.endswith(".") and not stripped.endswith("...") else 0.0
    v[12] = math.log1p(len(_EMOJI.findall(text)))
    v[13] = text.count("#")
    v[14] = text.count("@")
    v[15] = sum(1 for c in text if c.isdigit()) / max(1, len(text))
    v[16] = (text.count("—") + text.count(" - ")) / n_words
    v[17] = (text.count(":") + text.count(";")) / n_words
    v[18] = len(set(lower_words)) / n_words
    v[19] = sum(1 for w in lower_words if "'" in w) / n_words
    v[20] = sum(1 for w in lower_words if w in BARE_CONTRACTIONS) / n_words
    v[21] = sum(1 for w in lower_words if w in INFORMAL) / n_words
    v[22] = sum(1 for w in lower_words if w in _FW_INDEX) / n_words
    v[23] = sum(1 for w in words if w[:1].isupper() and w[1:].islower()) / n_words
    v[24] = sum(1 for w in words if len(w) > 1 and w.isupper()) / n_words
    for w in lower_words:
        j = _FW_INDEX.get(w)
        if j is not None:
            v[N_BASE + j] += 1.0
    v[N_BASE:] /= n_words
    return v
