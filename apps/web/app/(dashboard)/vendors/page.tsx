// SERVER — vendor rollup + ranked consolidation candidates (code-computed).
import { apiServer } from "@/lib/api";
import { formatPct, formatUsd } from "@/lib/format";
import type { ConsolidationResponse, VendorListResponse } from "@/lib/types";

export default async function VendorsPage() {
  const [{ vendors }, { candidates }] = await Promise.all([
    apiServer.get<VendorListResponse>("/vendors"),
    apiServer.get<ConsolidationResponse>("/vendors/consolidation-candidates"),
  ]);
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Vendors</h1>

      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium">Consolidation candidates</h2>
        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">No fragmented categories detected.</p>
        ) : (
          <ul className="space-y-2">
            {candidates.map((c) => (
              <li key={c.key} className="flex items-center justify-between text-sm">
                <span>{c.label}</span>
                <span className="rounded-full border px-2 py-0.5 text-xs">
                  fragmentation {(Number(c.fragmentation_score) * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium">Vendor rollup</h2>
        {vendors.length === 0 ? (
          <p className="text-sm text-muted-foreground">No vendors yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2">Vendor</th>
                <th className="text-right">Spend</th>
                <th className="text-right">Contracts</th>
                <th className="text-right">Matched</th>
              </tr>
            </thead>
            <tbody>
              {vendors.map((v) => (
                <tr key={v.vendor_id} className="border-b">
                  <td className="py-2 font-medium">{v.name}</td>
                  <td className="text-right tabular-nums">{formatUsd(v.total_spend)}</td>
                  <td className="text-right tabular-nums">{v.contract_count}</td>
                  <td className="text-right tabular-nums">{formatPct(Number(v.matched_spend_pct) * 100)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
