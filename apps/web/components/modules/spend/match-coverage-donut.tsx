"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { MatchCoverageResponse } from "@/lib/types";

const COLORS = [
  "hsl(var(--terzo-primary))",
  "hsl(var(--terzo-savings))",
  "hsl(var(--terzo-control))",
  "hsl(var(--terzo-danger))",
];

export function MatchCoverageDonut({ coverage }: { coverage: MatchCoverageResponse }) {
  const data = [
    { name: "PO exact", value: coverage.po_exact },
    { name: "Vendor+amount+date", value: coverage.vendor_amount_date },
    { name: "AI inferred", value: coverage.ai_inferred },
    { name: "Unmatched", value: coverage.unmatched },
  ].filter((d) => d.value > 0);

  if (data.length === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">No coverage data.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80}>
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}
