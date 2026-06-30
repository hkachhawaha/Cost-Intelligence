"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const TONE: Record<string, string> = {
  maverick: "hsl(var(--terzo-savings))",
  unused_commitment: "hsl(var(--terzo-savings))",
  auto_renewal: "hsl(var(--terzo-savings))",
  uplift_creep: "hsl(var(--terzo-savings))",
  overspend: "hsl(var(--terzo-recovery))",
  spend_after_expiry: "hsl(var(--terzo-recovery))",
  post_expiry: "hsl(var(--terzo-recovery))",
  duplicate_invoice: "hsl(var(--terzo-recovery))",
};

export function OpportunityByTypeChart({
  countByType,
  amountByType,
}: {
  countByType: Record<string, number>;
  amountByType: Record<string, string>;
}) {
  const data = Object.entries(countByType).map(([type, count]) => ({
    type,
    count,
    amount: Number(amountByType[type] ?? 0),
  }));
  if (data.length === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">No opportunities yet.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
        <XAxis type="number" tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
        <YAxis type="category" dataKey="type" width={120} />
        <Tooltip formatter={(v: number) => `$${v.toLocaleString()}`} />
        <Bar dataKey="amount">
          {data.map((d) => (
            <Cell key={d.type} fill={TONE[d.type] ?? "hsl(var(--terzo-control))"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
