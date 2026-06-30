"use client";

import { useAssignOwner, useOpportunities, useUpdateStatus } from "@/lib/hooks/use-opportunities";
import { formatUsd } from "@/lib/format";
import type { OpportunityListResponse } from "@/lib/types";

import { OwnerSelect } from "./owner-select";
import { StatusBadge } from "./status-badge";
import { StatusWorkflow } from "./status-workflow";

export function AssessmentClient({ initialData }: { initialData: OpportunityListResponse }) {
  const { data } = useOpportunities({ sort: "ranked" }, initialData);
  const updateStatus = useUpdateStatus();
  const assign = useAssignOwner();
  const items = data?.items ?? [];

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No opportunities detected yet.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2">Type</th>
          <th>Bucket</th>
          <th className="text-right">Impact</th>
          <th className="text-right">Confidence</th>
          <th>Status</th>
          <th>Owner</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        {items.map((o) => (
          <tr key={o.id} className="border-b">
            <td className="py-2 font-medium">{o.type}</td>
            <td>{o.bucket}</td>
            <td className="text-right tabular-nums">{formatUsd(o.impact)}</td>
            <td className="text-right tabular-nums">{(Number(o.confidence) * 100).toFixed(0)}%</td>
            <td>
              <StatusBadge status={o.status} />
            </td>
            <td>
              <OwnerSelect
                value={o.owner_id}
                onChange={(owner_id) => assign.mutate({ id: o.id, owner_id })}
              />
            </td>
            <td>
              <StatusWorkflow
                current={o.status}
                onTransition={(status) => updateStatus.mutate({ id: o.id, status })}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
