// SERVER. Simple radial coverage indicator (match coverage % from memory).
import { formatPct } from "@/lib/format";

export function CoverageGauge({ pct }: { pct: string }) {
  const value = Math.min(Math.max(Number(pct), 0), 100);
  return (
    <div className="rounded-lg border p-4">
      <div className="text-xs text-muted-foreground">Match coverage</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{formatPct(pct)}</div>
      <div className="mt-2 h-2 w-full rounded bg-muted">
        <div
          className="h-2 rounded bg-[hsl(var(--terzo-savings))]"
          style={{ width: `${value}%` }}
          role="progressbar"
          aria-valuenow={value}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}
