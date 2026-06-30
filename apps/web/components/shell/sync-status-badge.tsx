"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { SyncStatus } from "@/lib/types";

// Polls /sync/status; shows a small stale/running indicator in the topbar.
// Phase 6 can swap polling for an SSE subscription to stream:memory.rebuilt (§8.1).
export function SyncStatusBadge() {
  const { data } = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => apiClient.get<SyncStatus>("/sync/status"),
    refetchInterval: 30_000,
  });
  if (!data) return null;
  if (data.status === "running") {
    return <span className="rounded-full bg-muted px-2 py-0.5 text-xs">Syncing…</span>;
  }
  if (data.stale) {
    return (
      <span className="rounded-full bg-[hsl(var(--terzo-recovery))]/15 px-2 py-0.5 text-xs text-[hsl(var(--terzo-recovery))]">
        Stale
      </span>
    );
  }
  return null;
}
