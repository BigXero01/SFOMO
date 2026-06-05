"""Drawdown controller — computes VaR, Sharpe, and portfolio risk metrics."""
from __future__ import annotations

import math
from typing import Any, Dict, List

from core.state import RiskMetrics


class DrawdownController:
    def compute_metrics(
        self,
        trade_history: List[Dict[str, Any]],
        equity: float,
        peak_equity: float,
    ) -> RiskMetrics:
        metrics = RiskMetrics()

        if not trade_history:
            return metrics

        pnls = [t.get("pnl", 0.0) for t in trade_history if t.get("pnl") is not None]
        if not pnls:
            return metrics

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        metrics.win_rate = len(wins) / len(pnls) if pnls else 0.0
        metrics.avg_win = sum(wins) / len(wins) if wins else 0.0
        metrics.avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        metrics.profit_factor = (
            sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")
        )
        metrics.max_drawdown = (
            (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        )
        metrics.current_drawdown = metrics.max_drawdown

        # Annualized Sharpe (assuming hourly returns)
        if len(pnls) > 1:
            mean_pnl = sum(pnls) / len(pnls)
            std_pnl = math.sqrt(sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls))
            if std_pnl > 0 and equity > 0:
                hourly_returns = [p / equity for p in pnls]
                mean_r = sum(hourly_returns) / len(hourly_returns)
                std_r = math.sqrt(sum((r - mean_r) ** 2 for r in hourly_returns) / len(hourly_returns))
                metrics.sharpe_ratio = (mean_r / std_r) * math.sqrt(365 * 24) if std_r > 0 else 0.0

                # 1-day VaR at 95% confidence (parametric)
                metrics.portfolio_var_1d = abs(mean_r - 1.645 * std_r) * math.sqrt(24)
                metrics.portfolio_var_5d = abs(mean_r - 1.645 * std_r) * math.sqrt(24 * 5)

                # Sortino (downside deviation only)
                neg_returns = [r for r in hourly_returns if r < 0]
                if neg_returns:
                    downside_std = math.sqrt(sum(r ** 2 for r in neg_returns) / len(neg_returns))
                    metrics.sortino_ratio = (mean_r / downside_std) * math.sqrt(365 * 24) if downside_std > 0 else 0.0

        return metrics
