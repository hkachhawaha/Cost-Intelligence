// SERVER — first dimension + trend + coverage preloaded in parallel.
import { SpendExplorerClient } from "@/components/modules/spend/spend-explorer-client";
import { apiServer } from "@/lib/api";
import type { MatchCoverageResponse, SpendBreakdownResponse, SpendTrendPoint } from "@/lib/types";

export default async function SpendExplorerPage() {
  const [byVendor, trend, coverage] = await Promise.all([
    apiServer.get<SpendBreakdownResponse>("/spend/by-vendor"),
    apiServer.get<{ items: SpendTrendPoint[] }>("/spend/trend"),
    apiServer.get<MatchCoverageResponse>("/spend/match-coverage"),
  ]);
  return <SpendExplorerClient byVendor={byVendor} trend={trend.items} coverage={coverage} />;
}
