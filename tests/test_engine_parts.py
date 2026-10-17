import math

import pytest

from knockout import genetics, label_match, rules
from knockout.openfda import Label
from knockout.signals import TermCounts


def test_prr_and_evans_criteria_on_the_eculizumab_counts():
    counts = TermCounts(term="MENINGOCOCCAL INFECTION", a=86, drug=54_046, reaction=311, all=20_692_690)
    assert counts.prr == pytest.approx((86 / 54_046) / (225 / (20_692_690 - 54_046)))
    assert round(counts.prr) == 146
    assert counts.chi_squared > 4
    assert counts.is_signal


def test_signal_needs_three_reports():
    assert not TermCounts(term="X", a=2, drug=100, reaction=10, all=1_000_000).is_signal


def test_yates_chi_squared_matches_the_textbook_formula():
    counts = TermCounts(term="X", a=10, drug=100, reaction=50, all=1_000)
    a, b, c, d = 10, 90, 40, 860
    n = a + b + c + d
    expected = n * (abs(a * d - b * c) - n / 2) ** 2 / ((a + b) * (c + d) * (a + c) * (b + d))
    assert math.isclose(counts.chi_squared, expected)


def test_underpowered_when_a_doubled_rate_cannot_reach_three_reports():
    assert TermCounts(term="X", a=0, drug=50, reaction=100, all=10_000_000).underpowered
    assert not TermCounts(term="X", a=0, drug=50_000, reaction=10_000, all=10_000_000).underpowered


@pytest.mark.parametrize(
    ("effect", "direction", "expected"),
    [
        ("lowers", "decreased_activity", "use"),
        ("raises", "increased_activity", "use"),
        ("lowers", "increased_activity", "points_the_other_way"),
        ("raises", "decreased_activity", "points_the_other_way"),
        ("unknown", "decreased_activity", "unknown"),
        ("lowers", "unknown", "unknown"),
    ],
)
def test_direction_rule(effect, direction, expected):
    assert rules.pairing(effect, direction) == expected


def test_conflicting_action_types_give_unknown():
    assert rules.target_effect(["INHIBITOR", "INHIBITOR"]) == "lowers"
    assert rules.target_effect(["INHIBITOR", "AGONIST"]) == "unknown"
    assert rules.target_effect(["MODULATOR"]) == "unknown"


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        ("Very frequent (99-80%)", True),
        ("Frequent (79-30%)", True),
        ("Frequent", True),
        ("Obligate (100%)", True),
        ("Occasional (29-5%)", False),
        ("Very rare", False),
        ("2/2", True),
        ("3/10", True),
        ("2/10", False),
        (None, False),
    ],
)
def test_frequency_threshold(frequency, expected):
    assert genetics.frequency_qualifies(frequency) is expected


def test_label_match_is_whole_phrase_with_plural():
    label = Label(
        set_id="s",
        effective_time="20260101",
        generic_names=("ECULIZUMAB",),
        sections={"boxed_warning": "WARNING: SERIOUS MENINGOCOCCAL INFECTIONS. Vaccinate patients first."},
    )
    match = label_match.find(label, ["MENINGOCOCCAL INFECTION"])
    assert match is not None and match.section == "boxed_warning"
    assert match.sentence.startswith("WARNING: SERIOUS MENINGOCOCCAL INFECTIONS")
    assert label_match.find(label, ["INFECTIONS OF THE EAR"]) is None
    assert label_match.term_pattern("SEPSIS").search("asepsis") is None


@pytest.mark.live
def test_eculizumab_steps_6_and_7_on_live_data():
    from knockout import openfda
    from knockout.engine import _count

    label = openfda.label("eculizumab")
    assert label is not None
    match = label_match.find(label, ["MENINGOCOCCAL INFECTION"])
    assert match is not None and match.section == "boxed_warning"
    counts = _count("eculizumab", "MENINGOCOCCAL INFECTION", openfda.total(openfda.drug_search("eculizumab")),
                    openfda.total(None))
    assert counts.a >= 3 and counts.is_signal
