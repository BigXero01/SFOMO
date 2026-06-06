# Sfomo — AI Agent Trading Bot

> Institutional-style crypto asset management via multi-agent AI.
> Compounds capital through disciplined risk management, not gambling.

---

## Architecture

```
Market Data → AI Analysis → Signal Generation → Risk Validation → Execution → Portfolio Update → Compounding → Dashboard
```

**6 LangGraph Agents, running in sequence each cycle:**

| Agent | Role |
|---|---|
| Market Intelligence | Fetches OHLCV, order books, sentiment, on-chain data. LLM classifies regime. |
| Strategy | Runs 5 strategies, regime-weights signals, LLM filters to high-conviction only. |
| Risk Management | Fixed-fractional position sizing, VaR check, drawdown guard, kill switch. |
| Execution | TWAP/market order routing via CCXT, slippage protection. |
| Portfolio Manager | Updates equity, peak tracking, compounding reinvestment, rebalance detection. |
| Learning | Evaluates cycle, adjusts strategy weights, stores memory in Qdrant. |

**5 Trading Strategies:**
- **Trend Following** — EMA crossover with RSI filter
- **Momentum Breakout** — Donchian channel + volume surge
- **Mean Reversion** — Bollinger Bands + RSI extreme
- **Volatility Arb** — Funding rate extremes fade
- **Portfolio Rotation** — Risk-adjusted momentum ranking

**Risk Principles:**
- 0.25–0.5% risk per trade (confidence-adjusted)
- 15% max drawdown kill switch (Redis-persistent, survives restarts)
- Regime-based strategy weight adjustment
- Compound 80% of profits, reserve 20%
- Min 1.5:1 R:R ratio on every trade

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, asyncio |
| AI Agents | LangGraph, OpenAI GPT-4o |
| Vector Memory | Qdrant |
| Exchange | CCXT (Binance, Bybit, OKX, Kraken) |
| Storage | PostgreSQL + TimescaleDB, Redis Streams |
| Frontend | Next.js 15, TypeScript, Tailwind, Recharts |
| Infra | Docker Compose, Railway |

---

## Quick Start (Local)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — add OPENAI_API_KEY, exchange credentials, SECRET_KEY, API_KEY, ADMIN_KEY

# 2. Start everything
make up

# 3. View logs
make logs

# 4. Open dashboard
open http://localhost:3000
```

---

## Deploy to Railway

This is a **monorepo** with two separate services. Each service must have its
**Root Directory** configured in the Railway dashboard.

### Step-by-step

1. **Create a new Railway project** at [railway.app](https://railway.app)

2. **Add a Backend service**
   - Source → GitHub → select this repo
   - **Settings → Root Directory → `backend`**
   - Add plugins: **PostgreSQL** and **Redis** (auto-injects `DATABASE_URL` and `REDIS_URL`)
   - Set environment variables (see below)

3. **Add a Frontend service**
   - Source → GitHub → select this repo
   - **Settings → Root Directory → `frontend`**
   - Set environment variables (see below)

4. **Add a Qdrant service** (optional — or use [Qdrant Cloud](https://cloud.qdrant.io))

### Backend environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | **Yes** | Min 32 chars. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `API_KEY` | **Yes** | Bearer token for all API endpoints. Generate same way. |
| `ADMIN_KEY` | **Yes** | Separate key for kill-switch reset. Generate independently. |
| `OPENAI_API_KEY` | **Yes** | GPT-4o for agent reasoning |
| `EXCHANGE_ID` | **Yes** | `binance` / `bybit` / `okx` / `kraken` |
| `EXCHANGE_API_KEY` | **Yes** | Exchange API key |
| `EXCHANGE_API_SECRET` | **Yes** | Exchange API secret |
| `EXCHANGE_SANDBOX` | **Yes** | `true` for paper trading |
| `CORS_ORIGINS` | **Yes** | `https://your-frontend.up.railway.app` |
| `QDRANT_URL` | No | Qdrant Cloud URL or internal Railway URL |
| `QDRANT_API_KEY` | No | Qdrant Cloud API key |
| `INITIAL_CAPITAL` | No | Default `10000` |
| `MAX_PORTFOLIO_DRAWDOWN` | No | Default `0.15` (15%) |

### Frontend environment variables

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | **Yes** | Same value as backend `API_KEY` (used server-side by Next.js proxy) |
| `API_URL` | **Yes** | Internal Railway URL of backend, e.g. `https://backend.railway.internal` |
| `NEXT_PUBLIC_WS_URL` | **Yes** | Public WebSocket URL, e.g. `wss://sfomo-backend.up.railway.app` |
| `NEXT_PUBLIC_API_KEY` | **Yes** | Same as `API_KEY` — needed for WebSocket auth |

> **Security note:** `API_KEY` (no `NEXT_PUBLIC_` prefix) is the server-side key
> used by the Next.js proxy for REST calls and never sent to the browser.
> `NEXT_PUBLIC_API_KEY` is only needed for the WebSocket in-message auth handshake.

---

## API Endpoints

```
GET  /health                              — System health
GET  /api/v1/portfolio/snapshot           — Current portfolio state
GET  /api/v1/portfolio/performance        — Win rate, PnL, Sharpe
GET  /api/v1/trades/recent                — Recent trade history
POST /api/v1/signals/run-cycle            — Trigger one trading cycle
GET  /api/v1/signals/last-cycle           — Last cycle status and signals
GET  /api/v1/funds/balances               — Exchange coin balances
GET  /api/v1/funds/deposit-address        — On-chain deposit address
POST /api/v1/funds/withdraw               — Submit withdrawal
POST /api/v1/admin/kill-switch/reset      — Re-enable trading (requires ADMIN_KEY)
WS   /ws                                  — Real-time event stream
WS   /ws/terminal                         — Production terminal
```

---

## Development

```bash
make dev-backend    # Backend hot-reload
make dev-frontend   # Frontend hot-reload
make backtest       # Run strategy backtests
make lint           # Ruff + mypy
make test           # pytest
```

---

## Safety

- **Paper trading by default** (`EXCHANGE_SANDBOX=true`)
- Kill switch halts all trading at configured drawdown limit (Redis-persistent)
- Minimum 1.5:1 risk/reward enforced at runtime
- Position size capped at 20% of equity per trade
- Withdrawal rate limiting via Redis (1 per IP per 60s)
- Separate `ADMIN_KEY` required to reset kill switch (isolated from API key)
- All agent decisions logged in append-only `audit_logs` table
