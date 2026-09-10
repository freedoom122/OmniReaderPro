"""Local text intelligence: extractive summarization and keyword extraction.

Pure-algorithm (TextRank-inspired frequency scoring) — no cloud, no fake AI
branding, presented in the UI as a plain document tool.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter

logger = logging.getLogger("omnireader.textstats")

_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F']{2,}")
_SENT_RE = re.compile(r"[^.!?…]+[.!?…]")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "at",
    "for", "with", "as", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "it", "its", "this", "that", "these", "those", "he", "she", "they",
    "them", "his", "her", "their", "we", "our", "you", "your", "i", "me", "my",
    "not", "no", "so", "do", "does", "did", "have", "has", "had", "will",
    "would", "can", "could", "should", "may", "might", "than", "then", "there",
    "here", "when", "where", "which", "who", "what", "how", "all", "each",
    "also", "into", "over", "some", "such", "only", "about", "up", "out",
    "more", "most", "other", "because", "while", "during", "between",
}


def keywords(text: str, count: int = 12) -> list[tuple[str, int]]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    words = [w for w in words if w not in _STOPWORDS and len(w) > 3]
    return Counter(words).most_common(count)


def summarize(text: str, max_sentences: int = 5) -> list[str]:
    """Extractive summary: score sentences by word frequency & position."""
    sentences = [s.strip() for s in _SENT_RE.findall(text) if len(s.strip()) > 25]
    if not sentences:
        return []
    if len(sentences) <= max_sentences:
        return sentences
    freq: dict[str, int] = {}
    for w in _WORD_RE.findall(text.lower()):
        if w not in _STOPWORDS and len(w) > 3:
            freq[w] = freq.get(w, 0) + 1
    if not freq:
        return sentences[:max_sentences]
    max_freq = max(freq.values())
    norm = {w: c / max_freq for w, c in freq.items()}

    scored = []
    for idx, sentence in enumerate(sentences):
        words = [w.lower() for w in _WORD_RE.findall(sentence)]
        if not words:
            continue
        score = sum(norm.get(w, 0) for w in words if w not in _STOPWORDS)
        score /= math.log(len(words) + 5)
        # Mild positional bias: openings and closings often matter.
        if idx == 0:
            score *= 1.15
        elif idx == len(sentences) - 1:
            score *= 1.05
        scored.append((score, idx, sentence))
    scored.sort(reverse=True)
    chosen = sorted(scored[:max_sentences], key=lambda t: t[1])
    return [s for _, _, s in chosen]


def reading_time_minutes(text: str, wpm: int = 220) -> float:
    words = len(_WORD_RE.findall(text))
    return words / max(1, wpm)


def language_guess(text: str) -> str:
    from omnireader_pro.core.translation.translator import detect_language
    return detect_language(text)
