# Mahoraga — Architecture

Adaptive evolution engine for trading hypotheses. Reads Sentinel-validated
survivors, diagnoses weaknesses, generates intentional adaptations, scores
them, and emits descendants for re-validation.

Mahoraga does not discover. It does not validate. It does not trade. It adapts.

---

## Position in the ecosystem

```
Reality
   ↑
Sentinel              ← validates against reality
   ↑
Library of Alexandria ← remembers
   ↑
Mahoraga              ← adapts
   ↑
Prometheus            ← discovers
```

Mahoraga never touches market data. Reality is reached only through Sentinel
verdicts, surfaced by the Library.

---

## Prime invariants

1. **Mechanism Integrity** — every non-crossover descendant has the same
   `mechanism_id` as its parent. Crossover descendants declare a composite
   mechanism up front.
2. **No untested evolution** — `intake` only yields hypotheses with a sealed
   `sentinel_verdict`.
3. **No blind mutation** — every `Adaptation` carries a `rationale` naming the
   failure mode it targets and the expected improvement.
4. **Budget cap** — at most 5 descendants emitted per survivor per run
   (3 conservative, 1 moderate, 1 aggressive).
5. **Append-only memory** — adaptation history is never rewritten.

If any invariant cannot hold, the descendant is rejected. Mahoraga prefers to
emit nothing rather than emit garbage.

---

## Inputs

All inputs are owned by the Library of Alexandria. Mahoraga is a read-only
consumer of these surfaces:

| Source              | Contents                                                       |
| ------------------- | -------------------------------------------------------------- |
| Survivor Library    | Hypotheses that passed Sentinel, with mechanism manifest       |
| Failure Library     | Hypotheses that failed Sentinel, with failure classification   |
| Sentinel Reports    | Per-run verdicts: regime, cost, sample, expectancy, crowding   |
| Adaptation Memory   | Mahoraga's own history of attempted adaptations + outcomes     |

## Outputs

| Sink                | Contents                                                       |
| ------------------- | -------------------------------------------------------------- |
| Descendant Queue    | Adapted hypotheses, ready for Prometheus/Sentinel re-test      |
| Adaptation Memory   | Lineage: parent → adaptation → descendant → eventual outcome   |
| Rejection Log       | Descendants killed by kill rules, with reason                  |

---

## Pipeline

```
[intake] → [diagnose] → [adapt] → [crossover] → [validate] → [score] → [select] → [emit]
   |          |            |          |             |           |          |          |
   |          |            |          |             |           |          |          └─ Descendant Queue
   |          |            |          |             |           |          └─ Budget: 3 cons / 1 mod / 1 agg
   |          |            |          |             |           └─ 9-dim FitnessScore
   |          |            |          |             └─ Mechanism Integrity + KillRules
   |          |            |          └─ Survivor × Survivor pairings
   |          |            └─ 7 adaptation engines, dispatched by failure mode
   |          └─ Sentinel verdict → structured WeaknessSet
   └─ Survivor + failure + sentinel report join (read-only)
```

Each stage is a pure transformation over typed values from `mahoraga.core`.
The orchestrator is stateless per run; persistence is delegated to `memory`.

---

## Modules

### `mahoraga.core`

Domain primitives. No I/O, no business logic.

- `Mechanism` — the underlying edge (e.g. PEAD, Analyst Revisions). Identity is
  sacred — `mechanism_id` flows unchanged from parent to non-crossover child.
- `Hypothesis` — `Mechanism` + configuration: universe, signal thresholds,
  sizing, holding period, execution model.
- `Survivor` / `Failure` — `Hypothesis` + sealed Sentinel verdict.
- `FailureMode` — enum: `REGIME_DEPENDENT`, `COST_FRAGILE`, `SAMPLE_TOO_SMALL`,
  `LIQUIDITY_CONSTRAINED`, `WEAK_EXPECTANCY`, `CROWDED`, `STRUCTURAL_DECAY`.
- `Adaptation` — typed transformation: `kind` + `delta` + `rationale` +
  `confidence` ∈ {`CONSERVATIVE`, `MODERATE`, `AGGRESSIVE`}.
- `AdaptationKind` — enum of the 7 adaptation engines.
- `Descendant` — `Hypothesis` + lineage (parent_id, adaptation, generation).
- `FitnessScore` — 9 dimensions (see below).

### `mahoraga.intake`

Read-only adapters over the Library of Alexandria.

- `SurvivorLibrary`, `FailureLibrary`, `SentinelReports` — Protocols. Mahoraga
  does not own the storage; concrete implementations live behind these.

### `mahoraga.diagnose`

Turns Sentinel verdicts into structured weaknesses.

- `FailureClassifier` — maps a Sentinel verdict to one or more `FailureMode`s.
- `WeaknessExtractor` — per-hypothesis list of `(FailureMode, evidence, severity)`.

Survivors have weaknesses too — Sentinel reports include sub-threshold
findings. `diagnose` runs against both libraries.

### `mahoraga.adapt`

Seven adaptation engines. Each is dispatched by the failure modes it targets;
none operate freely:

| Engine               | Targets                                                |
| -------------------- | ------------------------------------------------------ |
| `FilterEngine`       | `WEAK_EXPECTANCY`, `COST_FRAGILE`                      |
| `RegimeEngine`       | `REGIME_DEPENDENT`                                     |
| `UniverseEngine`     | `CROWDED`, `LIQUIDITY_CONSTRAINED`, `SAMPLE_TOO_SMALL` |
| `ConfirmationEngine` | `WEAK_EXPECTANCY`                                      |
| `TimingEngine`       | `COST_FRAGILE`, `STRUCTURAL_DECAY`                     |
| `RiskEngine`         | cross-cutting                                          |
| `ExecutionEngine`    | `COST_FRAGILE`                                         |

Engines emit `Adaptation`s — not hypotheses. Materialization into
`Descendant` happens after `validate`.

### `mahoraga.crossover`

Combines two Sentinel-surviving parents into a child. Preconditions:

- both parents are `Survivor`s,
- mechanisms are compatible (compatibility matrix, not freeform),
- the composite mechanism has an explicit economic rationale.

If any precondition fails, the pairing is dropped silently — crossover does
not surface "almost compatible" attempts.

### `mahoraga.validate`

Pre-emit kill rules. A descendant is rejected if any rule fires.

- `MechanismIntegrityChecker` — non-crossover child mechanism must equal
  parent mechanism. Crossover children must match their declared composite.
- `KillRules`:
  - `complexity_increase > threshold`
  - `mechanism_obscured`
  - `data_unavailable`
  - `expected_sample_collapses`
  - `economic_rationale_weak_or_missing`
  - `adaptation_unexplained`
  - `change_motivated_only_by_backtest_optimization`

Rejections are logged with reason. Repeated rejections of the same
`(parent, AdaptationKind)` pair feed back into `memory` to suppress future
attempts.

### `mahoraga.score`

Computes `FitnessScore` over 9 dimensions:

1. `mechanism_integrity`
2. `economic_plausibility`
3. `novelty`
4. `data_availability`
5. `expected_sample_size`
6. `expected_robustness`
7. `expected_sentinel_survival`
8. `complexity_penalty`  *(higher value = worse)*
9. `adaptation_quality`

Scores are independent dimensions, not collapsed to a single number until
selection. Selection enforces the per-survivor budget (3 conservative,
1 moderate, 1 aggressive).

### `mahoraga.memory`

Append-only adaptation log keyed by
`(parent_id, adaptation_kind, descendant_id)`. Records:

- every proposed adaptation,
- every rejection with reason,
- every Sentinel outcome once it lands.

Diagnose and Adapt query this log to avoid repeating failed adaptations
(e.g. if `RegimeEngine` repeatedly produces children that re-fail with
`REGIME_DEPENDENT`, that pattern is suppressed for the parent mechanism).

### `mahoraga.engine`

The orchestrator. Stateless per run:

```python
for survivor in intake.survivors():
    weaknesses = diagnose.extract(survivor)
    proposals  = adapt.propose(survivor, weaknesses)
    proposals += crossover.propose(survivor, intake.survivors())
    valid      = [p for p in proposals if validate.accept(p)]
    scored     = [(p, score.evaluate(p)) for p in valid]
    selected   = select.budget(scored)
    emit(selected)
    memory.record(proposed=proposals, rejected=set(valid) - set(selected),
                  selected=selected)
```

---

## Forbidden mutations

Any adaptation that satisfies any of the following is rejected at `validate`,
not at `score`:

- adds indicators without an economic rationale,
- adds complexity without a justified failure mode,
- optimizes for backtest returns, Sharpe, CAGR, or profit directly,
- creates indicator soup or black-box logic,
- cannot be explained in one sentence in terms of the parent's mechanism.

Selection cannot rescue a forbidden mutation. The kill rules are upstream of
the score deliberately.

---

## Non-goals

- Mahoraga does not generate hypotheses from scratch — that is Prometheus.
- Mahoraga does not run backtests or touch market data — that is Sentinel.
- Mahoraga does not store hypotheses — that is the Library of Alexandria.
- Mahoraga does not optimize for backtest performance. It optimizes for
  expected Sentinel survival of the underlying mechanism.

---

## Repository layout

```
mahoraga/
├── ARCHITECTURE.md          ← this document
├── pyproject.toml
└── src/mahoraga/
    ├── __init__.py
    ├── core.py              ← domain types, enums
    ├── intake.py            ← Library of Alexandria adapters (Protocols)
    ├── diagnose.py          ← FailureClassifier, WeaknessExtractor
    ├── adapt.py             ← 7 adaptation engines
    ├── crossover.py         ← CrossoverEngine
    ├── validate.py          ← MechanismIntegrityChecker, KillRules
    ├── score.py             ← FitnessScorer
    ├── memory.py            ← AdaptationMemory (Protocol)
    └── engine.py            ← orchestrator
```

Each Python module is one of the architecture sections above. The
file-to-section mapping is deliberate — there is no clever decomposition
to learn.
