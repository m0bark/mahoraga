"""Mahoraga orchestrator. Stateless per run.

The orchestrator is intentionally thin — it sequences the pipeline laid out
in ARCHITECTURE.md and delegates every interesting decision to a typed
collaborator. New behaviour belongs in one of those collaborators, not
here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .adapt import AdaptationDispatcher
from .core import (
    Descendant,
    RejectedDescendant,
    ScoredDescendant,
    Survivor,
    SurvivorReport,
)
from .crossover import CrossoverEngine
from .diagnose import WeaknessExtractor
from .intake import SurvivorLibrary
from .memory import AdaptationMemory
from .score import FitnessScorer, Selector
from .validate import Validator


@dataclass(frozen=True)
class Mahoraga:
    """Dependency-injected orchestrator. Build it once per run."""

    survivors: SurvivorLibrary
    diagnose: WeaknessExtractor
    adapt: AdaptationDispatcher
    crossover: CrossoverEngine
    validate: Validator
    score: FitnessScorer
    select: Selector
    memory: AdaptationMemory

    def run(self) -> Iterable[SurvivorReport]:
        """Drive the pipeline once over every survivor.

        Yields a SurvivorReport per survivor — including those with no
        weaknesses (where every bucket is empty). Emission to the
        Descendant Queue is the caller's responsibility; this method
        returns the structured reports promised by the spec.
        """
        survivor_pool = list(self.survivors.survivors())
        for survivor in survivor_pool:
            yield self._run_one(survivor, survivor_pool)

    def _run_one(
        self, survivor: Survivor, pool: list[Survivor]
    ) -> SurvivorReport:
        weaknesses = self.diagnose.extract(survivor)

        # 1. Propose
        proposed_descendants: list[Descendant] = []
        for adaptation in self.adapt.propose(survivor, weaknesses):
            proposed_descendants.append(
                _materialize(survivor, adaptation, generation=_next_gen(survivor))
            )
        proposed_descendants.extend(self.crossover.propose(survivor, pool))

        # 2. Validate
        accepted: list[Descendant] = []
        rejected: list[RejectedDescendant] = []
        for descendant in proposed_descendants:
            result = self.validate.accept(descendant)
            if result.accepted:
                accepted.append(descendant)
            else:
                assert result.reason is not None
                rejected.append(RejectedDescendant(descendant, result.reason))

        # 3. Score
        scored: list[ScoredDescendant] = [
            ScoredDescendant(d, self.score.evaluate(d)) for d in accepted
        ]

        # 4. Select within per-survivor budget
        selected = self.select.select(scored)

        # 5. Persist
        self.memory.record_proposed(proposed_descendants)
        self.memory.record_rejected(rejected)
        self.memory.record_emitted(selected)

        return _to_report(survivor, weaknesses, selected, rejected)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers. Materialisation and report shaping are deterministic —
# they belong here so the orchestrator stays the only place that reads the
# full pipeline shape.
# ──────────────────────────────────────────────────────────────────────────────


def _materialize(survivor: Survivor, adaptation, generation: int) -> Descendant:
    """Apply the Adaptation's delta to the survivor's Hypothesis to produce
    a child. Concrete delta semantics live alongside each engine — this
    helper is the seam where they plug in."""
    raise NotImplementedError("plug in per-engine materialisation")


def _next_gen(survivor: Survivor) -> int:
    """Read the parent's generation from its hypothesis config, default 0."""
    raise NotImplementedError


def _to_report(
    survivor: Survivor,
    weaknesses,
    selected,
    rejected,
) -> SurvivorReport:
    """Partition the selected descendants into the conservative / moderate /
    aggressive buckets promised by the spec."""
    raise NotImplementedError
