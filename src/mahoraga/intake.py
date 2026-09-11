"""Read-only adapters over the Library of Alexandria.

Mahoraga does not own this storage. These Protocols define what the engine
needs; concrete implementations live in the Library and are injected at
runtime.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from .core import Failure, SentinelVerdict, Survivor


class SurvivorLibrary(Protocol):
    """Yields every hypothesis that has passed Sentinel."""

    def survivors(self) -> Iterable[Survivor]: ...


class FailureLibrary(Protocol):
    """Yields every hypothesis that has failed Sentinel. Used by diagnose
    (to recognise recurring failure modes) and by memory (to avoid
    proposing re-runs of already-killed children)."""

    def failures(self) -> Iterable[Failure]: ...


class SentinelReports(Protocol):
    """Per-hypothesis access to the latest sealed Sentinel verdict.

    Survivors and Failures already carry their verdict; this protocol is
    for cross-referencing (e.g. checking siblings of a survivor in the same
    mechanism family)."""

    def latest(self, hypothesis_id: str) -> SentinelVerdict | None: ...
