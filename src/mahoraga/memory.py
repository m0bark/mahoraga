"""Append-only adaptation memory.

Keyed by `(parent_id, adaptation_kind, descendant_id)`. Memory is consulted
by diagnose (to recognise persistent failure modes), by the adapt
dispatcher (to suppress engines that keep producing rejected children for
a parent mechanism), and by score (for novelty and expected survival).

Memory never overwrites history. Outcomes are appended as they land from
Sentinel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from .core import (
    AdaptationKind,
    Descendant,
    RejectedDescendant,
    ScoredDescendant,
    SentinelVerdict,
)


@dataclass(frozen=True)
class AdaptationRecord:
    parent_id: str
    descendant_id: str
    adaptation_kind: AdaptationKind
    proposed: bool
    rejected_reason: str | None
    emitted: bool
    sentinel_outcome: SentinelVerdict | None  # filled later, after Sentinel runs


class AdaptationMemory(Protocol):
    """The persistence boundary. Implementations are append-only."""

    def record_proposed(self, descendants: Iterable[Descendant]) -> None: ...

    def record_rejected(self, rejections: Iterable[RejectedDescendant]) -> None: ...

    def record_emitted(self, selected: Iterable[ScoredDescendant]) -> None: ...

    def record_outcome(
        self, descendant_id: str, verdict: SentinelVerdict
    ) -> None: ...

    # Read paths used by diagnose, adapt, and score.

    def rejections_for(
        self, parent_id: str, kind: AdaptationKind
    ) -> int:
        """How many times this (parent, engine) pair has been rejected.
        The adapt dispatcher uses this to suppress repeat offenders."""
        ...

    def outcomes_for(self, parent_id: str) -> Iterable[AdaptationRecord]:
        """Every closed-loop outcome for descendants of this parent."""
        ...
