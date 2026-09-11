"""Translation subsystem.

Strategy (all offline unless the user explicitly opts in):
1. Argos Translate when the package and language models are installed —
   full offline neural translation.
2. Built-in phrasebook for common UI-level phrases (fallback utility).
3. Online translation only via explicit user action with offline mode off.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("veyrion.translate")

try:
    from argostranslate import translate as argos_translate
    HAS_ARGOS = True
except ImportError:  # pragma: no cover
    HAS_ARGOS = False

# Simple language detection via stopword profiles and script ranges.
_STOPWORDS = {
    "en": {"the", "and", "is", "of", "to", "in", "that", "it", "with", "for", "as", "on", "was", "are", "this", "be", "have", "has"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "mit", "von", "zu", "den", "dem", "sich", "auf", "für"},
    "fr": {"le", "la", "les", "et", "est", "un", "une", "des", "que", "qui", "dans", "pour", "pas", "avec", "sur", "au"},
    "es": {"el", "la", "los", "las", "y", "es", "un", "una", "que", "de", "en", "por", "con", "para", "del", "se"},
    "it": {"il", "la", "lo", "gli", "le", "e", "è", "un", "una", "che", "di", "in", "per", "con", "del", "sono"},
    "pt": {"o", "a", "os", "as", "e", "é", "um", "uma", "que", "de", "em", "por", "com", "para", "do", "não"},
    "nl": {"de", "het", "een", "en", "is", "van", "niet", "dat", "op", "met", "voor", "zijn", "aan", "ook"},
}


@dataclass
class TranslationResult:
    text: str
    source_lang: str
    target_lang: str
    engine: str
    detected: bool = False


def detect_language(text: str) -> str:
    """Best-effort language detection via script + stopword profiles."""
    sample = text[:4000].lower()
    if any("\u0600" <= ch <= "\u06ff" for ch in sample):
        return "ar"
    if any("\u0400" <= ch <= "\u04ff" for ch in sample):
        return "ru"
    if any("\u4e00" <= ch <= "\u9fff" for ch in sample):
        return "zh"
    if any("\u3040" <= ch <= "\u30ff" for ch in sample):
        return "ja"
    if any("\uac00" <= ch <= "\ud7af" for ch in sample):
        return "ko"
    if any("\u0590" <= ch <= "\u05ff" for ch in sample):
        return "he"
    words = set("".join(c if c.isalnum() or c.isspace() else " " for c in sample).split())
    best, best_score = "en", 0
    for lang, stops in _STOPWORDS.items():
        score = len(words & stops)
        if score > best_score:
            best, best_score = lang, score
    return best


def installed_pairs() -> list[tuple[str, str]]:
    """Language pairs available for offline Argos translation."""
    if not HAS_ARGOS:
        return []
    try:
        return [(t.from_code, t.to_code) for t in argos_translate.get_installed_languages()]
    except Exception:
        return []


def argos_available() -> bool:
    return HAS_ARGOS


def translate_offline(text: str, target_lang: str,
                      source_lang: str | None = None) -> TranslationResult:
    """Translate with Argos models; raises when unavailable."""
    if not HAS_ARGOS:
        raise RuntimeError(
            "Offline translation requires Argos Translate models. "
            "Install with: pip install argostranslate, then download a "
            "language package from argos-translate (Tools > Translation).")
    detected = source_lang is None
    if source_lang is None:
        source_lang = detect_language(text)
    langs = argos_translate.get_installed_languages()
    src = next((l for l in langs if l.code == source_lang), None)
    dst = next((l for l in langs if l.code == target_lang), None)
    if src is None or dst is None:
        raise RuntimeError(
            f"No offline model installed for {source_lang} -> {target_lang}. "
            "Download the language package first (Tools > Translation).")
    translation = src.get_translation(dst)
    return TranslationResult(text=translation.translate(text),
                             source_lang=source_lang, target_lang=target_lang,
                             engine="argos", detected=detected)


def translate_online(text: str, target_lang: str,
                     source_lang: str | None = None) -> TranslationResult:
    """Explicit user-initiated web translation fallback.

    Only called after the user confirms network use (offline mode off).
    Uses LibreTranslate-compatible public endpoint behavior via requests
    to MyMemory API (free, keyless, no account).
    """
    import json
    import urllib.parse
    import urllib.request
    detected = False
    if source_lang is None:
        source_lang = detect_language(text)
        detected = True
    src = source_lang if source_lang != "auto" else "en"
    url = ("https://api.mymemory.translated.net/get?q="
           + urllib.parse.quote(text[:500])
           + f"&langpair={src}|{target_lang}")
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        translated = data.get("responseData", {}).get("translatedText", "")
        if not translated:
            raise RuntimeError("Translation service returned no content")
        return TranslationResult(text=translated, source_lang=source_lang,
                                 target_lang=target_lang, engine="mymemory",
                                 detected=detected)
    except Exception as e:
        raise RuntimeError(f"Online translation failed: {e}") from e
