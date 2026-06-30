"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiClient } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type { ExposureResponse } from "@/lib/types";

// Interactive exposure modeling: indexed_exposure = ACV × indexed_share × assumed_move.
// `assumed_move` is the user's FIRST-PARTY assumption (the slider), not a market feed.
export function ExposureSlider({ initial }: { initial: ExposureResponse }) {
  const [movePct, setMovePct] = useState(10);
  const { data } = useQuery({
    queryKey: ["indexation-exposure", movePct],
    queryFn: () => apiClient.get<ExposureResponse>(`/indexation/exposure?move_pct=${movePct}`),
    initialData: movePct === 10 ? initial : undefined,
    staleTime: 0,
  });
  const result = data ?? initial;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border p-4">
        <label className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">Assumed index move</span>
          <input
            type="range"
            min={0}
            max={50}
            value={movePct}
            onChange={(e) => setMovePct(Number(e.target.value))}
            className="flex-1"
            aria-label="Assumed index move percent"
          />
          <span className="w-12 tabular-nums">{movePct}%</span>
        </label>
        <div className="mt-3 text-sm">
          Total indexed exposure:{" "}
          <strong className="text-[hsl(var(--terzo-recovery))]">
            {formatUsd(result.total_indexed_exposure)}
          </strong>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{result.note}</p>
      </div>

      {result.lines.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2">Vendor</th>
              <th>Index</th>
              <th className="text-right">ACV</th>
              <th className="text-right">Indexed share</th>
              <th className="text-right">Exposure</th>
            </tr>
          </thead>
          <tbody>
            {result.lines.map((ln) => (
              <tr key={ln.contract_id} className="border-b">
                <td className="py-2">{ln.vendor_name}</td>
                <td>{ln.index_type}</td>
                <td className="text-right tabular-nums">{formatUsd(ln.acv)}</td>
                <td className="text-right tabular-nums">
                  {(Number(ln.indexed_share) * 100).toFixed(0)}%
                </td>
                <td className="text-right tabular-nums">{formatUsd(ln.indexed_exposure)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
