"use client";

import type { CycleStatus } from "@/lib/api";

const AGENTS = [
  "market_intelligence",
  "strategy",
  "risk_management",
  "execution",
  "portfolio_manager",
  "learning",
];

const AGENT_LABELS: Record<string, string> = {
  market_intelligence: "Market Intel",
  strategy: "Strategy",
  risk_management: "Risk Mgmt",
  execution: "Execution",
  portfolio_manager: "Portfolio",
  learning: "Learning",
};

interface Props {
  cycle: CycleStatus | null;
  isRunning: boolean;
  onRunCycle: () => void;
}

function RegimeBadge({ regime }: { regime: string }) {
  const colors: Record<string, string> = {
    bull_trend: "text-success bg-success/20",
    bear_trend: "text-danger bg-danger/20",
    ranging: "text-warning bg-warning/20",
    high_volatility: "text-orange-400 bg-orange-400/20",
    low_volatility: "text-blue-400 bg-blue-400/20",
    accumulation: "text-purple-400 bg-purple-400/20",
    distribution: "text-pink-400 bg-pink-400/20",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        colors[regime] ?? "text-[#7c85a2] bg-[#2a2d3e]"
      }`}
    >
      {regime?.replace("_", " ").toUpperCase() ?? "UNKNOWN"}
    </span>
  );
}

export function AgentStatus({ cycle, isRunning, onRunCycle }: Props) {
  const activeAgents = cycle
    ? AGENTS.filter((a) =>
        cycle.messages.some((m) => m.toLowerCase().includes(`[${a}`))
      )
    : [];

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider">
          Agent Pipeline
        </h3>
        <button
          onClick={onRunCycle}
          disabled={isRunning}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            isRunning
              ? "bg-brand/20 text-brand cursor-not-allowed"
              : "bg-brand text-surface hover:bg-brand-dark"
          }`}
        >
          {isRunning ? "Running..." : "Run Cycle"}
        </button>
      </div>

      {/* Pipeline flow */}
      <div className="flex items-center gap-1 mb-4 flex-wrap">
        {AGENTS.map((agent, i) => {
          const active = activeAgents.includes(agent);
          return (
            <div key={agent} className="flex items-center gap-1">
              <div
                className={`px-2 py-1 rounded text-xs font-mono transition-all ${
                  active
                    ? "bg-brand/20 text-brand border border-brand/40"
                    : "bg-surface-border text-[#7c85a2]"
                }`}
              >
                {AGENT_LABELS[agent]}
              </div>
              {i < AGENTS.length - 1 && (
                <span className="text-[#2a2d3e] text-xs">→</span>
              )}
            </div>
          );
        })}
      </div>

      {cycle ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#7c85a2]">Market Regime</span>
            <RegimeBadge regime={cycle.regime} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#7c85a2]">Kill Switch</span>
            <span
              className={`text-xs font-mono ${
                cycle.kill_switch ? "text-danger" : "text-success"
              }`}
            >
              {cycle.kill_switch ? "TRIGGERED" : "OK"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#7c85a2]">Signals</span>
            <span className="text-xs font-mono">
              {cycle.raw_signals} raw → {cycle.filtered_signals} filtered
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#7c85a2]">Executed</span>
            <span className="text-xs font-mono text-brand">
              {cycle.executed_orders} orders
            </span>
          </div>

          {/* Strategy weights */}
          <div className="pt-2 border-t border-surface-border">
            <p className="text-xs text-[#7c85a2] mb-2">Strategy Weights</p>
            {Object.entries(cycle.strategy_weights).map(([name, weight]) => (
              <div key={name} className="flex items-center gap-2 mb-1.5">
                <span className="text-xs text-[#7c85a2] w-32 truncate">
                  {name.replace("_", " ")}
                </span>
                <div className="flex-1 bg-surface-border rounded-full h-1.5">
                  <div
                    className="h-1.5 rounded-full bg-brand"
                    style={{ width: `${(weight * 100).toFixed(0)}%` }}
                  />
                </div>
                <span className="text-xs font-mono text-brand w-10 text-right">
                  {(weight * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>

          {/* Log messages */}
          {cycle.messages.length > 0 && (
            <div className="pt-2 border-t border-surface-border">
              <p className="text-xs text-[#7c85a2] mb-2">Cycle Log</p>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {cycle.messages.map((msg, i) => (
                  <p key={i} className="text-xs font-mono text-[#7c85a2] truncate">
                    {msg}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-[#7c85a2] text-center py-4">
          No cycle data. Click Run Cycle to start.
        </p>
      )}
    </div>
  );
}
