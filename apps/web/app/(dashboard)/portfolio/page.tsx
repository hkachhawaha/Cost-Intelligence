// SERVER — multi-entity rollup + Phase 10 vendor leverage (portfolio_admin only; 403 otherwise).
import { ApiError, apiServer } from "@/lib/api";
import { formatPct, formatUsd } from "@/lib/format";
import type { PortfolioResponse, VendorLeverageResponse } from "@/lib/types";

export default async function PortfolioPage() {
  let data: PortfolioResponse | null = null;
  let leverage: VendorLeverageResponse | null = null;
  let denied = false;
  try {
    data = await apiServer.get<PortfolioResponse>("/portfolio/by-entity");
    leverage = await apiServer.get<VendorLeverageResponse>("/portfolio/vendor-leverage");
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) denied = true;
    else throw e;
  }

  if (denied) {
    return (
      <div className="mx-auto max-w-md rounded-lg border p-8 text-center">
        <h1 className="text-lg font-semibold">Portfolio</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The portfolio view is available to portfolio administrators only.
        </p>
      </div>
    );
  }

  const entities = data?.entities ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Portfolio</h1>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2">Entity</th>
            <th className="text-right">Spend</th>
            <th className="text-right">Under mgmt</th>
            <th className="text-right">Savings</th>
            <th className="text-right">Recovery</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => (
            <tr key={e.entity_id} className="border-b">
              <td className="py-2 font-medium">{e.entity_name}</td>
              <td className="text-right tabular-nums">{formatUsd(e.total_spend)}</td>
              <td className="text-right tabular-nums">
                {formatPct(Number(e.spend_under_management_pct) * 100)}
              </td>
              <td className="text-right tabular-nums text-[hsl(var(--terzo-savings))]">
                {formatUsd(e.identified_savings)}
              </td>
              <td className="text-right tabular-nums text-[hsl(var(--terzo-recovery))]">
                {formatUsd(e.identified_recovery)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Same-vendor multi-entity leverage</h2>
        <p className="text-xs text-muted-foreground">
          First-party consolidation signal &mdash; vendors spending across &ge;2 entities. No
          external pricing is used.
        </p>
        {(leverage?.vendors ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No multi-entity vendors detected (needs a vendor across &ge;2 entities).
          </p>
        ) : (
          <ul className="space-y-2">
            {leverage!.vendors.map((v) => (
              <li key={v.vendor_id} className="rounded-lg border p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{v.vendor ?? v.vendor_id}</span>
                  <span className="tabular-nums">{formatUsd(v.total_spend)}</span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {v.entity_count} entities &middot; {v.leverage_estimate}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
