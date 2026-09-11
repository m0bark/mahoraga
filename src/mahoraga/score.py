"""Fitness scoring and budgeted selection.

Scoring produces a 9-dimensional `FitnessScore`. Dimensions are not
collapsed to a single number until selection, and selection scopes its
ranking to each `AdaptationConfidence` bucket independently — the per-
survivor budget (3 conservative, 1 moderate, 1 aggressive) is a hard cap,
not a soft target.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from .core import (
    AdaptationConfidence,
    Descendant,
    FitnessScore,
    ScoredDescendant,
)


class FitnessScorer(Protocol):
    """Computes FitnessScore for a single descendant.

    Implementations may consult `memory` to inform `novelty` and
    `expected_sentinel_survival` (e.g. similar adaptations that have
    already been validated). They must not consult historical returns."""

    def evaluate(self, descendant: Descendant) -> FitnessScore: ...


class Selector(Protocol):
    """Per-survivor budgeted selection.

    Contract:
      - returns at most 3 CONSERVATIVE, 1 MODERATE, 1 AGGRESSIVE
      - if a bucket has no acceptable candidates, the bucket is emitted
        empty rather than backfilled from another confidence tier
      - ties are broken deterministically (stable sort by descendant id)
    """

    BUDGET: dict[AdaptationConfidence, int] = {
        AdaptationConfidence.CONSERVATIVE: 3,
        AdaptationConfidence.MODERATE: 1,
        AdaptationConfidence.AGGRESSIVE: 1,
    }

    def select(
        self, scored: Iterable[ScoredDescendant]
    ) -> tuple[ScoredDescendant, ...]: ...
