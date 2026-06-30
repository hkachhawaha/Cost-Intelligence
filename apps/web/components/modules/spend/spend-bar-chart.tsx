"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { SpendBreakdownItem } from "@/lib/types";

export function SpendBarChart({ items }: { items: SpendBreakdownItem[] }) {
  if (items.length === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">No data for this view.</p>;
  }
  const data = items.map((i) => ({ label: i.label, amount: Number(i.amount) }));
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
        <XAxis type="number" tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
        <YAxis type="category" dataKey="label" width={140} />
        <Tooltip formatter={(v: number) => `$${v.toLocaleString()}`} />
        <Bar dataKey="amount" fill="hsl(var(--terzo-primary))" />
      </BarChart>
    </ResponsiveContainer>
  );
}
