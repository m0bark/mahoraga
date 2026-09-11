"""Sentinel verdict → structured WeaknessSet.

Diagnose runs against both libraries — survivors carry sub-threshold
findings that are still adaptation targets.
"""

from __future__ import annotations

from typing import Protocol

from .core import FailureMode, SentinelVerdict, Survivor, Weakness, WeaknessSet


class FailureClassifier(Protocol):
    """Maps a Sentinel verdict to the failure modes it expresses.

    A verdict may map to zero or more modes. Survivors with a clean verdict
    yield an empty result; adapt will produce nothing for them and that is
    correct."""

    def classify(self, verdict: SentinelVerdict) -> tuple[FailureMode, ...]: ...


class WeaknessExtractor(Protocol):
    """Produces the per-survivor weakness set used by adapt.

    Each Weakness carries its evidence and severity so adapt can choose
    between conservative, moderate, and aggressive responses."""

    def extract(self, survivor: Survivor) -> WeaknessSet: ...


def empty() -> WeaknessSet:
    """Convenience for diagnose impls that need a no-weakness sentinel."""
    return tuple[Weakness, ...]()
