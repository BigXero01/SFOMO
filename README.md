# SFOMO — AI Agent Trading Bot

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
| Risk Management | Kelly-adjusted position sizing, VaR check, drawdown guard, kill switch. |
| Execution | TWAP/market order routing via CCXT, slippage protection. |
| Portfolio Manager | Updates equity, peak tracking, compounding reinvestment, rebalance detection. |
| Learning | Evaluates cycle, adjusts strategy weights, stores memory in Qdrant. |

**5 Trading Strategies:**
- **Trend Following** — EMA crossover with RSI filter
- **Momentum Breakout** — Donchian channel + volume surge
- **Mean Reversion** — Bollinger Bands + RSI extreme
- **Volatility Arb** — Funding rate extremes fade
- **Portfolio Rotation** — Risk-adjusted momentum ranking

**Elite Trader Principles:**
- 0.25–0.5% risk per trade (Kelly-adjusted by confidence)
- 15% max drawdown kill switch
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
| Infra | Docker Compose, GitHub Actions |

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY and exchange credentials

# 2. Start everything
make up

# 3. View logs
make logs

# 4. Open dashboard
open http://localhost:3000

# 5. API docs
open http://localhost:8000/docs
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | GPT-4o for agent reasoning |
| `EXCHANGE_ID` | Yes | binance / bybit / okx / kraken |
| `EXCHANGE_API_KEY` | Yes | Exchange API key |
| `EXCHANGE_API_SECRET` | Yes | Exchange API secret |
| `EXCHANGE_SANDBOX` | Yes | `true` for paper trading |
| `RISK_PER_TRADE` | No | Default 0.005 (0.5%) |
| `MAX_PORTFOLIO_DRAWDOWN` | No | Default 0.15 (15%) |
| `INITIAL_CAPITAL` | No | Default 10000 USDT |

---

## API Endpoints

```
GET  /health                          — System health
GET  /api/v1/portfolio/snapshot       — Current portfolio state
GET  /api/v1/portfolio/performance    — Win rate, PnL, Sharpe
GET  /api/v1/trades/recent            — Recent trade history
POST /api/v1/signals/run-cycle        — Trigger one trading cycle
GET  /api/v1/signals/last-cycle       — Last cycle status and signals
WS   /ws                              — Real-time event stream
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
- Kill switch halts all trading at configured drawdown limit
- Minimum 1.5:1 risk/reward enforced at runtime
- Position size capped at 20% of equity per trade
- All agent decisions logged and stored in Qdrant for audit
