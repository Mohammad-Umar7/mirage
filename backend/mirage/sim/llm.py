"""Optional LLM-generated post cache (Groq or Gemini).

If ``GROQ_API_KEY`` or ``GEMINI_API_KEY`` is set, ``python -m mirage.cli
llm-cache`` asks the provider for a sample of persona posts and stores
them in ``backend/.cache/llm/posts.jsonl``. The simulator mixes cached
posts into its offline generator. Nothing requires the network at run
time: without a cache the offline generator is used exclusively.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..config import CACHE_DIR, load_dotenv
from .textgen import PERSONAS
from .topics import TOPIC_KEYS

CACHE_FILE = CACHE_DIR / "llm" / "posts.jsonl"

REAL_PROMPT = (
    "Write {n} different short social media posts (each under 200 characters) that real, different "
    "people might write about {topic} in a crypto/web3 community. Vary tone, length, slang, casing and "
    "opinions a lot; some casual, some thoughtful, some jokey. No hashtags, no numbering. "
    "Return one post per line."
)
SWARM_PROMPT = (
    "Write {n} different short, polished social media posts (each under 220 characters) about {topic}, "
    "written in the voice of {persona}. Keep them upbeat and articulate. No hashtags, no numbering. "
    "Return one post per line."
)


def load_cache(path: Path = CACHE_FILE) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    out: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.setdefault(row["key"], []).append(row["text"])
    return out


class LLMClient:
    def __init__(self, provider: str, key: str, model: str) -> None:
        self.provider, self.key, self.model = provider, key, model

    @classmethod
    def from_env(cls) -> "LLMClient | None":
        load_dotenv()
        if os.environ.get("GROQ_API_KEY"):
            return cls("groq", os.environ["GROQ_API_KEY"], os.environ.get("MIRAGE_GROQ_MODEL", "llama-3.1-8b-instant"))
        if os.environ.get("GEMINI_API_KEY"):
            return cls("gemini", os.environ["GEMINI_API_KEY"], os.environ.get("MIRAGE_GEMINI_MODEL", "gemini-2.5-flash"))
        return None

    def complete(self, prompt: str) -> str:
        import httpx

        if self.provider == "groq":
            r = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json={"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 1.0},
                timeout=60,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.key},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 1.0}},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _lines(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("-*0123456789.) ").strip().strip('"')
        if 12 <= len(line) <= 260:
            out.append(line)
    return out


def build_cache(per_prompt: int = 20, path: Path = CACHE_FILE, log=print) -> int:
    """Populate the cache. Returns number of posts written (0 without a key)."""
    client = LLMClient.from_env()
    if client is None:
        log("No GROQ_API_KEY / GEMINI_API_KEY set; offline generator only.")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for topic in TOPIC_KEYS:
            try:
                for text in _lines(client.complete(REAL_PROMPT.format(n=per_prompt, topic=topic))):
                    fh.write(json.dumps({"key": f"real:{topic}", "text": text}) + "\n")
                    written += 1
            except Exception as exc:  # network / quota problems are non-fatal
                log(f"[llm] real:{topic} failed: {exc}")
        for persona, (intro, topic) in PERSONAS.items():
            try:
                prompt = SWARM_PROMPT.format(n=per_prompt, topic=topic, persona=intro.lower())
                for text in _lines(client.complete(prompt)):
                    fh.write(json.dumps({"key": f"swarm:{topic}", "text": text}) + "\n")
                    written += 1
            except Exception as exc:
                log(f"[llm] swarm:{persona} failed: {exc}")
    log(f"[llm] cached {written} posts via {client.provider} ({client.model}) -> {path}")
    return written
