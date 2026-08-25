# Project AURA

**Automated Unbiased Return Algo** — a production-grade, 24/7 algorithmic trading system running live capital on Binance Spot, deployed on a self-hosted ARM64 edge node.

I am simultaneously the **system architect, the SRE, and the portfolio manager** with full P&L responsibility.

---

## What I Built

- **Synchronous execution engine** — a deliberate design choice: the system is I/O-bounded by exchange rate limits, so a single-threaded, `time.sleep()`-paced loop yields a strictly auditable trace and one source of truth for portfolio state.
- **4-stage walk-forward optimizer** (successive-halving, ETA=3) that tunes selector, regime, and risk parameters against rolling historical windows and scores on a `(wins, sharpe, excess, aura)` tuple to favor generalization over single-window overfit.
- **SQLite-backed persistence** across events, intents, orders, snapshots, and heartbeats — every boot reconciles unacknowledged fills against the exchange, recovers entry prices, and rehydrates kill-switch state before the first trade.
- **Multi-provider market-data layer** (Binance Vision → Tiingo → Polygon → Alpha Vantage → yfinance → CoinGecko) with per-symbol Parquet caching, cutting cascade failures and accelerating backtests by orders of magnitude.
- **Sync-failure guard** on the broker reconciliation path — transient empty position sets are flagged as suspect instead of wiping in-memory state, eliminating a class of phantom kill-switch trips.

---

## Portfolio Management

- Operate a multi-asset crypto universe: a high-liquidity anchor (BTC, ETH, BNB, XRP) plus a dynamic momentum-screened tail ranked on multi-horizon return, Sharpe, drawdown depth, and SMA-200 trend filters.
- Multi-layer risk stack: per-position stop-loss/take-profit with persistent entry-price recovery, a rolling-loss kill-switch, a portfolio-level cost-benefit gate, and an overlap gate that suppresses uneconomical turnover.
- Regime-aware defensive overlay routes a configurable fraction of capital into PAXG (tokenized gold) in SIDEWAYS/BEAR regimes.
- Root-caused every live incident — phantom kill-switch trips, lost fill callbacks, broker timestamp drift — and merged structural fixes back with permanent diagnostic logging.

---

## Deployment

Raspberry Pi 5 (ARM64, Ubuntu/Debian), two `systemd` services with `journalctl` observability and Telegram notifications on every order, regime change, and kill-switch event. **~15 W steady-state, no cloud dependency, live 24/7.**

**Stack:** Python 3, pandas, NumPy, CCXT, SQLite, systemd, Binance Spot REST/WebSocket, custom walk-forward engine.
