"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatUsd } from "@/lib/format";
import type { RecoveryPack } from "@/lib/types";

export function RecoveryPackCard({ pack }: { pack: RecoveryPack }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <div className="font-medium">Vendor {pack.vendor_id.slice(0, 8)}</div>
        <div className="font-semibold text-[hsl(var(--terzo-recovery))]">
          {formatUsd(pack.total)}
        </div>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {pack.items.length} recoverable item(s)
      </p>
      <button className="mt-2 text-sm underline" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Show"} evidence
      </button>
      {open && (
        <ul className="mt-2 space-y-1 text-sm">
          {pack.items.map((it) => (
            <li key={it.rec_id} className="flex justify-between">
              <span>{it.evidence.formula ?? it.opp_id.slice(0, 8)}</span>
              <span className="tabular-nums">{formatUsd(it.amount)}</span>
            </li>
          ))}
        </ul>
      )}
      {/* Phase 6: opens NirvanaI with the "supplier challenge letter" template prefilled. */}
      <Button size="sm" className="mt-3" disabled title="Available in Phase 6">
        Draft challenge letter
      </Button>
    </div>
  );
}
