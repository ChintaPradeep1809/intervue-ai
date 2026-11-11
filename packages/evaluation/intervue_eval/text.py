"""Text utilities shared by the deterministic evaluator and evidence verification."""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9+#*.=<>()_\-\s]")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

DONT_KNOW = re.compile(
    r"\b(i\s*(do\s*not|don'?t)\s*know|no idea|not sure|i have no clue|skip( this)?( question)?|pass)\b",
    re.I,
)
REASONING = re.compile(
    r"\b(because|so that|therefore|trade-?offs?|however|instead|for example|e\.g\.|depends|whereas|"
    r"on the other hand|the reason|which means|downside|upside|in contrast|alternatively)\b",
    re.I,
)
TRADEOFF = re.compile(
    r"\b(trade-?offs?|cost|latency|throughput|consistency|simplicity|complexity|downside|pros?|cons?|"
    r"at the expense|balance|versus|vs\.?)\b",
    re.I,
)
FILLER = re.compile(r"\b(um+|uh+|like|you know|basically|kind of|sort of)\b", re.I)
NUMBER = re.compile(r"\b\d+(\.\d+)?\s*(%|ms|s|gb|tb|mb|k|m|x|rows|records|minutes|hours)?\b", re.I)


def normalize(text: str) -> str:
    t = text.lower().replace("’", "'").replace("‘", "'")
    t = _NON_WORD.sub(" ", t)
    return _WS.sub(" ", t).strip()


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]


def word_count(text: str) -> int:
    return len(text.split())


def keyword_in(keyword: str, norm_text: str) -> bool:
    kw = normalize(keyword)
    if not kw:
        return False
    if len(kw) <= 3 and kw.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", norm_text) is not None
    if kw[0].isalnum():  # word-start boundary: "partition" matches "partitioning", "ties" not "properties"
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}", norm_text) is not None
    return kw in norm_text


def find_sentence(text: str, keyword: str, max_len: int = 220) -> str | None:
    """Return the verbatim sentence containing `keyword`, trimmed around the hit if long."""
    for s in sentences(text):
        if keyword_in(keyword, normalize(s)):
            if len(s) <= max_len:
                return s
            idx = s.lower().find(keyword.lower().split()[0])
            start = max(0, idx - max_len // 2)
            snippet = s[start : start + max_len]
            # snap to word boundaries so the quote stays verbatim
            if start > 0 and " " in snippet:
                snippet = snippet[snippet.index(" ") + 1 :]
            if " " in snippet and start + max_len < len(s):
                snippet = snippet[: snippet.rindex(" ")]
            return snippet
    return None


def quote_in_source(quote: str, source: str) -> bool:
    q = normalize(quote)
    return len(q) >= 3 and q in normalize(source)
