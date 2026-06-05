"""Market Intelligence Agent — market structure, sentiment, on-chain, order flow."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger

from config import get_settings
from core.state import MarketRegime, TradingState
from services.exchange import ExchangeService
from services.market_data import MarketDataService

settings = get_settings()

_llm = ChatOpenAI(
    model=settings.openai_model,
    temperature=0,
    api_key=settings.openai_api_key,
)

SYSTEM_PROMPT = """You are an elite crypto market intelligence analyst.
Analyze the provided market data and return a JSON object with:
{
  "regime": "<bull_trend|bear_trend|ranging|high_volatility|low_volatility|accumulation|distribution>",
  "structure": {
    "trend_direction": "<up|down|sideways>",
    "key_support": <float>,
    "key_resistance": <float>,
    "higher_highs": <bool>,
    "higher_lows": <bool>
  },
  "sentiment": {
    "overall": <float -1 to 1>,
    "fear_greed": <int 0-100>,
    "social_score": <float>
  },
  "key_levels": {<symbol>: {"support": <float>, "resistance": <float>}},
  "news_summary": "<brief summary of relevant news>",
  "risk_flags": ["<list of risk flags>"],
  "opportunities": ["<list of opportunities>"]
}
Return only valid JSON, no markdown."""


def _compute_technical_context(candles: Dict[str, Any]) -> str:
    """Compute a concise technical summary from OHLCV candles."""
    summaries = []
    for symbol, data in list(candles.items())[:5]:
        if not data or "close" not in data:
            continue
        closes = data.get("close", [])
        if len(closes) < 20:
            continue
        price = closes[-1]
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma20
        pct_change_24h = ((price - closes[-25]) / closes[-25] * 100) if len(closes) > 25 else 0
        summaries.append(
            f"{symbol}: price={price:.4f}, sma20={sma20:.4f}, sma50={sma50:.4f}, "
            f"24h_change={pct_change_24h:.2f}%"
        )
    return "\n".join(summaries) if summaries else "No candle data available"


async def market_intelligence_node(state: TradingState) -> TradingState:
    """Fetch market data and classify regime via LLM analysis."""
    logger.info(f"[MarketIntelligence] cycle={state.cycle_id}")

    exchange = ExchangeService()
    market_data = MarketDataService()

    try:
        candles: Dict[str, Any] = {}
        order_books: Dict[str, Any] = {}
        funding_rates: Dict[str, float] = {}
        open_interest: Dict[str, float] = {}

        for symbol in state.symbols:
            try:
                candles[symbol] = await exchange.fetch_ohlcv(symbol, state.timeframe, limit=100)
                order_books[symbol] = await exchange.fetch_order_book(symbol, limit=20)
                if "/" in symbol:
                    funding_rates[symbol] = await exchange.fetch_funding_rate(symbol)
                    open_interest[symbol] = await exchange.fetch_open_interest(symbol)
            except Exception as e:
                logger.warning(f"[MarketIntelligence] data error {symbol}: {e}")

        sentiment = await market_data.fetch_sentiment(state.symbols)
        on_chain = await market_data.fetch_on_chain_metrics(["BTC", "ETH"])

        tech_context = _compute_technical_context(candles)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Technical context:\n{tech_context}\n\n"
                    f"Sentiment scores: {json.dumps(sentiment)}\n"
                    f"Funding rates: {json.dumps(funding_rates)}\n"
                    f"On-chain metrics: {json.dumps(on_chain)}\n"
                    f"Analyze for timeframe: {state.timeframe}"
                )
            ),
        ]

        response = await _llm.ainvoke(messages)
        analysis = json.loads(response.content)

        regime = MarketRegime(analysis.get("regime", "ranging"))
        structure = analysis.get("structure", {})
        sentiment_data = analysis.get("sentiment", {})

        state.candles = candles
        state.order_books = order_books
        state.funding_rates = funding_rates
        state.open_interest = open_interest
        state.sentiment_scores = {s: sentiment_data.get("overall", 0.0) for s in state.symbols}
        state.on_chain_metrics = on_chain
        state.market_regime = regime
        state.market_structure = structure
        state.news_summary = analysis.get("news_summary", "")
        state.agent_messages.append(
            f"[MarketIntelligence] Regime={regime.value} | "
            f"Flags={analysis.get('risk_flags', [])}"
        )

        logger.info(f"[MarketIntelligence] regime={regime.value}")

    except Exception as e:
        logger.error(f"[MarketIntelligence] error: {e}")
        state.errors.append(f"market_intelligence: {str(e)}")

    finally:
        await exchange.close()

    return state
