"""Seven adaptation engines.

Each engine is dispatched by the failure modes it targets — none operate
freely. Engines emit `Adaptation` objects, not hypotheses. Materialization
into `Descendant` happens after `validate.accept` clears the proposal.
"""

from __future__ import annotations

from typing import Protocol

from .core import (
    Adaptation,
    AdaptationKind,
    FailureMode,
    Survivor,
    WeaknessSet,
)


class AdaptationEngine(Protocol):
    """Common contract for the seven engines."""

    kind: AdaptationKind
    targets: frozenset[FailureMode]

    def propose(
        self, survivor: Survivor, weaknesses: WeaknessSet
    ) -> tuple[Adaptation, ...]:
        """Return zero or more typed Adaptations for this survivor.

        Engines must ignore weaknesses outside their `targets` set. They
        must not invent failure modes. If no weakness matches, return ().
        """
        ...


# ──────────────────────────────────────────────────────────────────────────────
# The seven engines. Each is a separate class so failure-mode → engine
# dispatch is grep-visible and so memory can suppress engines independently.
# ──────────────────────────────────────────────────────────────────────────────


class FilterEngine(Protocol):
    """Strengthen the signal: tighter thresholds, secondary confirmations
    that share the same information source. Targets WEAK_EXPECTANCY and
    COST_FRAGILE (by reducing trade frequency)."""

    kind = AdaptationKind.FILTER
    targets = frozenset({FailureMode.WEAK_EXPECTANCY, FailureMode.COST_FRAGILE})


class RegimeEngine(Protocol):
    """Gate the strategy on a regime indicator (vol, trend, rates).
    Targets REGIME_DEPENDENT."""

    kind = AdaptationKind.REGIME
    targets = frozenset({FailureMode.REGIME_DEPENDENT})


class UniverseEngine(Protocol):
    """Shift or shape the universe — market cap, sector, liquidity tier.
    Targets CROWDED, LIQUIDITY_CONSTRAINED, SAMPLE_TOO_SMALL."""

    kind = AdaptationKind.UNIVERSE
    targets = frozenset({
        FailureMode.CROWDED,
        FailureMode.LIQUIDITY_CONSTRAINED,
        FailureMode.SAMPLE_TOO_SMALL,
    })


class ConfirmationEngine(Protocol):
    """Require a second, independent signal source. Distinct from
    FilterEngine: the confirming signal must come from a different
    information channel. Targets WEAK_EXPECTANCY."""

    kind = AdaptationKind.CONFIRMATION
    targets = frozenset({FailureMode.WEAK_EXPECTANCY})


class TimingEngine(Protocol):
    """Adjust entry, exit, or holding period. Targets COST_FRAGILE (longer
    holds reduce turnover) and STRUCTURAL_DECAY (shorter holds reduce
    exposure to fading signal)."""

    kind = AdaptationKind.TIMING
    targets = frozenset({FailureMode.COST_FRAGILE, FailureMode.STRUCTURAL_DECAY})


class RiskEngine(Protocol):
    """Cross-cutting: position sizing, vol scaling, drawdown caps.
    Operates on weaknesses where signal is sound but the realised
    distribution is fragile."""

    kind = AdaptationKind.RISK
    targets = frozenset[FailureMode]()  # cross-cutting; checked at dispatch


class ExecutionEngine(Protocol):
    """How trades reach the market: VWAP, TWAP, limit ladders. Targets
    COST_FRAGILE."""

    kind = AdaptationKind.EXECUTION
    targets = frozenset({FailureMode.COST_FRAGILE})


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher.
# ──────────────────────────────────────────────────────────────────────────────


class AdaptationDispatcher(Protocol):
    """Routes weaknesses to engines and merges their proposals.

    The dispatcher is the single entry point used by `engine.run`. It is
    also the only place that consults `memory` to suppress engines that
    have repeatedly failed for this parent mechanism."""

    def propose(
        self, survivor: Survivor, weaknesses: WeaknessSet
    ) -> tuple[Adaptation, ...]: ...
