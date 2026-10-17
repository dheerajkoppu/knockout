"""Reads what the person asked: which drug or protein, an effect they care about, or a card button they pressed."""

import json
import re
from dataclasses import dataclass, field

ANALYZE = "analyze"
FULL_REPORT = "full_report"
HELP = "help"
LIST_DRUGS = "list_drugs"

STOPWORDS = {
    "about", "adverse", "after", "against", "agent", "also", "analyse", "analyze", "and", "any", "anything", "are",
    "based", "being", "block", "blocker", "blockers", "blocking", "blocks", "can", "cause", "caused", "causes",
    "causing", "check", "could", "does", "drug", "drugs", "effect", "effects", "expect", "expected", "explain",
    "for", "from", "full", "genetic", "genetics", "give", "have", "hello", "how", "increase", "increases",
    "inhibitor", "inhibitors", "inhibits", "into", "is", "knockout", "lead", "like", "likely", "lower", "lowers",
    "me", "medicine", "might", "more", "patients", "please", "predict", "predicted", "prediction", "predictions",
    "protein", "raise", "raises", "reactions", "reduce", "reduces", "report", "risk", "risks", "safety", "should",
    "show", "side", "tell", "than", "that", "the", "their", "them", "there", "these", "this", "those", "what",
    "when", "which", "who", "why", "will", "with", "would", "you", "your", "people", "take", "takes", "taking",
    "taken", "used", "uses", "using", "treat", "treats", "treating", "given", "pill", "pills", "they", "user",
    "users", "selected", "selects", "picked", "clicked", "chose", "chosen", "button", "wants", "want", "asked",
}
DRUG_SUFFIXES = (
    "mab", "nib", "cept", "parin", "prazole", "statin", "olol", "pril", "sartan", "vir", "mycin", "cillin",
    "azole", "tide", "platin", "taxel", "rubicin", "lukast", "gliptin", "gliflozin", "dronate", "oxetine",
)
TARGET_PATTERN = re.compile(
    r"\b(?:an?\s+|the\s+)?([a-z0-9][a-z0-9-]*(?:\s+[a-z0-9][a-z0-9-]*)?)\s+"
    r"(?:blockers?|inhibitors?|antagonists?|blocking\s+(?:drugs?|antibod(?:y|ies)))\b"
)
BLOCKS_PATTERN = re.compile(r"\b(?:block|blocks|blocking|inhibit|inhibits|inhibiting|target|targets|targeting)\s+"
                            r"(?:the\s+)?(?:protein\s+)?([a-z0-9][a-z0-9-]*)")
FOCUS_PATTERN = re.compile(
    r"\b(?:cause|causes|lead\s+to|leads\s+to|risk\s+of|give\s+(?:me|you|people|them|us|patients)?\s*)\s*(?:an?\s+|more\s+)?"
    r"([a-z][a-z\s-]{2,40}?)\s*(?:[?.!]|$|\bin\b|\bfor\b|\bin\s+patients\b)"
)
LIST_PATTERN = re.compile(r"\b(?:which|what|list|name)\s+(?:the\s+)?(?:approved\s+)?(?:drugs|medicines|medications)\b")
FULL_REPORT_PATTERN = re.compile(r"\b(full|complete|paid|whole|detailed)[\s_]+report\b|\bbuy\b|\bunlock\b")
GENERIC_FOCUS = {"side effects", "side effect", "effects", "adverse effects", "problems", "harm", "any side effects"}


@dataclass
class Intent:
    action: str
    drug_words: list[str] = field(default_factory=list)
    drug: str | None = None
    target_words: str | None = None
    # "lowers" when the person asked about a blocker or an inhibitor, so only lowering drugs are offered.
    target_effect: str | None = None
    focus: str | None = None
    text: str = ""


def _selection(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _clean_target(words: str) -> str | None:
    filler = {"a", "an", "the", "of", "to", "do", "does", "should", "would", "will", "can", "could", "what", "which",
              "are", "is", "be", "were", "was", "as", "like", "other"}
    parts = [part for part in words.split() if part not in filler]
    if not parts:
        return None
    return " ".join(parts[-2:])


def _candidate_drug_words(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9-]{3,}", text)
    candidates = []
    for word in words:
        if word in STOPWORDS or word in candidates:
            continue
        candidates.append(word)
    candidates.sort(key=lambda word: 0 if word.endswith(DRUG_SUFFIXES) else 1)
    return candidates[:6]


def parse(text: str, selection: dict | None = None) -> Intent:
    selection = selection or _selection(text.strip())
    if selection:
        action = str(selection.get("action") or ANALYZE)
        drug = selection.get("drug")
        return Intent(action=FULL_REPORT if action == FULL_REPORT else ANALYZE,
                      drug=str(drug).lower() if drug else None, text=text)

    lowered = " ".join(text.lower().split())
    if not lowered or lowered in {"hi", "hello", "hey", "help", "start", "?"}:
        return Intent(action=HELP, text=text)

    action = FULL_REPORT if FULL_REPORT_PATTERN.search(lowered) else ANALYZE
    target_words = None
    target_effect = None
    match = TARGET_PATTERN.search(lowered)
    if match:
        target_words = _clean_target(match.group(1))
        target_effect = "lowers"
    else:
        match = BLOCKS_PATTERN.search(lowered)
        if match and match.group(1) not in STOPWORDS:
            target_words = match.group(1)
            target_effect = None if match.group(0).startswith("target") else "lowers"

    if target_words and action == ANALYZE and LIST_PATTERN.search(lowered):
        action = LIST_DRUGS

    focus = None
    focus_match = FOCUS_PATTERN.search(lowered)
    if focus_match:
        candidate = focus_match.group(1).strip(" -")
        if candidate and candidate not in GENERIC_FOCUS and not candidate.startswith("side effect"):
            focus = candidate

    excluded = set((target_words or "").split()) | set((focus or "").split())
    drug_words = [word for word in _candidate_drug_words(lowered) if word not in excluded]
    return Intent(action=action, drug_words=drug_words, target_words=target_words, target_effect=target_effect,
                  focus=focus, text=text)


def focus_terms(focus: str | None) -> list[str]:
    """Stems to look for in phenotype names and reaction terms: "infections" -> "infection"."""
    if not focus:
        return []
    stems = []
    for word in focus.split():
        if len(word) < 4 or word in STOPWORDS:
            continue
        for ending in ("ies", "es", "s"):
            if word.endswith(ending) and len(word) - len(ending) >= 4:
                word = word[: -len(ending)] + ("y" if ending == "ies" else "")
                break
        stems.append(word)
    return stems


def matches_focus(prediction: dict, stems: list[str]) -> bool:
    if not stems:
        return False
    haystack = " ".join([prediction.get("phenotype") or "", *(prediction.get("reaction_terms") or [])]).lower()
    return any(stem in haystack for stem in stems)
