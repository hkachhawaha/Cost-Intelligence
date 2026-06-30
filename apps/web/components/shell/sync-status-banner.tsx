import Link from "next/link";

import { formatDate } from "@/lib/format";

// Amber banner when memory is stale (source edited, no refresh — §5.8). Modules
// keep rendering the last-good memory by design; this just prompts a refresh.
export function SyncStatusBanner({
  stale,
  lastSynced,
}: {
  stale: boolean;
  lastSynced: string | null;
}) {
  if (!stale) return null;
  return (
    <div
      role="status"
      className="flex items-center justify-between rounded-md border border-[hsl(var(--terzo-recovery))] bg-[hsl(var(--terzo-recovery))]/10 px-4 py-2 text-sm"
    >
      <span>
        Source data changed since {formatDate(lastSynced)}. Refresh to update your intelligence.
      </span>
      <Link href="/settings/data-sources" className="font-medium underline">
        Go to Data Sources
      </Link>
    </div>
  );
}
