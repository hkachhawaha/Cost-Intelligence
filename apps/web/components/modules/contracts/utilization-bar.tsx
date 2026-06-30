// SERVER. Caps the bar at 100%, shows the true % in danger color when over (§10).
import { cn } from "@/lib/cn";
import { formatPct, formatUsd } from "@/lib/format";

export function UtilizationBar({
  utilizationPct,
  matchedSpend,
  acv,
}: {
  utilizationPct: string;
  matchedSpend: string;
  acv: string | null;
}) {
  const pct = Math.min(Number(utilizationPct), 100);
  const over = Number(utilizationPct) > 100;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span>
          {formatUsd(matchedSpend)} of {formatUsd(acv ?? 0)} ACV
        </span>
        <span className={over ? "font-medium text-[hsl(var(--terzo-danger))]" : ""}>
          {formatPct(utilizationPct)}
        </span>
      </div>
      <div className="h-2 w-full rounded bg-muted">
        <div
          className={cn(
            "h-2 rounded",
            over ? "bg-[hsl(var(--terzo-danger))]" : "bg-[hsl(var(--terzo-primary))]",
          )}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={Number(utilizationPct)}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}
