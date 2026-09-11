"""Pre-emit kill rules. Any rule firing rejects the descendant.

Validate is upstream of score, deliberately. A descendant that violates an
invariant cannot be rescued by a high fitness score — selection never sees
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .core import Descendant


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str | None  # set iff accepted is False


class MechanismIntegrityChecker(Protocol):
    """Non-crossover descendants must carry the parent's mechanism unchanged.
    Crossover descendants must match the declared composite mechanism.

    This is the prime invariant. The checker runs before all other kill
    rules so the failure reason is unambiguous."""

    def check(self, descendant: Descendant) -> ValidationResult: ...


class KillRule(Protocol):
    """Single rejection criterion. Stateless; runs in isolation."""

    name: str

    def check(self, descendant: Descendant) -> ValidationResult: ...


# ──────────────────────────────────────────────────────────────────────────────
# The canonical kill rules. Concrete implementations live alongside their
# protocols; this module declares the contract and the registry.
# ──────────────────────────────────────────────────────────────────────────────


class ComplexityIncreaseRule(Protocol):
    """Reject if the descendant's configuration adds more parameters or
    rule branches than a threshold over the parent."""

    name = "complexity_increase"


class MechanismObscuredRule(Protocol):
    """Reject if the rationale cannot be stated in one sentence in terms of
    the parent's mechanism."""

    name = "mechanism_obscured"


class DataUnavailableRule(Protocol):
    """Reject if the adaptation references a data source the Library does
    not provide."""

    name = "data_unavailable"


class ExpectedSampleCollapseRule(Protocol):
    """Reject if the adaptation is expected to drop sample size below the
    Sentinel statistical floor."""

    name = "expected_sample_collapses"


class EconomicRationaleRule(Protocol):
    """Reject if the rationale is missing or fails to explain why the
    adaptation should improve survivability."""

    name = "economic_rationale_weak_or_missing"


class AdaptationUnexplainedRule(Protocol):
    """Reject if the adaptation's delta cannot be tied back to a specific
    Weakness in the survivor's WeaknessSet."""

    name = "adaptation_unexplained"


class BacktestOnlyMotivationRule(Protocol):
    """Reject if the adaptation is justified only by improved historical
    returns / Sharpe / CAGR. Mahoraga does not optimise these."""

    name = "change_motivated_only_by_backtest_optimization"


class Validator(Protocol):
    """Runs MechanismIntegrityChecker, then every KillRule. Short-circuits
    on the first rejection."""

    def accept(self, descendant: Descendant) -> ValidationResult: ...
