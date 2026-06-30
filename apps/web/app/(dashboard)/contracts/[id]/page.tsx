// SERVER — drill-down: detail + linked spend + utilization, both canonical reads.
import { ContractFields } from "@/components/modules/contracts/contract-fields";
import { IndexationBadge } from "@/components/modules/contracts/indexation-badge";
import { LinkedSpendTable } from "@/components/modules/contracts/linked-spend-table";
import { UtilizationBar } from "@/components/modules/contracts/utilization-bar";
import { apiServer } from "@/lib/api";
import type { ContractDetail, ContractSpendResponse } from "@/lib/types";

export default async function ContractDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [contract, spend] = await Promise.all([
    apiServer.get<ContractDetail>(`/contracts/${id}`),
    apiServer.get<ContractSpendResponse>(`/contracts/${id}/spend`),
  ]);
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">Contract {contract.id.slice(0, 8)}</h1>
        {contract.indexation.has_indexation && (
          <IndexationBadge indexation={contract.indexation} />
        )}
      </div>
      <div className="rounded-lg border p-4">
        <h2 className="mb-2 text-sm font-medium">Utilization</h2>
        <UtilizationBar
          utilizationPct={spend.utilization_pct}
          matchedSpend={spend.total_matched_spend}
          acv={contract.acv}
        />
      </div>
      <ContractFields contract={contract} />
      <div className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium">Linked Spend ({spend.lines.length})</h2>
        <LinkedSpendTable lines={spend.lines} />
      </div>
    </div>
  );
}
