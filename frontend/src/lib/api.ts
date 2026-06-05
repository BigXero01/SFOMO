const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface PortfolioSnapshot {
  total_equity: number;
  cash: number;
  positions_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  current_drawdown: number;
  peak_equity: number;
}

export interface Trade {
  id: number;
  symbol: string;
  side: string;
  size: number;
  price: number;
  pnl: number;
  strategy: string;
  fees: number;
  slippage_pct: number;
  created_at: string;
}

export interface Signal {
  symbol: string;
  strategy: string;
  direction: string;
  strength: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  confidence: number;
  reasoning: string;
}

export interface CycleStatus {
  cycle_id: string;
  regime: string;
  raw_signals: number;
  filtered_signals: number;
  executed_orders: number;
  kill_switch: boolean;
  errors: string[];
  messages: string[];
  strategy_weights: Record<string, number>;
  signals: Signal[];
}

export interface Performance {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_win: number;
  avg_loss: number;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export const api = {
  portfolio: {
    snapshot: () => get<PortfolioSnapshot>("/api/v1/portfolio/snapshot"),
    history: (limit = 100) =>
      get<{ history: any[] }>(`/api/v1/portfolio/history?limit=${limit}`),
    performance: () => get<Performance>("/api/v1/portfolio/performance"),
  },
  trades: {
    recent: (limit = 50) =>
      get<{ trades: Trade[]; count: number }>(`/api/v1/trades/recent?limit=${limit}`),
    byStrategy: () => get<Record<string, Trade[]>>("/api/v1/trades/by-strategy"),
  },
  signals: {
    lastCycle: () => get<CycleStatus>("/api/v1/signals/last-cycle"),
    runCycle: (symbols?: string[], timeframe?: string) =>
      fetch(`${BASE}/api/v1/signals/run-cycle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols, timeframe }),
      }).then((r) => r.json()),
  },
  health: () => get<{ status: string; env: string; exchange: string }>("/health"),
};
