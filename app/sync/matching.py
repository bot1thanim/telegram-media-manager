"""Deterministic, explainable topic-name normalization and matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

_FINAL_LETTERS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_MULTI_SPACE = re.compile(r"\s+")
_HEBREW_WORD = re.compile(r"^[\u0590-\u05ff]+$")
_ASCII_WORD = re.compile(r"^[a-z0-9]+$")


@dataclass(frozen=True, slots=True)
class TopicNameMatch:
    """A safe candidate selection between a category and a target topic."""

    topic_id: int | None
    topic_name: str | None
    confidence: float
    method: str
    ambiguous: bool = False

    @property
    def is_match(self) -> bool:
        return self.topic_id is not None and not self.ambiguous


def _strip_marks(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if unicodedata.category(character) != "Mn"
    )


def normalize_topic_name(name: str) -> str:
    """Return a stable display-independent name for topic comparison.

    The function preserves word boundaries while removing Hebrew diacritics,
    punctuation, presentation variants, final-letter variants, and redundant
    whitespace. It intentionally does not translate names or guess meaning.
    """
    normalized = _strip_marks(name).casefold().translate(_FINAL_LETTERS)
    normalized = _NON_WORD.sub(" ", normalized)
    return _MULTI_SPACE.sub(" ", normalized).strip()


def _canonical_hebrew_word(word: str) -> str:
    """Reduce common Hebrew definite/plural/adjectival variants conservatively."""
    canonical = word
    if len(canonical) >= 4 and canonical.startswith("ה"):
        canonical = canonical[1:]

    # Both "ישראלי" and "ישראליות" reduce to "ישראל"; both "סדרה" and
    # "סדרות" reduce to "סדר". The minimum length protects short words.
    if len(canonical) >= 5 and canonical.endswith("יות"):
        canonical = canonical[:-3]
    elif len(canonical) >= 4 and canonical.endswith("ים"):
        canonical = canonical[:-2]
    elif len(canonical) >= 4 and canonical.endswith("ות"):
        canonical = canonical[:-2]
    elif len(canonical) >= 4 and canonical.endswith("ית"):
        canonical = canonical[:-2]
    elif len(canonical) >= 4 and canonical.endswith(("ה", "י")):
        canonical = canonical[:-1]
    return canonical


def _canonical_english_word(word: str) -> str:
    """Reduce only unambiguous English plural suffixes."""
    # Preserve the terminal "e" in words such as movie → movies. This is the
    # safer default for topic labels; irregular forms intentionally fall back to
    # the conservative fuzzy matcher rather than being over-normalized.
    if len(word) > 4 and word.endswith("ies"):
        return word[:-1]
    if len(word) > 3 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def canonical_topic_name(name: str) -> str:
    """Return the plural-tolerant canonical key used for exact topic matching."""
    normalized = normalize_topic_name(name)
    words: list[str] = []
    for word in normalized.split():
        if _HEBREW_WORD.fullmatch(word):
            words.append(_canonical_hebrew_word(word))
        elif _ASCII_WORD.fullmatch(word):
            words.append(_canonical_english_word(word))
        else:
            words.append(word)
    return " ".join(words)


def _similarity(left: str, right: str) -> float:
    """Score only normalized names; callers retain a conservative acceptance bar."""
    return SequenceMatcher(a=left, b=right, autojunk=False).ratio()


def choose_best_topic_match(
    category_name: str,
    topics: Iterable[object],
    *,
    minimum_fuzzy_confidence: float = 0.92,
    ambiguity_margin: float = 0.08,
) -> TopicNameMatch:
    """Choose one safe topic candidate from objects exposing ``id`` and ``name``.

    Exact normalized matches and exact canonical matches are deterministic. A
    fuzzy candidate is accepted only when it clears a high threshold and is
    clearly better than its closest competitor. Ambiguous input deliberately
    produces no automatic match so media cannot be sent to the wrong topic.
    """
    normalized_category = normalize_topic_name(category_name)
    canonical_category = canonical_topic_name(category_name)
    if not normalized_category:
        return TopicNameMatch(None, None, 0.0, "empty")

    scored: list[tuple[float, object, str]] = []
    for topic in topics:
        topic_name = getattr(topic, "name", "")
        normalized_topic = normalize_topic_name(topic_name)
        if not normalized_topic:
            continue
        if normalized_topic == normalized_category:
            return TopicNameMatch(topic.id, topic_name, 1.0, "normalized_exact")
        if canonical_topic_name(topic_name) == canonical_category:
            scored.append((0.98, topic, "canonical_exact"))
            continue
        scored.append((_similarity(normalized_category, normalized_topic), topic, "fuzzy"))

    if not scored:
        return TopicNameMatch(None, None, 0.0, "none")

    scored.sort(key=lambda candidate: candidate[0], reverse=True)
    best_score, best_topic, method = scored[0]
    runner_up_score = scored[1][0] if len(scored) > 1 else 0.0
    if method == "canonical_exact":
        if runner_up_score >= best_score - ambiguity_margin:
            return TopicNameMatch(None, None, best_score, method, ambiguous=True)
        return TopicNameMatch(best_topic.id, best_topic.name, best_score, method)

    if best_score < minimum_fuzzy_confidence:
        return TopicNameMatch(None, None, best_score, method)
    if runner_up_score >= best_score - ambiguity_margin:
        return TopicNameMatch(None, None, best_score, method, ambiguous=True)
    return TopicNameMatch(best_topic.id, best_topic.name, best_score, method)
