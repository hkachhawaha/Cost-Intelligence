// SERVER. Spend matched to this contract (via match_results), with lineage.
import { formatDate, formatUsd } from "@/lib/format";
import type { ContractSpendLine } from "@/lib/types";

export function LinkedSpendTable({ lines }: { lines: ContractSpendLine[] }) {
  if (lines.length === 0) {
    return <p className="text-sm text-muted-foreground">No spend matched to this contract.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2">Spend</th>
          <th>Date</th>
          <th>PO</th>
          <th className="text-right">Amount</th>
        </tr>
      </thead>
      <tbody>
        {lines.map((l) => (
          <tr key={l.spend_id} className="border-b">
            <td className="py-2 font-mono text-xs">{l.spend_id.slice(0, 8)}</td>
            <td>{formatDate(l.spend_date)}</td>
            <td>{l.po_number ?? "—"}</td>
            <td className="text-right tabular-nums">{formatUsd(l.amount)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
