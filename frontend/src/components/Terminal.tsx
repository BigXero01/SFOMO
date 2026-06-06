"use client";

import {
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

type Style =
  | "normal"
  | "success"
  | "error"
  | "warn"
  | "info"
  | "gold"
  | "muted"
  | "dim"
  | "code"
  | "header";

interface OutputLine {
  id: number;
  text: string;
  style: Style;
}

// ── Style → Tailwind class map ────────────────────────────────────────────────

const STYLE_CLASS: Record<Style, string> = {
  normal:  "text-[#c8cfe8]",
  success: "text-[#4ade80]",
  error:   "text-[#f87171]",
  warn:    "text-[#facc15]",
  info:    "text-[#60a5fa]",
  gold:    "text-[#c9a84c] font-semibold",
  muted:   "text-[#5a6380]",
  dim:     "text-[#3d4461]",
  code:    "text-[#a78bfa] font-mono",
  header:  "text-[#e8eaf6] font-bold",
};

// ── WS message shapes ─────────────────────────────────────────────────────────

type WsMsg =
  | { t: "line"; text: string; style: Style }
  | { t: "prompt" }
  | { t: "clear" };

// ── Component ──────────────────────────────────────────────────────────────────

interface TerminalProps {
  apiKey: string;
  wsUrl?: string;
}

let _lineId = 0;

export function Terminal({ apiKey, wsUrl = "" }: TerminalProps) {
  const [lines, setLines] = useState<OutputLine[]>([]);
  const [input, setInput] = useState("");
  const [isPrompt, setIsPrompt] = useState(false);
  const [connected, setConnected] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);

  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const appendLine = useCallback((text: string, style: Style) => {
    setLines((prev) => [
      ...prev,
      { id: ++_lineId, text, style },
    ]);
  }, []);

  const clearLines = useCallback(() => setLines([]), []);

  // ── WebSocket connection ──────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (wsRef.current) return;

    const base =
      wsUrl ||
      (typeof window !== "undefined"
        ? window.location.origin.replace(/^http/, "ws")
        : "ws://localhost:8000");

    const url = `${base}/ws/terminal?api_key=${encodeURIComponent(apiKey)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (ev) => {
      try {
        const msg: WsMsg = JSON.parse(ev.data);
        if (msg.t === "clear") {
          clearLines();
        } else if (msg.t === "line") {
          appendLine(msg.text, msg.style || "normal");
        } else if (msg.t === "prompt") {
          setIsPrompt(true);
          inputRef.current?.focus();
        }
      } catch {
        appendLine(ev.data, "muted");
      }
    };

    ws.onclose = () => {
      setConnected(false);
      setIsPrompt(false);
      wsRef.current = null;
      appendLine("  [disconnected]", "error");
    };

    ws.onerror = () => {
      appendLine("  [connection error]", "error");
    };
  }, [apiKey, wsUrl, appendLine, clearLines]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  // ── Auto-scroll ───────────────────────────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  // ── Send command ──────────────────────────────────────────────────────────

  const sendCommand = useCallback(
    (cmd: string) => {
      const trimmed = cmd.trim();
      if (!trimmed || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

      // Echo the command in the terminal
      appendLine(`  sfomo> ${trimmed}`, "gold");
      setIsPrompt(false);

      // Push to history (dedup consecutive)
      setHistory((prev) => {
        if (prev[0] === trimmed) return prev;
        return [trimmed, ...prev].slice(0, 100);
      });
      setHistoryIdx(-1);

      wsRef.current.send(JSON.stringify({ cmd: trimmed }));
      setInput("");
    },
    [appendLine]
  );

  // ── Keyboard handling ─────────────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        sendCommand(input);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHistoryIdx((idx) => {
          const next = Math.min(idx + 1, history.length - 1);
          setInput(history[next] ?? "");
          return next;
        });
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setHistoryIdx((idx) => {
          const next = Math.max(idx - 1, -1);
          setInput(next === -1 ? "" : (history[next] ?? ""));
          return next;
        });
      } else if (e.key === "l" && e.ctrlKey) {
        e.preventDefault();
        clearLines();
      } else if (e.key === "c" && e.ctrlKey) {
        e.preventDefault();
        setInput("");
        appendLine("  ^C", "muted");
      }
    },
    [input, history, sendCommand, clearLines, appendLine]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className="
        flex flex-col h-full bg-[#07070e] rounded-xl
        border border-[#1a1f35] overflow-hidden font-mono text-xs
        select-text
      "
      onClick={() => inputRef.current?.focus()}
    >
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-[#0b0d1a] border-b border-[#1a1f35] shrink-0">
        <span className="w-3 h-3 rounded-full bg-[#f87171]" />
        <span className="w-3 h-3 rounded-full bg-[#facc15]" />
        <span className="w-3 h-3 rounded-full bg-[#4ade80]" />
        <span className="ml-2 text-[#3d4461] text-[11px] tracking-widest uppercase">
          SFOMO Terminal
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              connected ? "bg-[#4ade80]" : "bg-[#f87171]"
            }`}
          />
          <span className="text-[#3d4461] text-[10px]">
            {connected ? "connected" : "offline"}
          </span>
        </div>
      </div>

      {/* Output area */}
      <div className="flex-1 overflow-y-auto px-2 py-3 leading-5 space-y-0.5">
        {lines.map((line) => (
          <div
            key={line.id}
            className={`whitespace-pre ${STYLE_CLASS[line.style] ?? STYLE_CLASS.normal}`}
          >
            {line.text || " "}
          </div>
        ))}

        {/* Input row */}
        {isPrompt && connected && (
          <div className="flex items-center mt-1">
            <span className="text-[#c9a84c] mr-1">sfomo&gt;</span>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              className="
                flex-1 bg-transparent outline-none text-[#c8cfe8] caret-[#c9a84c]
                placeholder-[#3d4461]
              "
              placeholder="type a command…"
              autoComplete="off"
              spellCheck={false}
              autoFocus
            />
            {/* Blinking cursor */}
            <span className="ml-0.5 w-[7px] h-[14px] bg-[#c9a84c] opacity-80 animate-[blink_1.1s_step-end_infinite]" />
          </div>
        )}

        {!connected && (
          <div className="mt-2">
            <button
              onClick={(e) => { e.stopPropagation(); connect(); }}
              className="text-[#c9a84c] hover:text-[#e8c86a] text-xs underline"
            >
              reconnect
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
