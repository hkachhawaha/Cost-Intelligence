// SERVER component — single memory read (<50ms), no source query.
import { AlertsPanel } from "@/components/modules/dashboard/alerts-panel";
import { KpiTile } from "@/components/modules/dashboard/kpi-tile";
import { OnboardingEmptyState } from "@/components/modules/dashboard/onboarding-empty-state";
import { OpportunityByTypeChart } from "@/components/modules/dashboard/opportunity-chart";
import { SyncStatusBanner } from "@/components/shell/sync-status-banner";
import { apiServer } from "@/lib/api";
import type { DashboardKpis } from "@/lib/types";

export default async function DashboardPage() {
  const kpis = await apiServer.get<DashboardKpis>("/dashboard/kpis");

  if (!kpis.initialized) return <OnboardingEmptyState />;

  return (
    <div className="space-y-6">
      <SyncStatusBanner stale={kpis.stale} lastSynced={kpis.last_synced_at} />

      <section
        aria-label="Key metrics"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5"
      >
        <KpiTile
          label="Spend Under Management"
          value={kpis.spend_under_management_pct}
          format="pct"
        />
        <KpiTile label="Contract Compliance" value={kpis.contract_compliance_pct} format="pct" />
        <KpiTile label="PO Coverage" value={kpis.po_coverage_pct} format="pct" />
        <KpiTile
          label="Identified Savings"
          value={kpis.total_savings}
          format="usd"
          tone="savings"
        />
        <KpiTile
          label="Recoverable Cash"
          value={kpis.total_recovery}
          format="usd"
          tone="recovery"
        />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="rounded-lg border p-4 lg:col-span-2">
          <h2 className="mb-3 text-sm font-medium">Opportunity by Type</h2>
          <OpportunityByTypeChart
            countByType={kpis.opportunity_count_by_type}
            amountByType={kpis.opportunity_amount_by_type}
          />
        </section>
        <AlertsPanel alerts={kpis.alerts} />
      </div>
    </div>
  );
}
