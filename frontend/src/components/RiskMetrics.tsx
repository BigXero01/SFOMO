"use client";

import type { Performance } from "@/lib/api";

interface Props {
  performance: Performance | null;
  drawdown: number;
}

function Gauge({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="w-full bg-surface-border rounded-full h-1.5 mt-1">
      <div
        className="h-1.5 rounded-full transition-all"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  );
}

export function RiskMetrics({ performance, drawdown }: Props) {
  const p = performance;

  const metrics = [
    {
      label: "Win Rate",
      value: p ? `${(p.win_rate * 100).toFixed(1)}%` : "–",
      raw: p?.win_rate ?? 0,
      max: 1,
      color: "#00e676",
    },
    {
      label: "Profit Factor",
      value:
        p && p.avg_loss > 0
          ? (p.avg_win / p.avg_loss).toFixed(2)
          : "–",
      raw: p && p.avg_loss > 0 ? p.avg_win / p.avg_loss : 0,
      max: 3,
      color: "#00d4ff",
    },
    {
      label: "Drawdown",
      value: `${(drawdown * 100).toFixed(2)}%`,
      raw: drawdown,
      max: 0.15,
      color: drawdown > 0.1 ? "#ff4444" : "#ffab00",
    },
  ];

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider mb-4">
        Risk Metrics
      </h3>
      <div className="space-y-4">
        {metrics.map((m) => (
          <div key={m.label}>
            <div className="flex justify-between items-center">
              <span className="text-xs text-[#7c85a2]">{m.label}</span>
              <span className="text-sm font-mono font-bold" style={{ color: m.color }}>
                {m.value}
              </span>
            </div>
            <Gauge value={m.raw} max={m.max} color={m.color} />
          </div>
        ))}

        {p && (
          <div className="pt-2 border-t border-surface-border space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-[#7c85a2]">Total Trades</span>
              <span className="font-mono">{p.total_trades}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-[#7c85a2]">Avg Win</span>
              <span className="font-mono text-success">
                ${p.avg_win.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-[#7c85a2]">Avg Loss</span>
              <span className="font-mono text-danger">
                -${Math.abs(p.avg_loss).toFixed(2)}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
