"""Domain primitives. No I/O, no business logic.

These are the only types crossing module boundaries inside Mahoraga. Each
field that affects an invariant in ARCHITECTURE.md is documented at the
point of declaration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


# ──────────────────────────────────────────────────────────────────────────────
# Failure modes — the closed set of weaknesses Mahoraga can diagnose.
# ──────────────────────────────────────────────────────────────────────────────


class FailureMode(Enum):
    REGIME_DEPENDENT = "regime_dependent"
    COST_FRAGILE = "cost_fragile"
    SAMPLE_TOO_SMALL = "sample_too_small"
    LIQUIDITY_CONSTRAINED = "liquidity_constrained"
    WEAK_EXPECTANCY = "weak_expectancy"
    CROWDED = "crowded"
    STRUCTURAL_DECAY = "structural_decay"


# ──────────────────────────────────────────────────────────────────────────────
# Adaptation taxonomy.
# ──────────────────────────────────────────────────────────────────────────────


class AdaptationKind(Enum):
    """The seven adaptation engines. No engine emits an Adaptation outside
    this enum."""

    FILTER = "filter"
    REGIME = "regime"
    UNIVERSE = "universe"
    CONFIRMATION = "confirmation"
    TIMING = "timing"
    RISK = "risk"
    EXECUTION = "execution"


class AdaptationConfidence(Enum):
    """Per-survivor budget: 3 conservative, 1 moderate, 1 aggressive."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


# ──────────────────────────────────────────────────────────────────────────────
# Sentinel verdict — what comes back from reality, via the Library.
# ──────────────────────────────────────────────────────────────────────────────


class SentinelOutcome(Enum):
    SURVIVED = "survived"
    FAILED = "failed"


@dataclass(frozen=True)
class SentinelVerdict:
    """Sealed result from Sentinel. Mahoraga treats this as ground truth."""

    outcome: SentinelOutcome
    failure_modes: tuple[FailureMode, ...]
    evidence: Mapping[str, float]
    report_id: str


# ──────────────────────────────────────────────────────────────────────────────
# Mechanism and hypothesis. Mechanism identity is the prime invariant.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Mechanism:
    """The underlying edge. Identity flows unchanged through non-crossover
    adaptation. Crossover children declare a composite mechanism whose
    `id` is derived from its parents' ids."""

    id: str
    name: str
    rationale: str


@dataclass(frozen=True)
class Hypothesis:
    """A configured strategy built on a Mechanism. The `mechanism` field is
    immutable — any adaptation that changes it is rejected at validate."""

    id: str
    mechanism: Mechanism
    config: Mapping[str, object]


@dataclass(frozen=True)
class Survivor:
    """A Hypothesis that passed Sentinel. Carries the verdict so diagnose
    can read sub-threshold findings."""

    hypothesis: Hypothesis
    verdict: SentinelVerdict


@dataclass(frozen=True)
class Failure:
    """A Hypothesis that failed Sentinel. Used by diagnose and memory; never
    adapted directly."""

    hypothesis: Hypothesis
    verdict: SentinelVerdict


# ──────────────────────────────────────────────────────────────────────────────
# Weakness — diagnose's structured output.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Weakness:
    mode: FailureMode
    evidence: Mapping[str, float]
    severity: float  # 0..1; 1 = certain failure mode active


WeaknessSet = tuple[Weakness, ...]


# ──────────────────────────────────────────────────────────────────────────────
# Adaptation and descendant.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Adaptation:
    """A typed, intentional transformation. `rationale` names the failure
    mode targeted and the expected improvement — without it, validate
    rejects."""

    kind: AdaptationKind
    confidence: AdaptationConfidence
    targets: tuple[FailureMode, ...]
    delta: Mapping[str, object]
    rationale: str


@dataclass(frozen=True)
class Descendant:
    """A child Hypothesis with lineage. `mechanism` MUST equal the parent's
    mechanism (or the declared composite for crossover children)."""

    hypothesis: Hypothesis
    parent_id: str
    crossover_parent_id: str | None
    adaptation: Adaptation
    generation: int


# ──────────────────────────────────────────────────────────────────────────────
# Fitness — 9 dimensions, not collapsed to a scalar.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FitnessScore:
    """0..100 per dimension. `complexity_penalty` is the only dimension where
    higher is worse; the others are higher-is-better. Selection ranks within
    each AdaptationConfidence bucket independently."""

    mechanism_integrity: int
    economic_plausibility: int
    novelty: int
    data_availability: int
    expected_sample_size: int
    expected_robustness: int
    expected_sentinel_survival: int
    complexity_penalty: int
    adaptation_quality: int


# ──────────────────────────────────────────────────────────────────────────────
# Emission record — what leaves Mahoraga and what memory persists.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoredDescendant:
    descendant: Descendant
    score: FitnessScore


@dataclass(frozen=True)
class RejectedDescendant:
    descendant: Descendant
    reason: str  # which KillRule fired or which invariant was violated


@dataclass(frozen=True)
class SurvivorReport:
    """The per-survivor output shape promised by the spec."""

    survivor_id: str
    original_mechanism: Mechanism
    weaknesses: WeaknessSet
    sentinel_feedback: SentinelVerdict
    conservative: tuple[ScoredDescendant, ...]  # exactly 3 when budget filled
    moderate: tuple[ScoredDescendant, ...]      # exactly 1 when budget filled
    aggressive: tuple[ScoredDescendant, ...]    # exactly 1 when budget filled
    rejected: tuple[RejectedDescendant, ...] = field(default_factory=tuple)
