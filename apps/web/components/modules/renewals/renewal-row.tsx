import { cn } from "@/lib/cn";
import { formatDate, formatUsd } from "@/lib/format";
import type { RenewalEntry } from "@/lib/types";

export function RenewalRow({ renewal }: { renewal: RenewalEntry }) {
  const urgent = renewal.days_to_end <= 90;
  const auto = renewal.renewal_type === "auto";
  return (
    <li className="flex items-center justify-between px-4 py-3">
      <div>
        <div className="font-medium">Contract {renewal.contract_id.slice(0, 8)}</div>
        <div className="text-xs text-muted-foreground">
          Ends {formatDate(renewal.end_date)} · notice by {formatDate(renewal.notice_deadline)}
        </div>
      </div>
      <div className="flex items-center gap-3 text-sm">
        {auto && (
          <span className="rounded-full bg-[hsl(var(--terzo-danger))]/15 px-2 py-0.5 text-xs text-[hsl(var(--terzo-danger))]">
            auto-renews
          </span>
        )}
        <span className="tabular-nums">{formatUsd(renewal.acv ?? 0)}</span>
        <span className={cn("tabular-nums", urgent && "font-medium text-[hsl(var(--terzo-danger))]")}>
          {renewal.days_to_end}d
        </span>
      </div>
    </li>
  );
}
