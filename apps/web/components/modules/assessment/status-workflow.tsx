"use client";

import { Button } from "@/components/ui/button";

// Allowed transitions (mirrors blueprint §8.3 lifecycle; backend is authoritative).
const NEXT: Record<string, { to: string; label: string }[]> = {
  detected: [
    { to: "triaged", label: "Triage" },
    { to: "dismissed", label: "Dismiss" },
  ],
  triaged: [
    { to: "in_progress", label: "Start" },
    { to: "dismissed", label: "Dismiss" },
  ],
  in_progress: [
    { to: "realized", label: "Mark Realized" },
    { to: "dismissed", label: "Dismiss" },
  ],
  realized: [],
  dismissed: [],
};

export function StatusWorkflow({
  current,
  onTransition,
}: {
  current: string;
  onTransition: (to: string) => void;
}) {
  return (
    <div className="flex gap-2">
      {NEXT[current]?.map((t) => (
        <Button
          key={t.to}
          size="sm"
          variant={t.to === "dismissed" ? "ghost" : "default"}
          onClick={() => onTransition(t.to)}
        >
          {t.label}
        </Button>
      ))}
    </div>
  );
}
