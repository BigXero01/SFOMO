"""Market data service — sentiment, on-chain, news aggregation."""
from __future__ import annotations

from typing import Any, Dict, List

import httpx
from loguru import logger

from config import get_settings

settings = get_settings()

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
COINGECKO_SENTIMENT = "https://api.coingecko.com/api/v3/global"


class MarketDataService:
    """Aggregates sentiment and on-chain metrics from multiple sources."""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=10.0)

    async def fetch_sentiment(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch fear & greed index + approximate symbol sentiment."""
        sentiment: Dict[str, float] = {}

        try:
            resp = await self._client.get(FEAR_GREED_URL)
            if resp.status_code == 200:
                data = resp.json()
                fg_value = int(data["data"][0]["value"])  # 0–100
                # Normalize to -1 to 1
                normalized = (fg_value - 50) / 50
                for s in symbols:
                    sentiment[s] = normalized
        except Exception as e:
            logger.warning(f"[MarketData] fear/greed fetch failed: {e}")
            for s in symbols:
                sentiment[s] = 0.0

        return sentiment

    async def fetch_on_chain_metrics(self, assets: List[str]) -> Dict[str, Any]:
        """Fetch on-chain data — falls back to empty dict if unavailable."""
        metrics: Dict[str, Any] = {}

        if not settings.glassnode_api_key:
            return {a: {"active_addresses": 0, "nvt": 0, "sopr": 0} for a in assets}

        for asset in assets:
            try:
                url = f"https://api.glassnode.com/v1/metrics/addresses/active_count"
                resp = await self._client.get(
                    url,
                    params={"a": asset, "api_key": settings.glassnode_api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    metrics[asset] = {
                        "active_addresses": data[-1]["v"] if data else 0,
                    }
            except Exception as e:
                logger.warning(f"[MarketData] glassnode error {asset}: {e}")
                metrics[asset] = {}

        return metrics

    async def fetch_coinglass_data(self) -> Dict[str, Any]:
        """Fetch liquidation heatmap and long/short ratios from CoinGlass."""
        if not settings.coinglass_api_key:
            return {}

        try:
            resp = await self._client.get(
                "https://open-api.coinglass.com/public/v2/indicator/funding_avg",
                headers={"coinglassSecret": settings.coinglass_api_key},
            )
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except Exception as e:
            logger.warning(f"[MarketData] coinglass error: {e}")

        return {}

    async def close(self) -> None:
        await self._client.aclose()
