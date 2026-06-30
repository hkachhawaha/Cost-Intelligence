"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import type { ExtractionItem } from "@/lib/types";

// Human verification of extracted contract terms. Nothing reaches the canonical record
// until a reviewer promotes it; an injection_flags banner warns on suspicious documents.
export function VerificationQueue({ initial }: { initial: ExtractionItem[] }) {
  const [items, setItems] = useState(initial);

  async function act(id: string, action: "promote" | "reject") {
    await apiClient.post(`/extraction/verification-queue/${id}/verify`, { action });
    setItems((xs) => xs.filter((x) => x.id !== id));
  }

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing awaiting verification.</p>;
  }

  return (
    <ul className="space-y-3">
      {items.map((it) => (
        <li key={it.id} className="rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <span className="font-medium">
              Contract {it.contract_id ? it.contract_id.slice(0, 8) : "(new)"}
            </span>
            <span className="rounded-full border px-2 py-0.5 text-xs">{it.status}</span>
          </div>
          {it.injection_flags.length > 0 && (
            <p className="mt-2 rounded-md border border-[hsl(var(--terzo-danger))] bg-[hsl(var(--terzo-danger))]/10 px-2 py-1 text-xs text-[hsl(var(--terzo-danger))]">
              ⚠ Suspected prompt injection in the document — review carefully.
            </p>
          )}
          <dl className="mt-2 grid grid-cols-2 gap-2 text-sm md:grid-cols-3">
            {Object.entries(it.extracted_fields).map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted-foreground">{k}</dt>
                <dd className="tabular-nums">{String(v)}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => act(it.id, "promote")}>
              Promote
            </Button>
            <Button size="sm" variant="ghost" onClick={() => act(it.id, "reject")}>
              Reject
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
