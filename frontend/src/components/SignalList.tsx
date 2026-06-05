"use client";

import type { Signal } from "@/lib/api";

interface Props {
  signals: Signal[];
}

const strengthColor: Record<string, string> = {
  strong: "text-success",
  moderate: "text-warning",
  weak: "text-[#7c85a2]",
};

export function SignalList({ signals }: Props) {
  if (!signals.length) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider mb-4">
          Active Signals
        </h3>
        <p className="text-xs text-[#7c85a2] text-center py-8">
          No signals this cycle
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider mb-4">
        Active Signals ({signals.length})
      </h3>
      <div className="space-y-3">
        {signals.map((s, i) => {
          const rr =
            Math.abs(s.take_profit - s.entry_price) /
            Math.abs(s.entry_price - s.stop_loss);
          return (
            <div
              key={i}
              className="p-3 rounded-lg bg-surface border border-surface-border"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-sm">{s.symbol}</span>
                  <span
                    className={
                      s.direction === "long" ? "badge-long" : "badge-short"
                    }
                  >
                    {s.direction.toUpperCase()}
                  </span>
                  <span
                    className={`text-xs font-medium ${
                      strengthColor[s.strength] ?? "text-[#7c85a2]"
                    }`}
                  >
                    {s.strength}
                  </span>
                </div>
                <span className="text-xs text-brand font-mono">
                  {(s.confidence * 100).toFixed(0)}% conf
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div>
                  <p className="text-[#7c85a2]">Entry</p>
                  <p className="font-mono">${s.entry_price.toFixed(4)}</p>
                </div>
                <div>
                  <p className="text-[#7c85a2]">Stop</p>
                  <p className="font-mono text-danger">${s.stop_loss.toFixed(4)}</p>
                </div>
                <div>
                  <p className="text-[#7c85a2]">Target</p>
                  <p className="font-mono text-success">${s.take_profit.toFixed(4)}</p>
                </div>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <span className="text-xs text-[#7c85a2]">
                  {s.strategy?.replace(/_/g, " ")}
                </span>
                <span className="text-xs text-[#7c85a2]">
                  R:R {rr.toFixed(1)}x
                </span>
              </div>
              {s.reasoning && (
                <p className="text-xs text-[#7c85a2] mt-1 truncate" title={s.reasoning}>
                  {s.reasoning}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
