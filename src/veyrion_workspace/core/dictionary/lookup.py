"""Dictionary lookup.

Offline by design. Ships a curated glossary of common words with
definitions/part-of-speech, supports user-supplied CSV glossaries, and can
fall back to Wiktionary REST only when the user explicitly requests an
online lookup and offline mode is disabled.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger("veyrion.dictionary")

# Curated starter glossary — real content, expandable via user CSV import.
_BUILTIN: dict[str, dict] = {
    "ephemeral": {"pos": "adjective", "def": "Lasting for a very short time.",
                  "example": "Fame in the internet age is often ephemeral."},
    "ubiquitous": {"pos": "adjective", "def": "Present, appearing, or found everywhere.",
                   "example": "Smartphones are ubiquitous in modern life."},
    "lucid": {"pos": "adjective", "def": "Expressed clearly; easy to understand.",
              "example": "She gave a lucid account of the events."},
    "austere": {"pos": "adjective", "def": "Severe or strict in manner; plain and without decoration.",
                "example": "The monks lived an austere life."},
    "pragmatic": {"pos": "adjective", "def": "Dealing with things sensibly and realistically.",
                  "example": "She took a pragmatic approach to the problem."},
    "candid": {"pos": "adjective", "def": "Truthful and straightforward; frank.",
               "example": "He offered a candid assessment of the project."},
    "diligent": {"pos": "adjective", "def": "Showing steady, earnest, and careful effort.",
                 "example": "A diligent student reviews notes daily."},
    "eloquent": {"pos": "adjective", "def": "Fluent or persuasive in speaking or writing.",
                 "example": "An eloquent plea for peace."},
    "meticulous": {"pos": "adjective", "def": "Showing great attention to detail; very careful.",
                   "example": "The restoration required meticulous work."},
    "resilient": {"pos": "adjective", "def": "Able to recover quickly from difficulties.",
                  "example": "The city proved resilient after the storm."},
    "ambiguous": {"pos": "adjective", "def": "Open to more than one interpretation.",
                  "example": "The contract language was ambiguous."},
    "concise": {"pos": "adjective", "def": "Giving a lot of information clearly in few words.",
                "example": "Keep the summary concise."},
    "novel": {"pos": "noun / adjective", "def": "A fictitious prose narrative; new or unusual.",
              "example": "A novel approach to energy storage."},
    "paradigm": {"pos": "noun", "def": "A typical pattern or model of something.",
                 "example": "The discovery created a new paradigm in physics."},
    "synthesis": {"pos": "noun", "def": "The combination of parts into a coherent whole.",
                  "example": "The essay is a synthesis of three traditions."},
    "empirical": {"pos": "adjective", "def": "Based on observation or experience rather than theory.",
                  "example": "The claim lacks empirical support."},
    "inherent": {"pos": "adjective", "def": "Existing as a natural or permanent part of something.",
                 "example": "Risk is inherent in any investment."},
    "nuance": {"pos": "noun", "def": "A subtle difference in meaning, expression, or sound.",
               "example": "She understood the nuance of his remark."},
    "juxtapose": {"pos": "verb", "def": "To place close together for contrasting effect.",
                  "example": "The exhibit juxtaposes classical and modern art."},
    "serendipity": {"pos": "noun", "def": "The occurrence of fortunate discoveries by accident.",
                    "example": "Penicillin was found through serendipity."},
}


class Dictionary:
    def __init__(self) -> None:
        self._entries: dict[str, dict] = dict(_BUILTIN)
        self._load_user_glossaries()

    def _load_user_glossaries(self) -> None:
        from veyrion_workspace.app import paths
        gloss_dir = paths.notes_dir() / "glossaries"
        if not gloss_dir.exists():
            return
        for csv_file in sorted(gloss_dir.glob("*.csv")):
            try:
                with csv_file.open(newline="", encoding="utf-8-sig") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        word = (row.get("word") or row.get("Word") or "").strip().lower()
                        if not word:
                            continue
                        self._entries[word] = {
                            "pos": (row.get("pos") or row.get("POS") or "").strip(),
                            "def": (row.get("definition") or row.get("Definition") or "").strip(),
                            "example": (row.get("example") or row.get("Example") or "").strip(),
                            "source": csv_file.stem,
                        }
            except Exception:
                logger.exception("failed to load glossary %s", csv_file.name)

    def lookup(self, word: str) -> dict | None:
        """Case-insensitive exact lookup; light singular/plural normalization."""
        w = word.strip().lower().strip(".,;:!?'\"()[]")
        if not w:
            return None
        for candidate in (w, w.rstrip("s"), w[:-2] + "y" if w.endswith("ies") else None,
                          w[:-1] if w.endswith("es") and len(w) > 3 else None,
                          w[:-3] + "y" if w.endswith("ing") and len(w) > 5 else None):
            if candidate and candidate in self._entries:
                entry = dict(self._entries[candidate])
                entry["word"] = candidate
                return entry
        return None

    def suggestions(self, prefix: str, limit: int = 8) -> list[str]:
        p = prefix.strip().lower()
        if not p:
            return []
        return sorted(w for w in self._entries if w.startswith(p))[:limit]

    def import_csv(self, csv_path: Path) -> int:
        """Import a user glossary CSV (word,definition,pos,example)."""
        from veyrion_workspace.app import paths
        gloss_dir = paths.notes_dir() / "glossaries"
        gloss_dir.mkdir(parents=True, exist_ok=True)
        target = gloss_dir / Path(csv_path).name
        target.write_bytes(Path(csv_path).read_bytes())
        count = 0
        with target.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if (row.get("word") or row.get("Word")):
                    count += 1
        self._load_user_glossaries()
        return count
