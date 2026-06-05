"""LangGraph orchestration — wires all 6 agents into a trading pipeline."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agents.execution import execution_node
from agents.learning import learning_node
from agents.market_intelligence import market_intelligence_node
from agents.portfolio_manager import portfolio_manager_node
from agents.risk_management import risk_management_node
from agents.strategy import strategy_node
from core.state import TradingState
from config import get_settings

settings = get_settings()


def _should_execute(state: TradingState) -> str:
    """Route: skip execution if kill switch fired or no approved positions."""
    if state.kill_switch:
        return "portfolio_manager"
    if not state.approved_positions:
        return "portfolio_manager"
    return "execution"


def _should_continue(state: TradingState) -> str:
    """After learning, decide whether to loop or end the cycle."""
    if state.kill_switch:
        return END
    return END  # production: return "market_intelligence" for continuous loop


def build_graph() -> StateGraph:
    """Construct the full agent graph."""
    builder = StateGraph(TradingState)

    builder.add_node("market_intelligence", market_intelligence_node)
    builder.add_node("strategy", strategy_node)
    builder.add_node("risk_management", risk_management_node)
    builder.add_node("execution", execution_node)
    builder.add_node("portfolio_manager", portfolio_manager_node)
    builder.add_node("learning", learning_node)

    builder.add_edge(START, "market_intelligence")
    builder.add_edge("market_intelligence", "strategy")
    builder.add_edge("strategy", "risk_management")
    builder.add_conditional_edges(
        "risk_management",
        _should_execute,
        {
            "execution": "execution",
            "portfolio_manager": "portfolio_manager",
        },
    )
    builder.add_edge("execution", "portfolio_manager")
    builder.add_edge("portfolio_manager", "learning")
    builder.add_conditional_edges(
        "learning",
        _should_continue,
        {END: END},
    )

    return builder.compile()


graph = build_graph()


async def run_trading_cycle(
    symbols: list[str] | None = None,
    timeframe: str | None = None,
    config: RunnableConfig | None = None,
) -> TradingState:
    """Execute one full market analysis → execution → learning cycle."""
    initial_state = TradingState(
        cycle_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        symbols=symbols or settings.trading_pairs,
        timeframe=timeframe or settings.timeframe,
        strategy_weights={
            "trend_following": settings.weight_trend_following,
            "momentum_breakout": settings.weight_momentum_breakout,
            "mean_reversion": settings.weight_mean_reversion,
            "volatility_arb": settings.weight_volatility_arb,
            "portfolio_rotation": settings.weight_portfolio_rotation,
        },
    )

    result = await graph.ainvoke(initial_state, config=config or {})
    return TradingState(**result)
