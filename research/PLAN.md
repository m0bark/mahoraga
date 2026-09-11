# The Alexandria Loop — system blueprint (2026-08-27)

Plan only — nothing built. Produced by a nine-agent adversarial design debate
(four opposed architects → four red-teams → synthesis), against four locked
user constraints: **≤$100/mo · signals-only (human trades) · $6 VPS + QC ·
capital <$25k**. Full designed version: see the published artifact
"The Alexandria Loop".

**The product is the weekly digest. Everything upstream exists only to
decide, verifiably, what that digest is allowed to contain. "No trade this
week" is first-class output.**

## Where the red team drew blood (what shaped the design)

1. All four six-month failure stories died at month 3–4: quota pressure
   ("≥1 signal/month") eroding kill rules — one story ends in four
   individually-clean pre-registered revisions producing a laundered overfit
   with an immaculate audit trail.
2. Pre-registration launders already-mined hypotheses: the weekly-loser
   t=3.0 was found on the same window a "confirmation" would reuse.
3. Locally-hidden holdout years are theater — every QC run reads the full
   period, burning the holdout for the family on run one.
4. The paper gate has no statistical power (n=4 rebalances) and runs the
   backtest's own fill models — it can only confirm the backtest at itself.
5. The human is the least-monitored component; every failure routed through
   an unlogged fill or a skipped ritual.

## Principles

1. QuantConnect is the sole verdict engine; local P&L numbers are banned
   from the ledger; no local backtester will ever exist.
2. Discipline lives in code: the Gatekeeper CLI *refuses* runs without a
   remote-pushed pre-registration hash, an unspent token, a complete card.
   A nightly audit diffs all QC account backtests against the ledger.
3. The append-only capture-timestamped archive is the only irreplaceable
   asset. Raw now, parse later; corrections are new rows; gaps are records;
   backfills are flagged and refused for features.
4. Verdicts never queue behind plumbing they don't consume.
5. Gates measure only what their sample size supports.
6. Every card carries an evidential class (DISCOVERY / REPLICATION /
   CONFIRMATION / RETROSPECTIVE) + family cumulative trial count.
7. Fail-safe default: no signal → no trade → an alert.
8. Dead-man switches on machines AND human rituals.
9. Budget is governance: 8 QC backtests/month as tokens; 10 lifetime shots
   per mechanism family; 2 revision cards max per near-miss; generation-
   scaled thresholds; 1.5× rollover cap.
10. Zero-survivor months are on-plan — pre-committed in writing in Phase 0.

## Key resolutions (condensed; full list in the artifact)

- **Quota vs discipline**: redefine the deliverable — pre-survivor months
  deliver the labeled paper digest + monthly verdict report; promotion
  criteria may never reference the quota.
- **No calibrating QC to the local sweep**: harness acceptance is structural
  only; a cost-driven FAIL is phase success; the reversal run is REPLICATION.
- **Parallel build**: first verdicts (weeks 2–4) use QC-native price +
  Morningstar PIT fundamentals only, alongside collector hardening.
- **Collect only the evanescent**: Stocktwits trending 30-min, Reddit hourly
  with score re-capture. EDGAR/FINRA/news fetched on demand (free archives).
- **Real holdout**: verdict runs end 2022-12-31; ONE recorded holdout run
  (2023+) per surviving family, token-consuming, required for promotion.
- **Baselines in-run**: candidate + dumb baseline + turnover-matched
  multi-seed random ranker inside the SAME QC backtest, plus SPY benchmark.
- **Paper gate is operational only**: performance conclusions forbidden at
  n<13; long-horizon kill rules only; 13–26 weeks paper before any real dollar.
- **Seal = push**: pre-registration sealed by GitHub remote push timestamp +
  OpenTimestamps anchor; nightly off-ledger-backtest tripwire.
- **Storage**: SQLite WAL 24h buffer → immutable day-partitioned zstd
  Parquet + SHA-256 manifests → Backblaze B2 mirror.
- **Alt-data**: capture-only in this plan; mine weeks 1–52 / confirm 53+;
  first trustworthy alt-data verdict ≈ month 12–18. Near-term edges come
  from price + fundamentals.
- **Scouting universe**: universe-sensitive scans move to free QC research
  notebooks (point-in-time universes); local cache stamped
  SURVIVORSHIP-BIASED — SCOUTING ONLY.
- **Human monitoring**: Telegram digest with placed/skipped ack buttons,
  echo-back fill replies, missing fills = gap rows + red digest, auto-degrade
  to monitoring mode after 14 dark days.

## Components

| Component | Runs | Role |
|---|---|---|
| Harvesters | VPS | Stocktwits 30-min + Reddit hourly w/ score re-capture; raw even on parse failure |
| Point-in-Time Store | VPS+B2 | append-only SQLite buffer → immutable Parquet + manifests → B2 |
| Watchtower | VPS | dead-man per timer, daily Telegram digest, quarterly drills |
| Library of Alexandria | GitHub | hypothesis cards, ledger.csv, archived QC JSONs, gap/holdout records; seeded with the corpses day one |
| Gatekeeper (`alex` CLI) | PC+VPS | the only door to a verdict; refuses, then seals mechanically |
| Prometheus | PC+QC notebooks | mechanism-first scouting, structurally untrusted |
| Feature Foundry | VPS | PIT weekly features; 3 standing lookahead guards; dormant till depth gates |
| Sentinel | QC | one pre-registered cloud backtest per verdict; 3 tracks in-run |
| Mahoraga | PC monthly | ≤5 mechanism-preserving descendants per verdict, each token-consuming |
| Herald | QC paper node+VPS | Sunday digest, acks, fills loop, slippage check, degrade mode |

## Phases

- **P0 (wk 1)** Library + Gatekeeper + QC fact-check + pre-commitment doc.
  Done when: corpses queryable; `alex run` refuses unsealed/unbudgeted runs;
  QC cost sheet empirically confirmed.
- **P1 (wk 1–3, ∥P2)** Collector hardening + Watchtower. Done when: 14 days
  ≥95% captures per source (or explicit gaps); kill-drill alerts; B2 restore
  byte-identical.
- **P2 (wk 2–4, ∥P1)** First verdicts on QC-native data: reversal
  REPLICATION (dual fill models, ends 2022-12-31) + NN ranker frozen test.
  Done when: both sealed regardless of outcome; failure-branch doc predates
  verdicts in git.
- **P3 (wk 4–7)** Feature Foundry + QC bridge, then dormant. Done when:
  planted-future-row rejects; truncated-DB byte-identity in CI; QC canary
  can't see the future.
- **P4 (wk 7–12)** Herald paper gate (operational only). Done when: 4
  consecutive pre-open digests incl. one honest "no trade"; fill loop
  round-trips; missed-delivery drill caught; "no performance conclusions at
  n=4" written into the phase doc.
- **P5 (mo 4–6)** Steady state + Mahoraga cadence. Done when: a full monthly
  cycle reconciles with zero off-ledger runs; every month = signal/paper
  digest OR recorded on-plan disciplined silence — never a loosened gate.

## Not building

Auto-execution/broker APIs · any local backtester · X/Twitter · collectors
for reconstructible data · self-hosted fundamentals · Docker/Airflow/Kafka ·
DB servers/webservers/open ports · dashboards · intraday · ML infra
(GPU/MLflow/feature stores) · LLM sentiment in v1 · autonomous LLM
hypothesis generators · model zoos · options/crypto/futures · paid data
before a sealed verdict names the need.

## Budget

~$7/mo (months 1–3, free QC tier) → ~$17–47 steady → ~$87 worst case
(paid QC seat). Headroom deliberately unspent; a new data source claims it
only via a sealed verdict.

## Open decisions (the user's)

D1 sign the quota redefinition (the load-bearing one) · D2 holdout cutoff
(2022-12-31?) · D3 QC seat now vs when free tier binds · D4 Telegram vs
email-first · D5 RSS in v1 or deferred · D6 family-cap constants (10 / 2 /
1.5×) · D7 VPS x86 vs ARM.
