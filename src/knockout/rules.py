"""The direction rule (protocol step 3): which genetic diseases a drug's effect on a protein may borrow from."""

from typing import Literal

from helix.discovery.rules import molecule_effect

Pairing = Literal["use", "points_the_other_way", "unknown"]


def target_effect(action_types: list[str | None]) -> str:
    """One effect per target. Records that disagree, or any unreadable record, give `unknown`."""
    effects = {molecule_effect(action_type) for action_type in action_types}
    return effects.pop() if len(effects) == 1 else "unknown"


def pairing(effect: str, direction: str) -> Pairing:
    if effect == "unknown" or direction == "unknown":
        return "unknown"
    if (effect, direction) in {("lowers", "decreased_activity"), ("raises", "increased_activity")}:
        return "use"
    return "points_the_other_way"
