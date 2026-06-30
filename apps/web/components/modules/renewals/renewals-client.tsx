"use client";

import { useState } from "react";

import { useRenewals } from "@/lib/hooks/use-renewals";
import type { RenewalsResponse } from "@/lib/types";

import { RenewalRow } from "./renewal-row";

export function RenewalsClient({ initial }: { initial: RenewalsResponse }) {
  const [window, setWindow] = useState<90 | 180 | 365>(90);
  const { data } = useRenewals(window, window === 90 ? initial : undefined);
  const all = [
    ...(data?.within_90 ?? []),
    ...(data?.within_180 ?? []),
    ...(data?.within_365 ?? []),
  ].sort((a, b) => a.days_to_end - b.days_to_end); // urgency first

  return (
    <>
      <div className="flex gap-2">
        {([90, 180, 365] as const).map((w) => (
          <button
            key={w}
            onClick={() => setWindow(w)}
            aria-pressed={window === w}
            className={
              window === w
                ? "rounded-md bg-[hsl(var(--terzo-primary))] px-3 py-1 text-sm text-white"
                : "rounded-md border px-3 py-1 text-sm"
            }
          >
            {w} days
          </button>
        ))}
      </div>
      {all.length === 0 ? (
        <p className="text-sm text-muted-foreground">No renewals in this window.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {all.map((r) => (
            <RenewalRow key={r.contract_id} renewal={r} />
          ))}
        </ul>
      )}
    </>
  );
}
