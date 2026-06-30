"use client";

import { useState } from "react";

import { formatDate } from "@/lib/format";
import type { DataQualityEventsResponse } from "@/lib/types";

// The human-review feed. Accept/reassign actions reuse the Phase 2 match endpoints
// (wired per-row as the maverick queue is surfaced); v1 lists the recent DQ events.
export function ReviewQueueClient({
  initialEvents,
}: {
  initialEvents: DataQualityEventsResponse;
}) {
  const [events] = useState(initialEvents.items);
  return (
    <section className="rounded-lg border p-4">
      <h2 className="mb-3 text-sm font-medium">Review queue</h2>
      {events.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing awaiting review.</p>
      ) : (
        <ul className="divide-y text-sm">
          {events.map((e) => (
            <li key={e.id} className="flex items-center justify-between py-2">
              <span>{e.event_type.replace(/[._]/g, " ")}</span>
              <span className="text-xs text-muted-foreground">{formatDate(e.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
