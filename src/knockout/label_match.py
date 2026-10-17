"""Find a reaction term in a label, as a whole phrase (protocol step 6). No model takes part."""

import re
from dataclasses import dataclass

from knockout.openfda import Label

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


@dataclass(frozen=True)
class LabelMatch:
    section: str
    term: str
    sentence: str


def term_pattern(term: str) -> re.Pattern[str]:
    """Whole words, any spacing, the last word optionally ending in "s" or "es"."""
    words = [re.escape(word) for word in term.lower().split()]
    words[-1] += r"(?:e?s)?"
    return re.compile(r"\b" + r"\s+".join(words) + r"\b", re.IGNORECASE)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_END.split(text) if part.strip()]


def find(label: Label, terms: list[str]) -> LabelMatch | None:
    """The first matching sentence, sections in the protocol's order, terms in the mapping's order."""
    patterns = [(term, term_pattern(term)) for term in terms]
    for section, text in label.sections.items():
        for sentence in sentences(text):
            for term, pattern in patterns:
                if pattern.search(sentence):
                    return LabelMatch(section=section, term=term, sentence=sentence)
    return None
