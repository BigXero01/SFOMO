"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format } from "date-fns";

interface EquityPoint {
  snapshot_at: string;
  total_equity: number;
}

interface Props {
  data: EquityPoint[];
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-3 text-sm">
      <p className="text-[#7c85a2] mb-1">
        {format(new Date(label), "MMM d, HH:mm")}
      </p>
      <p className="text-brand font-mono font-bold">
        ${payload[0].value.toLocaleString("en-US", { minimumFractionDigits: 2 })}
      </p>
    </div>
  );
};

export function PortfolioChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-48 text-[#7c85a2] text-sm">
        No equity history yet
      </div>
    );
  }

  const chartData = data.map((d) => ({
    time: d.snapshot_at,
    equity: d.total_equity,
  }));

  const min = Math.min(...chartData.map((d) => d.equity)) * 0.995;
  const max = Math.max(...chartData.map((d) => d.equity)) * 1.005;
  const isUp = chartData[chartData.length - 1].equity >= chartData[0].equity;

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={chartData} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop
              offset="5%"
              stopColor={isUp ? "#00d4ff" : "#ff4444"}
              stopOpacity={0.3}
            />
            <stop
              offset="95%"
              stopColor={isUp ? "#00d4ff" : "#ff4444"}
              stopOpacity={0}
            />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3e" />
        <XAxis
          dataKey="time"
          tickFormatter={(v) => format(new Date(v), "MMM d")}
          stroke="#7c85a2"
          tick={{ fontSize: 11 }}
          tickLine={false}
        />
        <YAxis
          domain={[min, max]}
          tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
          stroke="#7c85a2"
          tick={{ fontSize: 11 }}
          tickLine={false}
          width={55}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="equity"
          stroke={isUp ? "#00d4ff" : "#ff4444"}
          strokeWidth={2}
          fill="url(#equityGradient)"
          dot={false}
          activeDot={{ r: 4, strokeWidth: 0 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
