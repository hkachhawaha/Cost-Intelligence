// SERVER — contract register (canonical, paginated, ordered by ACV).
import Link from "next/link";

import { apiServer } from "@/lib/api";
import { formatDate, formatUsd } from "@/lib/format";
import type { ContractListResponse } from "@/lib/types";

export default async function ContractsPage() {
  const { items, total } = await apiServer.get<ContractListResponse>("/contracts?page=1");
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Contracts</h1>
        <span className="text-sm text-muted-foreground">{total} total</span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No contracts ingested yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2">Contract</th>
              <th>Status</th>
              <th>Renewal</th>
              <th>End</th>
              <th className="text-right">ACV</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-b hover:bg-accent">
                <td className="py-2">
                  <Link href={`/contracts/${c.id}`} className="font-medium underline">
                    {c.id.slice(0, 8)}
                  </Link>
                </td>
                <td>{c.status}</td>
                <td>{c.renewal_type ?? "—"}</td>
                <td>{formatDate(c.end_date)}</td>
                <td className="text-right tabular-nums">{formatUsd(c.acv ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
