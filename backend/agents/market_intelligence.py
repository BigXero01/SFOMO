"""Market Intelligence Agent — market structure, sentiment, on-chain, order flow."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import BaseModel, ValidationError, field_validator

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

_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize(value: Any, max_len: int = 200) -> str:
    """Strip control characters and cap length to prevent prompt injection."""
    return _UNSAFE_RE.sub(" ", str(value))[:max_len]


# ── Bounded sub-models for LLM response validation ────────────────────────────

class _MarketStructure(BaseModel):
    trend_direction: str = "sideways"
    key_support: float = 0.0
    key_resistance: float = 0.0
    higher_highs: bool = False
    higher_lows: bool = False

    @field_validator("trend_direction")
    @classmethod
    def _valid_direction(cls, v: str) -> str:
        if v not in {"up", "down", "sideways"}:
            return "sideways"
        return v

    @field_validator("key_support", "key_resistance")
    @classmethod
    def _positive_price(cls, v: float) -> float:
        return max(0.0, v)


class _MarketSentiment(BaseModel):
    overall: float = 0.0
    fear_greed: int = 50
    social_score: float = 0.0

    @field_validator("overall")
    @classmethod
    def _clamp_overall(cls, v: float) -> float:
        return max(-1.0, min(1.0, v))

    @field_validator("fear_greed")
    @classmethod
    def _clamp_fg(cls, v: int) -> int:
        return max(0, min(100, v))


class _MarketAnalysis(BaseModel):
    """Validated schema for LLM market analysis response."""
    regime: str
    structure: _MarketStructure = _MarketStructure()
    sentiment: _MarketSentiment = _MarketSentiment()
    key_levels: Dict[str, Any] = {}
    news_summary: str = ""
    risk_flags: List[str] = []
    opportunities: List[str] = []

    @field_validator("regime")
    @classmethod
    def _valid_regime(cls, v: str) -> str:
        valid = {r.value for r in MarketRegime}
        if v not in valid:
            return MarketRegime.RANGING.value
        return v

    @field_validator("news_summary")
    @classmethod
    def _cap_news(cls, v: str) -> str:
        return _UNSAFE_RE.sub(" ", v)[:500]

    @field_validator("risk_flags", "opportunities")
    @classmethod
    def _cap_list(cls, v: List[str]) -> List[str]:
        return [_UNSAFE_RE.sub(" ", s)[:200] for s in v[:10]]


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

        # Sanitize all external/user-controlled values before LLM injection
        safe_timeframe = _sanitize(state.timeframe, max_len=4)
        # Sentiment and on-chain are external API data — sanitize numeric values only
        safe_sentiment = {
            k: float(v) if isinstance(v, (int, float)) else 0.0
            for k, v in sentiment.items()
        }
        safe_on_chain = {
            k: float(v) if isinstance(v, (int, float)) else 0.0
            for k, v in on_chain.items()
        }

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Technical context:\n{tech_context}\n\n"
                    f"Sentiment scores: {json.dumps(safe_sentiment)}\n"
                    f"Funding rates: {json.dumps(funding_rates)}\n"
                    f"On-chain metrics: {json.dumps(safe_on_chain)}\n"
                    f"Analyze for timeframe: {safe_timeframe}"
                )
            ),
        ]

        response = await _llm.ainvoke(messages)
        try:
            raw = json.loads(response.content)
            analysis = _MarketAnalysis(**raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(f"[MarketIntelligence] LLM response validation failed: {exc}")
            state.errors.append(f"market_intelligence: invalid LLM response")
            return state

        regime = MarketRegime(analysis.regime)
        structure = analysis.structure.model_dump()
        sentiment_data = analysis.sentiment

        state.candles = candles
        state.order_books = order_books
        state.funding_rates = funding_rates
        state.open_interest = open_interest
        state.sentiment_scores = {s: sentiment_data.overall for s in state.symbols}
        state.on_chain_metrics = on_chain
        state.market_regime = regime
        state.market_structure = structure
        state.news_summary = analysis.news_summary
        state.agent_messages.append(
            f"[MarketIntelligence] Regime={regime.value} | "
            f"Flags={analysis.risk_flags}"
        )

        logger.info(f"[MarketIntelligence] regime={regime.value}")

    except Exception as e:
        logger.error(f"[MarketIntelligence] error: {e}")
        state.errors.append(f"market_intelligence: {str(e)}")

    finally:
        await exchange.close()

    return state
