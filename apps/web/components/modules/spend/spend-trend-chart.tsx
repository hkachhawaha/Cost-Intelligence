"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { SpendTrendPoint } from "@/lib/types";

export function SpendTrendChart({ points }: { points: SpendTrendPoint[] }) {
  if (points.length === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">No trend data.</p>;
  }
  const data = points.map((p) => ({ month: p.month, amount: Number(p.amount) }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <XAxis dataKey="month" />
        <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
        <Tooltip formatter={(v: number) => `$${v.toLocaleString()}`} />
        <Line type="monotone" dataKey="amount" stroke="hsl(var(--terzo-primary))" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
