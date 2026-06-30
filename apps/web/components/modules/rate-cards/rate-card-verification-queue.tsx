"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import type { RateCard } from "@/lib/types";

// Human verification of extracted rate cards. Only verified cards drive line-item $ math;
// verification is role-gated (legal/category_mgr/admin) at the API.
export function RateCardVerificationQueue({ initial }: { initial: RateCard[] }) {
  const [cards, setCards] = useState(initial);

  async function verify(id: string) {
    await apiClient.post(`/rate-cards/${id}/verify`, {});
    setCards((cs) => cs.filter((c) => c.id !== id));
  }

  if (cards.length === 0) {
    return <p className="text-sm text-muted-foreground">No rate cards awaiting verification.</p>;
  }

  return (
    <ul className="space-y-3">
      {cards.map((c) => (
        <li key={c.id} className="rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <span className="font-medium">{c.sku}</span>
            <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
              {c.is_tiered ? "tiered" : `${c.unit_rate}/${c.uom}`}
              {c.confidence && ` · conf ${(Number(c.confidence) * 100).toFixed(0)}%`}
            </span>
          </div>
          {c.raw_sku && c.raw_sku !== c.sku && (
            <p className="mt-1 text-xs text-muted-foreground">raw: {c.raw_sku}</p>
          )}
          {c.is_tiered && (
            <table className="mt-2 w-full text-xs">
              <tbody>
                {c.tiers.map((t) => (
                  <tr key={t.tier_index}>
                    <td>
                      {t.min_volume}–{t.max_volume ?? "∞"}
                    </td>
                    <td className="text-right tabular-nums">{t.tier_rate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="mt-3">
            <Button size="sm" onClick={() => verify(c.id)}>
              Verify
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
