"""Shared state schema for the LangGraph trading agent pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MarketRegime(str, Enum):
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalStrength(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class TradingSignal(BaseModel):
    symbol: str
    strategy: str
    direction: SignalDirection
    strength: SignalStrength
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PositionSize(BaseModel):
    symbol: str
    signal: TradingSignal
    size_usd: float
    size_units: float
    risk_amount: float
    risk_pct: float
    approved: bool = False
    rejection_reason: str = ""


class ExecutedOrder(BaseModel):
    symbol: str
    side: OrderSide
    size: float
    price: float
    order_id: str
    exchange: str
    fees: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    slippage_pct: float = 0.0


class PortfolioSnapshot(BaseModel):
    total_equity: float
    cash: float
    positions_value: float
    open_positions: Dict[str, Any] = Field(default_factory=dict)
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    peak_equity: float = 0.0
    current_drawdown: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RiskMetrics(BaseModel):
    portfolio_var_1d: float = 0.0
    portfolio_var_5d: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    kill_switch_triggered: bool = False


class TradingState(BaseModel):
    """Complete state passed between LangGraph nodes."""

    # ── Inputs ─────────────────────────────────────────────────
    symbols: List[str] = Field(default_factory=list)
    timeframe: str = "1h"
    cycle_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # ── Market Intelligence ────────────────────────────────────
    candles: Dict[str, Any] = Field(default_factory=dict)
    order_books: Dict[str, Any] = Field(default_factory=dict)
    funding_rates: Dict[str, float] = Field(default_factory=dict)
    open_interest: Dict[str, float] = Field(default_factory=dict)
    sentiment_scores: Dict[str, float] = Field(default_factory=dict)
    on_chain_metrics: Dict[str, Any] = Field(default_factory=dict)
    news_summary: str = ""
    market_regime: MarketRegime = MarketRegime.RANGING
    market_structure: Dict[str, Any] = Field(default_factory=dict)

    # ── Strategy Signals ───────────────────────────────────────
    raw_signals: List[TradingSignal] = Field(default_factory=list)
    filtered_signals: List[TradingSignal] = Field(default_factory=list)
    strategy_weights: Dict[str, float] = Field(default_factory=dict)

    # ── Risk Management ────────────────────────────────────────
    portfolio: Optional[PortfolioSnapshot] = None
    risk_metrics: Optional[RiskMetrics] = None
    approved_positions: List[PositionSize] = Field(default_factory=list)
    rejected_positions: List[PositionSize] = Field(default_factory=list)

    # ── Execution ──────────────────────────────────────────────
    executed_orders: List[ExecutedOrder] = Field(default_factory=list)
    failed_orders: List[Dict[str, Any]] = Field(default_factory=list)

    # ── Portfolio Management ───────────────────────────────────
    rebalance_needed: bool = False
    compounding_allocation: Dict[str, float] = Field(default_factory=dict)
    performance_attribution: Dict[str, float] = Field(default_factory=dict)

    # ── Learning Feedback ──────────────────────────────────────
    closed_trades: List[Dict[str, Any]] = Field(default_factory=list)
    regime_history: List[Dict[str, Any]] = Field(default_factory=list)
    strategy_performance: Dict[str, Any] = Field(default_factory=dict)
    rl_feedback: Dict[str, Any] = Field(default_factory=dict)

    # ── Control Flow ───────────────────────────────────────────
    errors: List[str] = Field(default_factory=list)
    kill_switch: bool = False
    skip_execution: bool = False
    agent_messages: List[str] = Field(default_factory=list)
