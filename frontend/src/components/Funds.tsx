"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type CoinBalance, type DepositAddressResult, type FundTransaction } from "@/lib/api";

// ── Common networks per currency ──────────────────────────────────────────────

const COIN_NETWORKS: Record<string, string[]> = {
  BTC:   ["BTC"],
  ETH:   ["ERC20"],
  USDT:  ["TRC20", "ERC20", "BEP20", "SOL"],
  USDC:  ["ERC20", "BEP20", "SOL", "AVAX"],
  BNB:   ["BEP20"],
  SOL:   ["SOL"],
  AVAX:  ["AVAX"],
  MATIC: ["MATIC"],
  XRP:   ["XRP"],
  TRX:   ["TRC20"],
};

const DEFAULT_NETWORKS = ["ERC20", "TRC20", "BEP20", "SOL", "NATIVE"];

function networksFor(currency: string): string[] {
  return COIN_NETWORKS[currency.toUpperCase()] ?? DEFAULT_NETWORKS;
}

const TOP_COINS = ["USDT", "BTC", "ETH", "BNB", "SOL", "USDC", "AVAX", "MATIC"];

// ── Sub-types ─────────────────────────────────────────────────────────────────

type FundsTab = "balances" | "deposit" | "withdraw" | "history";
type HistoryType = "deposits" | "withdrawals";

// ── Helpers ───────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={handleCopy}
      className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
        copied
          ? "bg-[#4ade80]/20 text-[#4ade80]"
          : "bg-[#1a1f35] text-[#7c85a2] hover:text-[#e8eaf6]"
      }`}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "ok" || s === "completed" || s === "success"
      ? "bg-[#4ade80]/15 text-[#4ade80]"
      : s === "pending" || s === "processing"
      ? "bg-[#facc15]/15 text-[#facc15]"
      : s === "failed" || s === "rejected" || s === "canceled"
      ? "bg-[#f87171]/15 text-[#f87171]"
      : "bg-[#2a2d3e] text-[#7c85a2]";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium ${cls}`}>
      {status || "unknown"}
    </span>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export function Funds() {
  const [tab, setTab] = useState<FundsTab>("balances");

  // ── Balances ────────────────────────────────────────────────────────────
  const [balances, setBalances] = useState<CoinBalance[]>([]);
  const [balLoading, setBalLoading] = useState(false);
  const [balError, setBalError] = useState("");

  const loadBalances = useCallback(async () => {
    setBalLoading(true);
    setBalError("");
    try {
      const res = await api.funds.balances();
      setBalances(res.balances);
    } catch (e: any) {
      setBalError(e.message ?? "Failed to load balances");
    } finally {
      setBalLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "balances") loadBalances();
  }, [tab, loadBalances]);

  // ── Deposit ─────────────────────────────────────────────────────────────
  const [depCoin, setDepCoin] = useState("USDT");
  const [depNetwork, setDepNetwork] = useState("TRC20");
  const [depResult, setDepResult] = useState<DepositAddressResult | null>(null);
  const [depLoading, setDepLoading] = useState(false);
  const [depError, setDepError] = useState("");

  const handleGetAddress = async () => {
    setDepLoading(true);
    setDepError("");
    setDepResult(null);
    try {
      const res = await api.funds.depositAddress(depCoin, depNetwork);
      setDepResult(res);
    } catch (e: any) {
      setDepError(e.message ?? "Failed to fetch address");
    } finally {
      setDepLoading(false);
    }
  };

  // reset address when coin/network changes
  useEffect(() => {
    setDepResult(null);
    setDepError("");
    const nets = networksFor(depCoin);
    setDepNetwork(nets[0] ?? "ERC20");
  }, [depCoin]);

  // ── Withdraw ─────────────────────────────────────────────────────────────
  const [wdForm, setWdForm] = useState({
    currency: "USDT",
    network: "TRC20",
    amount: "",
    address: "",
    tag: "",
  });
  const [wdConfirm, setWdConfirm] = useState(false);
  const [wdLoading, setWdLoading] = useState(false);
  const [wdResult, setWdResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [wdError, setWdError] = useState("");

  const maxFree = balances.find((b) => b.currency === wdForm.currency)?.free ?? 0;

  const handleWithdraw = async () => {
    setWdLoading(true);
    setWdError("");
    setWdResult(null);
    try {
      const res = await api.funds.withdraw({
        currency: wdForm.currency,
        amount: parseFloat(wdForm.amount),
        address: wdForm.address,
        tag: wdForm.tag || undefined,
        network: wdForm.network || undefined,
      });
      setWdResult({ ok: true, msg: `Submitted — ID: ${res.id || "pending"}` });
      setWdConfirm(false);
      setWdForm((f) => ({ ...f, amount: "", address: "", tag: "" }));
    } catch (e: any) {
      setWdError(e.message ?? "Withdrawal failed");
    } finally {
      setWdLoading(false);
    }
  };

  // ── History ──────────────────────────────────────────────────────────────
  const [histType, setHistType] = useState<HistoryType>("deposits");
  const [histItems, setHistItems] = useState<FundTransaction[]>([]);
  const [histLoading, setHistLoading] = useState(false);
  const [histError, setHistError] = useState("");

  const loadHistory = useCallback(async (type: HistoryType) => {
    setHistLoading(true);
    setHistError("");
    try {
      if (type === "deposits") {
        const res = await api.funds.deposits(undefined, 30);
        setHistItems(res.deposits);
      } else {
        const res = await api.funds.withdrawals(undefined, 30);
        setHistItems(res.withdrawals);
      }
    } catch (e: any) {
      setHistError(e.message ?? "Failed to load history");
      setHistItems([]);
    } finally {
      setHistLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "history") loadHistory(histType);
  }, [tab, histType, loadHistory]);

  // ── Tab nav ──────────────────────────────────────────────────────────────

  const TABS: { id: FundsTab; label: string }[] = [
    { id: "balances",  label: "Balances" },
    { id: "deposit",   label: "Deposit" },
    { id: "withdraw",  label: "Withdraw" },
    { id: "history",   label: "History" },
  ];

  return (
    <div className="card h-full flex flex-col gap-4">
      {/* Header + tabs */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[#7c85a2] uppercase tracking-wider">
          Funds
        </h2>
        <nav className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tab === t.id
                  ? "bg-[#1a1f35] text-[#e8eaf6]"
                  : "text-[#7c85a2] hover:text-[#e8eaf6]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Balances tab ──────────────────────────────────────────────────── */}
      {tab === "balances" && (
        <div className="flex-1 min-h-0 flex flex-col gap-3">
          <div className="flex justify-end">
            <button
              onClick={loadBalances}
              disabled={balLoading}
              className="text-xs text-[#7c85a2] hover:text-[#e8eaf6] px-2 py-1"
            >
              {balLoading ? "Loading…" : "↺ Refresh"}
            </button>
          </div>

          {balError && (
            <p className="text-xs text-[#f87171] px-1">{balError}</p>
          )}

          {balances.length === 0 && !balLoading && !balError && (
            <p className="text-xs text-[#5a6380] text-center py-8">
              No balances found. Connect exchange credentials.
            </p>
          )}

          <div className="overflow-y-auto flex-1">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#5a6380] uppercase tracking-wider">
                  <th className="text-left py-2 px-3">Currency</th>
                  <th className="text-right py-2 px-3">Free</th>
                  <th className="text-right py-2 px-3">Locked</th>
                  <th className="text-right py-2 px-3">Total</th>
                </tr>
              </thead>
              <tbody>
                {balances.map((b) => (
                  <tr
                    key={b.currency}
                    className="border-t border-[#1a1f35] hover:bg-[#0f1220] transition-colors"
                  >
                    <td className="py-2 px-3 font-semibold text-[#c9a84c]">
                      {b.currency}
                    </td>
                    <td className="py-2 px-3 text-right text-[#4ade80]">
                      {b.free.toLocaleString("en-US", { maximumFractionDigits: 8 })}
                    </td>
                    <td className="py-2 px-3 text-right text-[#7c85a2]">
                      {b.locked.toLocaleString("en-US", { maximumFractionDigits: 8 })}
                    </td>
                    <td className="py-2 px-3 text-right text-[#e8eaf6]">
                      {b.total.toLocaleString("en-US", { maximumFractionDigits: 8 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Deposit tab ───────────────────────────────────────────────────── */}
      {tab === "deposit" && (
        <div className="flex-1 flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] text-[#5a6380] uppercase mb-1">
                Currency
              </label>
              <select
                value={depCoin}
                onChange={(e) => setDepCoin(e.target.value)}
                className="w-full bg-[#0f1220] border border-[#2a2d3e] rounded px-3 py-2 text-xs text-[#e8eaf6] focus:outline-none focus:border-[#c9a84c]"
              >
                {TOP_COINS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-[#5a6380] uppercase mb-1">
                Network
              </label>
              <select
                value={depNetwork}
                onChange={(e) => setDepNetwork(e.target.value)}
                className="w-full bg-[#0f1220] border border-[#2a2d3e] rounded px-3 py-2 text-xs text-[#e8eaf6] focus:outline-none focus:border-[#c9a84c]"
              >
                {networksFor(depCoin).map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>

          <button
            onClick={handleGetAddress}
            disabled={depLoading}
            className="w-full py-2 rounded bg-[#c9a84c]/20 text-[#c9a84c] border border-[#c9a84c]/30 text-xs font-medium hover:bg-[#c9a84c]/30 transition-colors disabled:opacity-50"
          >
            {depLoading ? "Fetching…" : "Get Deposit Address"}
          </button>

          {depError && (
            <p className="text-xs text-[#f87171] px-1">{depError}</p>
          )}

          {depResult && (
            <div className="flex flex-col gap-3">
              <div className="bg-[#0b0d1a] border border-[#2a2d3e] rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-[#5a6380] uppercase tracking-wider">
                    {depResult.currency} — {depResult.network || depNetwork}
                  </span>
                  <CopyButton text={depResult.address} />
                </div>
                <p className="font-mono text-[11px] text-[#c9a84c] break-all leading-relaxed">
                  {depResult.address}
                </p>
                {depResult.tag && (
                  <div className="mt-3 pt-3 border-t border-[#1a1f35]">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-[#5a6380] uppercase">
                        Memo / Tag
                      </span>
                      <CopyButton text={depResult.tag} />
                    </div>
                    <p className="font-mono text-[11px] text-[#facc15] mt-1">
                      {depResult.tag}
                    </p>
                  </div>
                )}
              </div>

              <div className="flex items-start gap-2 bg-[#facc15]/5 border border-[#facc15]/20 rounded px-3 py-2">
                <span className="text-[#facc15] mt-0.5 shrink-0">⚠</span>
                <p className="text-[10px] text-[#facc15]/80 leading-relaxed">
                  Only send <strong>{depResult.currency}</strong> on the{" "}
                  <strong>{depResult.network || depNetwork}</strong> network to this
                  address. Sending any other asset may result in permanent loss.
                  {depResult.tag && " Memo/Tag is required for this currency."}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Withdraw tab ──────────────────────────────────────────────────── */}
      {tab === "withdraw" && (
        <div className="flex-1 flex flex-col gap-4">
          {wdResult?.ok && (
            <div className="bg-[#4ade80]/10 border border-[#4ade80]/30 rounded px-3 py-2 text-xs text-[#4ade80]">
              ✓ {wdResult.msg}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] text-[#5a6380] uppercase mb-1">Currency</label>
              <select
                value={wdForm.currency}
                onChange={(e) =>
                  setWdForm((f) => ({
                    ...f,
                    currency: e.target.value,
                    network: networksFor(e.target.value)[0] ?? "",
                  }))
                }
                className="w-full bg-[#0f1220] border border-[#2a2d3e] rounded px-3 py-2 text-xs text-[#e8eaf6] focus:outline-none focus:border-[#c9a84c]"
              >
                {TOP_COINS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-[#5a6380] uppercase mb-1">Network</label>
              <select
                value={wdForm.network}
                onChange={(e) => setWdForm((f) => ({ ...f, network: e.target.value }))}
                className="w-full bg-[#0f1220] border border-[#2a2d3e] rounded px-3 py-2 text-xs text-[#e8eaf6] focus:outline-none focus:border-[#c9a84c]"
              >
                {networksFor(wdForm.currency).map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-[#5a6380] uppercase">Amount</label>
              {maxFree > 0 && (
                <button
                  onClick={() => setWdForm((f) => ({ ...f, amount: String(maxFree) }))}
                  className="text-[10px] text-[#c9a84c] hover:text-[#e8c86a]"
                >
                  Max: {maxFree.toLocaleString("en-US", { maximumFractionDigits: 8 })}
                </button>
              )}
            </div>
            <input
              type="number"
              min="0"
              step="any"
              value={wdForm.amount}
              onChange={(e) => setWdForm((f) => ({ ...f, amount: e.target.value }))}
              placeholder="0.00"
              className="w-full bg-[#0f1220] border border-[#2a2d3e] rounded px-3 py-2 text-xs text-[#e8eaf6] placeholder-[#3d4461] focus:outline-none focus:border-[#c9a84c]"
            />
          </div>

          <div>
            <label className="block text-[10px] text-[#5a6380] uppercase mb-1">
              Destination Address
            </label>
            <input
              type="text"
              value={wdForm.address}
              onChange={(e) => setWdForm((f) => ({ ...f, address: e.target.value }))}
              placeholder="0x… or 1… or T…"
              className="w-full bg-[#0f1220] border border-[#2a2d3e] rounded px-3 py-2 text-xs font-mono text-[#e8eaf6] placeholder-[#3d4461] focus:outline-none focus:border-[#c9a84c]"
            />
          </div>

          <div>
            <label className="block text-[10px] text-[#5a6380] uppercase mb-1">
              Memo / Tag{" "}
              <span className="text-[#3d4461] normal-case">(optional)</span>
            </label>
            <input
              type="text"
              value={wdForm.tag}
              onChange={(e) => setWdForm((f) => ({ ...f, tag: e.target.value }))}
              placeholder="Required for XRP, XLM, EOS…"
              className="w-full bg-[#0f1220] border border-[#2a2d3e] rounded px-3 py-2 text-xs text-[#e8eaf6] placeholder-[#3d4461] focus:outline-none focus:border-[#c9a84c]"
            />
          </div>

          {wdError && (
            <p className="text-xs text-[#f87171]">{wdError}</p>
          )}

          {!wdConfirm ? (
            <button
              onClick={() => {
                setWdError("");
                setWdResult(null);
                if (!wdForm.amount || parseFloat(wdForm.amount) <= 0) {
                  setWdError("Enter a valid amount");
                  return;
                }
                if (!wdForm.address.trim()) {
                  setWdError("Enter a destination address");
                  return;
                }
                setWdConfirm(true);
              }}
              className="w-full py-2 rounded bg-[#f87171]/10 text-[#f87171] border border-[#f87171]/30 text-xs font-medium hover:bg-[#f87171]/20 transition-colors"
            >
              Preview Withdrawal →
            </button>
          ) : (
            <div className="bg-[#0b0d1a] border border-[#f87171]/40 rounded-lg p-4 flex flex-col gap-3">
              <p className="text-xs font-semibold text-[#f87171] uppercase tracking-wider">
                Confirm Withdrawal
              </p>
              <div className="grid grid-cols-2 gap-1 text-xs">
                <span className="text-[#5a6380]">Amount</span>
                <span className="text-[#e8eaf6] font-mono">
                  {parseFloat(wdForm.amount).toLocaleString("en-US", { maximumFractionDigits: 8 })}{" "}
                  {wdForm.currency}
                </span>
                <span className="text-[#5a6380]">Network</span>
                <span className="text-[#e8eaf6]">{wdForm.network}</span>
                <span className="text-[#5a6380]">Address</span>
                <span className="text-[#e8eaf6] font-mono break-all">
                  {wdForm.address.slice(0, 20)}…{wdForm.address.slice(-8)}
                </span>
                {wdForm.tag && (
                  <>
                    <span className="text-[#5a6380]">Tag/Memo</span>
                    <span className="text-[#facc15] font-mono">{wdForm.tag}</span>
                  </>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setWdConfirm(false)}
                  className="flex-1 py-2 rounded text-xs text-[#7c85a2] border border-[#2a2d3e] hover:text-[#e8eaf6] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleWithdraw}
                  disabled={wdLoading}
                  className="flex-1 py-2 rounded text-xs font-semibold text-white bg-[#f87171]/80 hover:bg-[#f87171] transition-colors disabled:opacity-50"
                >
                  {wdLoading ? "Submitting…" : "Confirm Withdraw"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── History tab ───────────────────────────────────────────────────── */}
      {tab === "history" && (
        <div className="flex-1 min-h-0 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setHistType("deposits")}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                histType === "deposits"
                  ? "bg-[#4ade80]/20 text-[#4ade80]"
                  : "text-[#7c85a2] hover:text-[#e8eaf6]"
              }`}
            >
              ↓ Deposits
            </button>
            <button
              onClick={() => setHistType("withdrawals")}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                histType === "withdrawals"
                  ? "bg-[#f87171]/20 text-[#f87171]"
                  : "text-[#7c85a2] hover:text-[#e8eaf6]"
              }`}
            >
              ↑ Withdrawals
            </button>
            <button
              onClick={() => loadHistory(histType)}
              className="ml-auto text-xs text-[#7c85a2] hover:text-[#e8eaf6] px-2 py-1"
            >
              ↺ Refresh
            </button>
          </div>

          {histLoading && (
            <p className="text-xs text-[#5a6380] text-center py-4">Loading…</p>
          )}
          {histError && (
            <p className="text-xs text-[#f87171] px-1">{histError}</p>
          )}
          {!histLoading && histItems.length === 0 && !histError && (
            <p className="text-xs text-[#5a6380] text-center py-8">
              No {histType} found.
            </p>
          )}

          <div className="overflow-y-auto flex-1">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#5a6380] uppercase tracking-wider">
                  <th className="text-left py-2 px-3">Time</th>
                  <th className="text-left py-2 px-3">Coin</th>
                  <th className="text-right py-2 px-3">Amount</th>
                  <th className="text-left py-2 px-3">Status</th>
                  <th className="text-left py-2 px-3">Address</th>
                  <th className="text-left py-2 px-3">TxID</th>
                </tr>
              </thead>
              <tbody>
                {histItems.map((tx, i) => (
                  <tr
                    key={tx.id || i}
                    className="border-t border-[#1a1f35] hover:bg-[#0f1220] transition-colors"
                  >
                    <td className="py-2 px-3 text-[#5a6380] whitespace-nowrap">
                      {tx.timestamp ? tx.timestamp.slice(0, 16).replace("T", " ") : "—"}
                    </td>
                    <td className="py-2 px-3 font-semibold text-[#c9a84c]">
                      {tx.currency}
                    </td>
                    <td
                      className={`py-2 px-3 text-right font-mono ${
                        histType === "deposits" ? "text-[#4ade80]" : "text-[#f87171]"
                      }`}
                    >
                      {histType === "deposits" ? "+" : "−"}
                      {tx.amount.toLocaleString("en-US", { maximumFractionDigits: 8 })}
                    </td>
                    <td className="py-2 px-3">
                      <StatusBadge status={tx.status} />
                    </td>
                    <td className="py-2 px-3 font-mono text-[#7c85a2]">
                      {tx.address
                        ? `${tx.address.slice(0, 8)}…${tx.address.slice(-4)}`
                        : "—"}
                    </td>
                    <td className="py-2 px-3 font-mono text-[#5a6380]">
                      {tx.txid
                        ? `${tx.txid.slice(0, 10)}…`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
