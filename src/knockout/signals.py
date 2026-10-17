"""Disproportionality on a 2×2 table of FAERS reports, with the Evans criteria (protocol step 7)."""

from dataclasses import dataclass

MIN_REPORTS = 3
MIN_PRR = 2.0
MIN_CHI_SQUARED = 4.0


@dataclass(frozen=True)
class TermCounts:
    term: str
    a: int
    drug: int
    reaction: int
    all: int

    @property
    def expected(self) -> float:
        return self.drug * self.reaction / self.all if self.all else 0.0

    @property
    def prr(self) -> float | None:
        background = self.reaction - self.a
        rest = self.all - self.drug
        if self.drug == 0 or rest <= 0:
            return None
        if background <= 0:
            return float("inf") if self.a else None
        return (self.a / self.drug) / (background / rest)

    @property
    def chi_squared(self) -> float:
        """Pearson chi-squared with Yates correction, 1 degree of freedom."""
        a, b = self.a, self.drug - self.a
        c, d = self.reaction - self.a, self.all - self.drug - (self.reaction - self.a)
        n = a + b + c + d
        denominator = (a + b) * (c + d) * (a + c) * (b + d)
        if denominator == 0:
            return 0.0
        difference = max(abs(a * d - b * c) - n / 2, 0.0)
        return n * difference**2 / denominator

    @property
    def is_signal(self) -> bool:
        prr = self.prr
        return (
            self.a >= MIN_REPORTS
            and prr is not None
            and prr >= MIN_PRR
            and self.chi_squared >= MIN_CHI_SQUARED
        )

    @property
    def underpowered(self) -> bool:
        """Even a doubled reporting rate could not reach the minimum number of reports."""
        return self.a < MIN_REPORTS and 2 * self.expected < MIN_REPORTS
