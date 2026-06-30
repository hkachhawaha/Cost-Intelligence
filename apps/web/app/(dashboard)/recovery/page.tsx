// SERVER — recovery packs (recovery_items grouped by vendor with totals + evidence).
import { RecoveryPackCard } from "@/components/modules/recovery/recovery-pack-card";
import { apiServer } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type { RecoveryPacksResponse } from "@/lib/types";

export default async function MarginRecoveryPage() {
  const { packs } = await apiServer.get<RecoveryPacksResponse>("/recovery/packs");
  const grandTotal = packs.reduce((s, p) => s + Number(p.total), 0);
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Margin Recovery</h1>
        <span className="text-sm text-muted-foreground">
          Recoverable:{" "}
          <strong className="text-[hsl(var(--terzo-recovery))]">{formatUsd(grandTotal)}</strong>
        </span>
      </div>
      {packs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No recoverable items detected.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {packs.map((p) => (
            <RecoveryPackCard key={p.vendor_id} pack={p} />
          ))}
        </div>
      )}
    </div>
  );
}
