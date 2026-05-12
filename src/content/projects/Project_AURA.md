# Project AURA

**Automated Unbiased Return Algo** — a production-grade, 24/7 algorithmic trading system for liquid crypto markets. Runs against the live Binance Spot exchange from a self-hosted ARM64 edge node. Designed around deterministic execution, persistent state, and post-incident hardening rather than throughput.

---

## Technical Architecture

- **Engineered a fully synchronous execution engine** to guarantee single-threaded determinism across the data → asset-selection → risk → portfolio → broker pipeline, eliminating an entire class of race conditions inherent in async/event-loop trading stacks.
- **Selected synchronous over async by design** — the system is I/O-bounded by exchange rate limits, not CPU-bounded; `time.sleep()`-paced retry loops produce a strictly auditable execution trace and a single source of truth for portfolio state at any instant.
- **Designed a hot-reloadable configuration plane** (`Cfg/config_overrides.json`) consumed via dataclass-backed `CFG` snapshots, enabling tuning of risk thresholds, regime parameters, and universe filters between cycles with no service restart and no Python module reimport.
- **Built a dual-service topology** — a live trading loop and a walk-forward parameter optimizer — communicating through a single JSON IPC surface, so optimization output flows into live execution with one atomic write.
- **Implemented a 4-stage successive-halving walk-forward optimizer** (ETA=3 reduction, budget-windowed evaluation) that tunes selector, regime, risk, and defensive-overlay knobs against rolling historical windows; scores candidates on a tuple of `(wins, avg_sharpe, avg_excess, avg_aura)` to favor robust generalization over single-window overfit.
- **Architected SQLite-backed persistence** across `events`, `intents`, `orders`, `snapshots`, `heartbeats`, and a `kv` state store, providing crash-safe reconciliation: any broker-acknowledged order whose fill callback is lost is refreshed against the exchange on the next service boot.
- **Hardened the broker reconciliation path** with a sync-failure guard: when a transient `recvWindow` or network error returns an empty exchange position set, the system flags valuation as suspect and skips PM reconciliation that tick rather than wiping in-memory state — eliminating a class of phantom kill-switch trips driven by API blips.
- **Implemented entry-price recovery from persisted snapshots** so that, after a restart, stop-loss enforcement is restored against the original cost basis instead of resetting to current market price.
- **Coded a 2-cycle hysteresis layer** over raw BULL/SIDEWAYS/BEAR regime detection (`BTC` total-return vs configurable threshold over an N-day lookback), requiring N consecutive confirmations before a regime transition commits — suppressing daily regime jitter at the boundary.
- **Built a custom multi-provider market-data layer** with a coverage-aware provider chain (Binance Vision → Tiingo → Polygon → Alpha Vantage → yfinance → CoinGecko), per-symbol Parquet caching, read-through fallback dirs, freshness short-circuits, and provider lookback padding — cutting "possibly delisted" cascade failures and accelerating walk-forward backtests by orders of magnitude.

## Infrastructure & Deployment

- **Deployed the production stack on a Raspberry Pi 5 (Ubuntu/Debian ARM64)** as two long-running `systemd` services — `trading.service` and `propagate.service` — running continuously with `journalctl`-based observability and Telegram notification on every order, regime change, and kill-switch event.
- **Engineered for edge-computing reliability** — low-power footprint (≈ 15 W steady-state), local SSD persistence, and full operational autonomy without dependence on cloud compute; the node has run multi-week stretches across regional power blips with no operator intervention.
- **Constrained BLAS thread pools to 1** (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`) at process boot to prevent NumPy/pandas oversubscription on ARM cores during 600+ symbol walk-forward sweeps.
- **Designed startup invariants** — every service boot performs (a) persistence reconciliation against the exchange, (b) PM-to-broker position sync, (c) entry-price recovery from snapshots, and (d) kill-switch state rehydration from the `kv` store before the first trade can fire.
- **Instrumented permanent diagnostic logging** (`[RISK_TICK]`, `[SL_CHECK]`, `[BOOT]`, `[SYNC_GUARD]`, `[ENTRY_RECOVER]`) — adds ~3 lines/min in steady state and makes silent regressions impossible to miss from `journalctl` alone.
- **Engineered a CCXT-mediated Binance Spot integration** with sell-clamp retry logic, BNB fee reserve management, persistent `clientOrderId` hashing for idempotent replays, and reconciliation passes that mark unreachable orders `RECONCILE_FAILED` rather than leaving them stranded as live pending work.
- **Hardened the kill-switch liquidation path** to retry partial liquidations on network instability — converting a prior single-attempt sell sequence into a verified loop that re-checks exchange positions and re-issues sells until the portfolio is flat.

## Strategic Portfolio Management

> **Operating role: Portfolio Manager.** Full P&L responsibility on live capital. Authority over risk parameters, universe construction, capital-utilization caps, regime thresholds, and the optimizer search space. Every code merge runs against real funds at the next hot-reload cycle.

- **Defined and tune the "Unbiased Return" thesis** — a control-oriented framework that enforces strict adherence to pre-committed parameters (position stability gates, cost-benefit thresholds, regime-aware utilization caps) so that no single trade is influenced by discretionary sentiment or recency bias.
- **Manage a multi-asset crypto universe** anchored on a high-liquidity whitelist (BTC, ETH, BNB, XRP) and a dynamic momentum-screened tail sourced daily from Binance via multi-horizon (6m/12m/24m) return scoring, drawdown caps, and SMA-200 trend filters.
- **Curate the defensive overlay**: in SIDEWAYS / BEAR regimes the system routes a configurable fraction of investable capital into **Pax Gold (PAXG-USD)** as a tokenized-gold safe haven, with a BTC-USD fallback; capital deployment is further governed by regime-specific utilization caps to deliberately retain dry powder during low-conviction tape.
- **Author the composite scoring function** that ranks the universe — a weighted blend of `trend_blend_alpha`-mixed long/short-horizon momentum, Sharpe, max-drawdown depth, and an optional news component — with a regime-multiplier overlay that amplifies momentum in BULL and penalizes volatility in BEAR.
- **Operate a multi-layer risk stack**: per-position stop-loss and take-profit (with persistent entry-price recovery), a rolling-loss kill-switch with configurable baseline window and cooldown, a portfolio-level cost-benefit gate that suppresses uneconomical rebalances, and an overlap-plus-score-improvement gate that suppresses turnover when conviction has not materially changed.
- **Iterate the optimizer search space** — define the propagation grid (regime threshold, trend-blend mixing, stop-loss bands, take-profit triggers, kill-switch sensitivity, defensive weights, utilization caps) and review walk-forward output before promoting any knob change to live capital.
- **Performed root-cause analysis on every live incident** (phantom kill-switch trips, stop-loss reachability regressions, lost fill callbacks, broker timestamp drift, universe screen blackouts during bear regimes) and merged structural fixes — not workarounds — back into the system with verification gates that surface any future recurrence in `journalctl` immediately.
- **Continuously refine the Unbiased Return logic** to balance defensive preservation against momentum capture across regime transitions, tightening the gap between propagation backtest yield and live realized return.

---

**Stack:** Python 3 (synchronous), `pandas`, `NumPy`, `CCXT`, `SQLite`, `systemd`, `journalctl`, custom Walk-Forward engine, Binance Spot REST/WebSocket via CCXT, Telegram bot API.

**Deployment surface:** ARM64 Raspberry Pi 5, Ubuntu/Debian; self-hosted, no cloud dependency.

**Operational mode:** Live capital, 24/7, single-operator portfolio management.
