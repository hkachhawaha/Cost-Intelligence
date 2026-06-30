// SERVER — pure presentational.
import { cn } from "@/lib/cn";
import { formatPct, formatUsd } from "@/lib/format";

export function KpiTile({
  label,
  value,
  format,
  tone = "default",
}: {
  label: string;
  value: string | number;
  format: "pct" | "usd";
  tone?: "default" | "savings" | "recovery";
}) {
  const display = format === "pct" ? formatPct(value) : formatUsd(value);
  const toneClass =
    tone === "savings"
      ? "text-[hsl(var(--terzo-savings))]"
      : tone === "recovery"
        ? "text-[hsl(var(--terzo-recovery))]"
        : "";
  return (
    <div className="rounded-lg border bg-[hsl(var(--terzo-surface-raised))] p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-2xl font-semibold tabular-nums", toneClass)}>{display}</div>
    </div>
  );
}
