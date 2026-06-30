import { cn } from "@/lib/cn";

const TONE: Record<string, string> = {
  detected: "bg-muted text-foreground",
  triaged: "bg-[hsl(var(--terzo-control))]/15 text-[hsl(var(--terzo-control))]",
  in_progress: "bg-[hsl(var(--terzo-primary))]/15 text-[hsl(var(--terzo-primary))]",
  realized: "bg-[hsl(var(--terzo-savings))]/15 text-[hsl(var(--terzo-savings))]",
  dismissed: "bg-muted text-muted-foreground line-through",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs", TONE[status] ?? "bg-muted")}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
