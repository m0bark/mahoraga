"""Combine two Sentinel-surviving parents into a composite child.

Crossover is the only path by which mechanism identity legitimately changes.
The composite mechanism must be declared up-front with its own rationale —
not invented from the parents' names.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from .core import Descendant, Mechanism, Survivor


class MechanismCompatibility(Protocol):
    """Closed compatibility matrix between mechanisms.

    Crossover is not freeform — only declared, economically-explained
    combinations are permitted (e.g. PEAD × Analyst Revisions, because both
    are post-event information-asymmetry mechanisms with the same direction
    of trade)."""

    def compatible(self, a: Mechanism, b: Mechanism) -> bool: ...

    def composite(self, a: Mechanism, b: Mechanism) -> Mechanism:
        """Return the composite mechanism. Must raise if not compatible —
        the composite's rationale carries the economic story for the
        combination, not the engine."""
        ...


class CrossoverEngine(Protocol):
    """Pairs a survivor against the survivor pool and yields candidate
    children.

    The engine drops incompatible pairs silently; it does not surface
    "almost compatible" attempts. Repeated drops do not waste memory."""

    def propose(
        self, survivor: Survivor, pool: Iterable[Survivor]
    ) -> tuple[Descendant, ...]: ...
