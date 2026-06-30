// SERVER. Renders the contract record (the 95+ field canonical model; v1 surfaces
// the headline commercial + renewal fields, full record expandable later).
import { formatDate, formatUsd } from "@/lib/format";
import type { ContractDetail } from "@/lib/types";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm tabular-nums">{value}</dd>
    </div>
  );
}

export function ContractFields({ contract }: { contract: ContractDetail }) {
  return (
    <div className="rounded-lg border p-4">
      <h2 className="mb-3 text-sm font-medium">Contract record</h2>
      <dl className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <Field label="Status" value={contract.status} />
        <Field label="ACV" value={formatUsd(contract.acv ?? 0)} />
        <Field label="TCV" value={formatUsd(contract.tcv ?? 0)} />
        <Field label="Start" value={formatDate(contract.start_date)} />
        <Field label="End" value={formatDate(contract.end_date)} />
        <Field label="Renewal" value={contract.renewal_type ?? "—"} />
        <Field label="Notice (days)" value={String(contract.renewal_notice_days ?? "—")} />
        <Field label="Uplift %" value={`${Number(contract.uplift_pct) * 100}%`} />
        <Field label="Yearly commit" value={formatUsd(contract.yearly_commit)} />
        <Field label="Payment terms" value={`${contract.payment_term_days ?? "—"} days`} />
        <Field label="Currency" value={contract.currency} />
        <Field label="Source" value={contract.source_system} />
      </dl>
    </div>
  );
}
