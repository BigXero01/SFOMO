const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

// ── Types ──────────────────────────────────────────────────────────────────────

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

export interface CoinBalance {
  currency: string;
  free: number;
  locked: number;
  total: number;
}

export interface DepositAddressResult {
  currency: string;
  address: string;
  tag?: string;
  network?: string;
}

export interface FundTransaction {
  id: string;
  type: "deposit" | "withdrawal";
  currency: string;
  amount: number;
  address: string;
  tag?: string;
  txid: string;
  network?: string;
  status: string;
  fee: number;
  timestamp: string | null;
}

// ── HTTP helpers ───────────────────────────────────────────────────────────────

function _headers(): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" };
  if (API_KEY) (h as Record<string, string>)["X-API-Key"] = API_KEY;
  return h;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: _headers(),
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: _headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `${res.status} ${path}`);
  }
  return res.json();
}

// ── API client ─────────────────────────────────────────────────────────────────

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
      post<{ status: string }>("/api/v1/signals/run-cycle", { symbols, timeframe }),
  },

  funds: {
    balances: () =>
      get<{ balances: CoinBalance[]; exchange: string }>("/api/v1/funds/balances"),

    depositAddress: (currency: string, network?: string) => {
      const q = network ? `&network=${encodeURIComponent(network)}` : "";
      return get<DepositAddressResult>(
        `/api/v1/funds/deposit-address?currency=${encodeURIComponent(currency)}${q}`
      );
    },

    deposits: (currency?: string, limit = 20) => {
      const q = currency ? `&currency=${encodeURIComponent(currency)}` : "";
      return get<{ deposits: FundTransaction[]; count: number }>(
        `/api/v1/funds/deposits?limit=${limit}${q}`
      );
    },

    withdraw: (body: {
      currency: string;
      amount: number;
      address: string;
      tag?: string;
      network?: string;
    }) => post<{ status: string; id?: string; currency: string; amount: number }>("/api/v1/funds/withdraw", body),

    withdrawals: (currency?: string, limit = 20) => {
      const q = currency ? `&currency=${encodeURIComponent(currency)}` : "";
      return get<{ withdrawals: FundTransaction[]; count: number }>(
        `/api/v1/funds/withdrawals?limit=${limit}${q}`
      );
    },
  },

  health: () =>
    get<{ status: string; env: string; exchange: string }>("/health"),
};
