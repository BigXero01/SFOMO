"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type CycleStatus, type Performance, type PortfolioSnapshot, type Trade } from "@/lib/api";
import { PortfolioChart } from "@/components/PortfolioChart";
import { RiskMetrics } from "@/components/RiskMetrics";
import { AgentStatus } from "@/components/AgentStatus";
import { TradeHistory } from "@/components/TradeHistory";
import { SignalList } from "@/components/SignalList";

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="card">
      <p className="stat-label">{label}</p>
      <p className={`stat-value mt-1 ${color ?? "text-[#e8eaf6]"}`}>{value}</p>
      {sub && <p className="text-xs text-[#7c85a2] mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [cycle, setCycle] = useState<CycleStatus | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [health, setHealth] = useState<{ status: string; env: string; exchange: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [snap, hist, perf, tr, cyc, h] = await Promise.allSettled([
        api.portfolio.snapshot(),
        api.portfolio.history(200),
        api.portfolio.performance(),
        api.trades.recent(50),
        api.signals.lastCycle(),
        api.health(),
      ]);

      if (snap.status === "fulfilled") setPortfolio(snap.value);
      if (hist.status === "fulfilled") setHistory(hist.value.history ?? []);
      if (perf.status === "fulfilled") setPerformance(perf.value);
      if (tr.status === "fulfilled") setTrades(tr.value.trades ?? []);
      if (cyc.status === "fulfilled" && "cycle_id" in cyc.value) setCycle(cyc.value as CycleStatus);
      if (h.status === "fulfilled") setHealth(h.value);
      setLastUpdate(new Date());
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [refresh]);

  const handleRunCycle = async () => {
    setIsRunning(true);
    try {
      await api.signals.runCycle();
      await new Promise((r) => setTimeout(r, 3000));
      await refresh();
    } finally {
      setIsRunning(false);
    }
  };

  const equity = portfolio?.total_equity ?? 0;
  const drawdown = portfolio?.current_drawdown ?? 0;
  const pnl = portfolio?.realized_pnl ?? 0;
  const unrealized = portfolio?.unrealized_pnl ?? 0;

  return (
    <div className="min-h-screen bg-surface text-[#e8eaf6]">
      {/* Header */}
      <header className="border-b border-surface-border px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center">
            <span className="text-surface text-xs font-black">SF</span>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight">SFOMO</h1>
            <p className="text-xs text-[#7c85a2]">AI Agent Trading Bot</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-[#7c85a2]">
          {health && (
            <>
              <span className={`flex items-center gap-1 ${health.status === "ok" ? "text-success" : "text-danger"}`}>
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                {health.status.toUpperCase()}
              </span>
              <span>{health.exchange} • {health.env}</span>
            </>
          )}
          {lastUpdate && (
            <span>Updated {lastUpdate.toLocaleTimeString()}</span>
          )}
        </div>
      </header>

      <main className="px-6 py-6 max-w-screen-2xl mx-auto space-y-6">
        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Total Equity"
            value={`$${equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
            sub={`Peak $${(portfolio?.peak_equity ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          />
          <StatCard
            label="Realized PnL"
            value={`${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}`}
            color={pnl >= 0 ? "text-success" : "text-danger"}
          />
          <StatCard
            label="Unrealized PnL"
            value={`${unrealized >= 0 ? "+" : ""}$${unrealized.toFixed(2)}`}
            color={unrealized >= 0 ? "text-success" : "text-danger"}
          />
          <StatCard
            label="Max Drawdown"
            value={`${(drawdown * 100).toFixed(2)}%`}
            sub="Kill switch: 15%"
            color={drawdown > 0.1 ? "text-danger" : drawdown > 0.05 ? "text-warning" : "text-success"}
          />
        </div>

        {/* Equity chart */}
        <div className="card">
          <h3 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider mb-4">
            Equity Curve
          </h3>
          <PortfolioChart data={history} />
        </div>

        {/* Middle row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <RiskMetrics performance={performance} drawdown={drawdown} />
          <div className="lg:col-span-2">
            <AgentStatus
              cycle={cycle}
              isRunning={isRunning}
              onRunCycle={handleRunCycle}
            />
          </div>
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <SignalList signals={cycle?.signals ?? []} />
          <TradeHistory trades={trades} />
        </div>
      </main>
    </div>
  );
}
