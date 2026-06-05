"use client";

import { format } from "date-fns";
import type { Trade } from "@/lib/api";

interface Props {
  trades: Trade[];
}

export function TradeHistory({ trades }: Props) {
  if (!trades.length) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider mb-4">
          Trade History
        </h3>
        <p className="text-xs text-[#7c85a2] text-center py-8">No trades yet</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider mb-4">
        Trade History
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="text-left pb-2 text-[#7c85a2] font-medium">Symbol</th>
              <th className="text-left pb-2 text-[#7c85a2] font-medium">Side</th>
              <th className="text-right pb-2 text-[#7c85a2] font-medium">Price</th>
              <th className="text-right pb-2 text-[#7c85a2] font-medium">PnL</th>
              <th className="text-left pb-2 text-[#7c85a2] font-medium">Strategy</th>
              <th className="text-right pb-2 text-[#7c85a2] font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {trades.map((t) => (
              <tr key={t.id} className="hover:bg-surface-border/30 transition-colors">
                <td className="py-2 font-mono font-bold text-[#e8eaf6]">{t.symbol}</td>
                <td className="py-2">
                  <span
                    className={
                      t.side === "buy" ? "badge-long" : "badge-short"
                    }
                  >
                    {t.side.toUpperCase()}
                  </span>
                </td>
                <td className="py-2 text-right font-mono">
                  ${t.price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </td>
                <td
                  className={`py-2 text-right font-mono font-bold ${
                    t.pnl >= 0 ? "text-success" : "text-danger"
                  }`}
                >
                  {t.pnl >= 0 ? "+" : ""}
                  {t.pnl.toFixed(2)}
                </td>
                <td className="py-2 text-[#7c85a2]">
                  {t.strategy?.replace("_", " ") ?? "–"}
                </td>
                <td className="py-2 text-right text-[#7c85a2]">
                  {t.created_at
                    ? format(new Date(t.created_at), "MMM d HH:mm")
                    : "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
