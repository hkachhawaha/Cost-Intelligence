// SERVER — renders the memory `alerts` blob (auto-renewal windows, recoveries).
import type { Alert } from "@/lib/types";

const SEVERITY: Record<string, string> = {
  high: "text-[hsl(var(--terzo-danger))]",
  medium: "text-[hsl(var(--terzo-recovery))]",
};

export function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  return (
    <section className="rounded-lg border p-4" aria-label="Alerts">
      <h2 className="mb-3 text-sm font-medium">Alerts</h2>
      {alerts.length === 0 ? (
        <p className="text-sm text-muted-foreground">No active alerts.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {alerts.map((a, i) => (
            <li key={i} className="flex items-center justify-between">
              <span>{a.kind.replace(/_/g, " ")}</span>
              <span className={SEVERITY[a.severity] ?? ""}>{a.severity}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
