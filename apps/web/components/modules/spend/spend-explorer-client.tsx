"use client";

import { useState } from "react";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSpendBreakdown } from "@/lib/hooks/use-spend";
import type { MatchCoverageResponse, SpendBreakdownResponse, SpendTrendPoint } from "@/lib/types";

import { MatchCoverageDonut } from "./match-coverage-donut";
import { SpendBarChart } from "./spend-bar-chart";
import { SpendTrendChart } from "./spend-trend-chart";

type Dim = "by-vendor" | "by-category" | "by-cost-center";

export function SpendExplorerClient({
  byVendor,
  trend,
  coverage,
}: {
  byVendor: SpendBreakdownResponse;
  trend: SpendTrendPoint[];
  coverage: MatchCoverageResponse;
}) {
  const [dim, setDim] = useState<Dim>("by-vendor");
  const { data } = useSpendBreakdown(dim, dim === "by-vendor" ? byVendor : undefined);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Spend Explorer</h1>
      <Tabs value={dim} onValueChange={(v) => setDim(v as Dim)}>
        <TabsList>
          <TabsTrigger value="by-vendor">By Vendor</TabsTrigger>
          <TabsTrigger value="by-category">By Category</TabsTrigger>
          <TabsTrigger value="by-cost-center">By Cost Center</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="rounded-lg border p-4">
        <SpendBarChart items={data?.items ?? []} />
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-lg border p-4 lg:col-span-2">
          <h2 className="mb-3 text-sm font-medium">Spend Trend</h2>
          <SpendTrendChart points={trend} />
        </div>
        <div className="rounded-lg border p-4">
          <h2 className="mb-3 text-sm font-medium">Match Coverage</h2>
          <MatchCoverageDonut coverage={coverage} />
        </div>
      </div>
    </div>
  );
}
