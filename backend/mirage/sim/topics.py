"""Topic vocabularies for the offline text generator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    nouns: tuple[str, ...]
    entities: tuple[str, ...]
    verbs: tuple[str, ...]
    adjs: tuple[str, ...]
    hashtags: tuple[str, ...]
    emojis: tuple[str, ...]
    lines: tuple[str, ...]  # topic-specific full sentences with {E}/{N} slots


TOPICS: dict[str, Topic] = {
    "defi": Topic(
        "defi",
        ("liquidity", "yield", "stablecoin peg", "lending market", "LP position", "vault strategy",
         "swap fees", "collateral ratio", "funding rate", "bridge volume", "restaking", "points program"),
        ("Aavex", "Uniflow", "Curvature", "Lidora", "Makerly", "Pendulum", "Morphic", "Ethera", "Compoundly"),
        ("just shipped", "is bleeding", "quietly launched", "cut fees on", "doubled down on", "paused",
         "is migrating", "is subsidising", "rugged"),
        ("insane", "sketchy", "underrated", "overleveraged", "sustainable", "degen", "solid", "fragile"),
        ("#DeFi", "#yield", "#stablecoins", "#onchain"),
        ("📈", "💸", "🏦", "🧮", "🌾"),
        ("{E} yields look way too good to be sustainable",
         "moved my {N} to {E}, fees are finally reasonable",
         "the {N} on {E} is getting weird again",
         "if {E} depegs again I'm done with {N}",
         "reading the {E} audit before touching any {N}"),
    ),
    "nft": Topic(
        "nft",
        ("generative art", "mint", "floor price", "collection", "royalties", "1/1 piece", "gallery drop",
         "pfp project", "on-chain art", "curation"),
        ("Glyphworks", "Pixel Harbor", "Nocturne", "Artblocks Lite", "Chromaform", "Ordinal Garden"),
        ("dropped", "sold out", "is curating", "burned", "revealed", "airdropped"),
        ("gorgeous", "overpriced", "haunting", "clean", "wild", "timeless", "derivative"),
        ("#NFT", "#generativeart", "#cryptoart", "#onchainart"),
        ("🎨", "🖼️", "✨", "🌀"),
        ("the {E} {N} is genuinely gorgeous",
         "missed the {E} mint again, story of my life",
         "{N} is back and I'm here for it",
         "hot take: most {N} is just noise right now",
         "spent the evening browsing {E}, the palette work is unreal"),
    ),
    "gaming": Topic(
        "gaming",
        ("season pass", "ranked queue", "patch notes", "loot drop", "speedrun", "guild raid", "open beta",
         "tournament", "server lag", "skill tree"),
        ("Voidrunner", "Hexfall", "Shardlands", "Neon Drift", "Crowncraft", "Duskmoor"),
        ("nerfed", "buffed", "delayed", "shadow-dropped", "reworked", "leaked"),
        ("broken", "cozy", "sweaty", "unplayable", "addictive", "grindy", "polished"),
        ("#gaming", "#esports", "#web3gaming", "#gamedev"),
        ("🎮", "🕹️", "⚔️", "🔥"),
        ("{E} {N} is completely broken lol",
         "one more {N} then bed. (it was not one more)",
         "the new {E} {N} is so good",
         "who's queuing {E} tonight",
         "{E} patch notes just dropped and my main got nerfed"),
    ),
    "ai": Topic(
        "ai",
        ("fine-tune", "benchmark", "inference cost", "context window", "agent framework", "eval suite",
         "open weights", "GPU cluster", "prompt injection", "RAG pipeline"),
        ("Orca-7", "Lumen AI", "Tensorly", "OpenForge", "Quill", "Nimbus Labs"),
        ("open sourced", "benchmarked", "fine-tuned", "shipped", "quantized", "deprecated"),
        ("impressive", "overfit", "cheap", "scary good", "hallucinated", "efficient", "brittle"),
        ("#AI", "#LLM", "#MachineLearning", "#agents"),
        ("🤖", "🧠", "⚡", "🔬"),
        ("tried the new {E} model and the {N} is wild",
         "{N} is the real bottleneck, not model size",
         "everyone is building agents but nobody has a real {N}",
         "{E} just {V} and my weekend is gone",
         "ran our {N} again, numbers moved in the right direction"),
    ),
    "climate": Topic(
        "climate",
        ("carbon credits", "solar install", "heat pump", "grid storage", "reforestation project",
         "emissions data", "e-bike commute", "community garden"),
        ("GreenLedger", "Solaris Coop", "Treeline DAO", "Kiln Energy", "Tidewater"),
        ("verified", "funded", "expanded", "installed", "launched"),
        ("hopeful", "overdue", "promising", "sobering", "practical"),
        ("#climate", "#ReFi", "#solar", "#sustainability"),
        ("🌱", "🌍", "☀️", "🌊"),
        ("our {N} finally went live this week",
         "{E} publishing real {N} is a big deal",
         "honestly {N} makes me more hopeful than anything else",
         "biked to work again, legs hate me, planet likes me"),
    ),
    "music": Topic(
        "music",
        ("new EP", "live set", "vinyl pressing", "synth patch", "listening party", "remix", "tour dates",
         "b-side", "setlist"),
        ("Velvet Static", "Mira Nova", "The Low Tides", "Kairo", "Glass Animals Club", "Sunday Arcade"),
        ("dropped", "announced", "remixed", "headlined", "teased"),
        ("dreamy", "hypnotic", "loud", "underrated", "perfect", "nostalgic"),
        ("#music", "#newmusic", "#synthwave", "#vinyl"),
        ("🎧", "🎶", "🎹", "📀"),
        ("{E} {V} a {N} and I've had it on repeat",
         "the {N} last night was unreal",
         "need more {N} like this in my life",
         "{E} live is a completely different experience"),
    ),
    "sports": Topic(
        "sports",
        ("derby", "transfer window", "playoff run", "injury report", "final whistle", "penalty call",
         "fantasy lineup", "comeback"),
        ("Rovers FC", "the Comets", "Harbor City", "Northside United", "the Falcons"),
        ("won", "lost", "signed", "benched", "traded"),
        ("robbed", "clutch", "brutal", "historic", "sloppy"),
        ("#matchday", "#football", "#NBA", "#fantasy"),
        ("⚽", "🏀", "🏆", "😤"),
        ("{E} got absolutely robbed in that {N}",
         "that {N} was the best game all season",
         "my {N} is in shambles after tonight",
         "{E} {V} again, what a {N}"),
    ),
    "governance": Topic(
        "governance",
        ("proposal", "quorum", "delegate vote", "treasury report", "forum thread", "voting period",
         "multisig", "grants committee", "temperature check"),
        ("the council", "the grants committee", "the treasury multisig", "the delegates"),
        ("passed", "rejected", "extended", "amended", "tabled"),
        ("reasonable", "rushed", "transparent", "contentious", "overdue", "sensible"),
        ("#DAO", "#governance", "#onchain"),
        ("🗳️", "📜", "🏛️"),
        ("read the full {N} before voting, it's worth it",
         "{E} should publish the {N} earlier",
         "the {N} discussion on the forum is actually productive",
         "quorum on this {N} is going to be close"),
    ),
    "dev": Topic(
        "dev",
        ("smart contract audit", "gas optimisation", "rust rewrite", "CI pipeline", "type system",
         "indexer", "SDK", "testnet deploy", "fuzzing campaign", "refactor"),
        ("Foundryx", "Hardcat", "Vyperlight", "Anchorwork", "Rethink", "Typegate"),
        ("shipped", "broke", "refactored", "deprecated", "merged", "benchmarked"),
        ("clean", "cursed", "elegant", "flaky", "blazing fast", "painful"),
        ("#buildinpublic", "#solidity", "#rustlang", "#devtools"),
        ("🛠️", "💻", "🐛", "🧪"),
        ("spent all day on a {N} and it was worth it",
         "{E} {V} a new release and my build is {A} now",
         "friendly reminder to write tests before the {N}",
         "our {N} caught a real bug today, fuzzing works"),
    ),
    "memes": Topic(
        "memes",
        ("meme", "shitpost", "copium", "ratio", "main character energy", "the timeline", "vibe check"),
        ("the timeline", "group chat", "crypto twitter", "the discord"),
        ("posted", "cooked", "ratioed", "fumbled"),
        ("unhinged", "legendary", "cursed", "iconic", "peak"),
        ("#memes", "#gm", "#wagmi"),
        ("😂", "💀", "🫠", "🐸"),
        ("the {N} today is absolutely unhinged",
         "not me checking {E} at 3am again",
         "whoever made this {N} deserves a raise",
         "{E} is in shambles and I'm eating popcorn"),
    ),
    "privacy": Topic(
        "privacy",
        ("zero-knowledge proof", "privacy pool", "encrypted messaging", "self-custody", "metadata leak",
         "stealth address", "hardware wallet"),
        ("ZKSafe", "Enigma Mail", "Shieldr", "Veil Protocol", "Nullset"),
        ("launched", "audited", "open sourced", "deanonymised", "patched"),
        ("essential", "underrated", "clunky", "elegant", "necessary"),
        ("#privacy", "#zk", "#selfcustody"),
        ("🔒", "🕶️", "🛡️"),
        ("{N} is a feature, not a crime",
         "moved everything to a {N}, feels good",
         "{E} doing real {N} research is refreshing",
         "every app leaks metadata, {N} matters"),
    ),
    "markets": Topic(
        "markets",
        ("BTC dominance", "ETH/BTC", "liquidation cascade", "funding rates", "rate cut", "ETF flows",
         "range breakout", "altseason"),
        ("BTC", "ETH", "SOL", "the Fed", "the ETFs"),
        ("broke out", "dumped", "ripped", "consolidated", "wicked down"),
        ("bullish", "bearish", "choppy", "overheated", "boring", "healthy"),
        ("#Bitcoin", "#crypto", "#trading"),
        ("📊", "🚀", "📉", "🐂"),
        ("{E} {V} and everyone suddenly has an opinion",
         "watching {N} closely this week",
         "zoom out. {N} is still {A}",
         "{N} tells you everything if you look"),
    ),
    "campus": Topic(
        "campus",
        ("hackathon", "club meetup", "workshop", "demo day", "pizza budget", "team formation",
         "judging round", "study group"),
        ("Blockchain@Uni", "the uni hackathon", "the club", "demo day"),
        ("kicked off", "announced", "wrapped up", "rescheduled"),
        ("chaotic", "amazing", "exhausting", "wholesome", "packed"),
        ("#hackathon", "#BlockchainAtUni", "#studentdevs"),
        ("🎓", "🍕", "🧑‍💻", "🏁"),
        ("{E} {N} tonight, who's coming",
         "our team for the {N} is stacked",
         "{N} was {A} but so worth it",
         "no sleep, just {N} energy"),
    ),
}

TOPIC_KEYS: tuple[str, ...] = tuple(k for k in TOPICS if k != "campus")
ALL_TOPIC_KEYS: tuple[str, ...] = tuple(TOPICS)

# Generic social-media glue shared by every writer.
OPENERS = ("", "", "", "ok so", "honestly", "not gonna lie", "hot take:", "PSA:", "reminder:",
           "just noticed", "anyone else think", "so apparently", "update:", "quick one:",
           "unpopular opinion:", "real question:", "calling it now:", "fun fact:")
OPINIONS = ("it's {A}", "worth a look", "not convinced", "honestly impressive", "overhyped",
            "underrated", "we'll see", "love it", "hard pass", "kinda fire", "mid", "bullish on it",
            "cautiously optimistic", "big if true", "this aged well", "no notes")
CLOSERS = ("", "", "", "thoughts?", "lmk", "anyway", "just saying", "back to work", "rant over",
           "cheers", "stay safe out there", "gm", "gn", "wen?", "who's with me")
TIMEFRAMES = ("morning", "weekend", "week", "night", "afternoon")
PET_PHRASES = ("fr", "lowkey", "highkey", "ngl", "tbh", "imo", "no cap", "big if true", "respectfully",
               "let him cook", "it is what it is", "vibes", "mark my words", "nfa", "dyor", "iykyk",
               "wagmi", "ser", "anon", "frens", "the way I see it", "for real though", "to be fair",
               "hear me out", "plot twist", "say less", "zero chance", "not financial advice", "welp",
               "yikes", "bless", "love that for us", "ok but", "lmao", "no thoughts just vibes",
               "the math is mathing", "touch grass", "absolute cinema", "we are so back", "it's over")
SLANG = {"to be honest": "tbh", "in my opinion": "imo", "not gonna lie": "ngl", "you": "u",
         "because": "bc", "people": "ppl", "really": "rly", "though": "tho", "with": "w/"}
