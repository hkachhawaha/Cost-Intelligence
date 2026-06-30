"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, apiClient } from "@/lib/api";
import type { WorkflowTask } from "@/lib/types";

// Human-in-the-loop approval queue (§5.1). Approve fires the gated external action; reject
// sends nothing. Both are role-gated (cfo/legal/category_mgr/admin) at the API — a 403 from a
// non-approver surfaces here as an inline error.
const STATUS_TONE: Record<string, string> = {
  awaiting_approval: "text-[hsl(var(--terzo-recovery))]",
  completed: "text-emerald-600",
  cancelled: "text-muted-foreground",
  rejected: "text-muted-foreground",
};

export function TaskApprovalQueue({ initial }: { initial: WorkflowTask[] }) {
  const [tasks, setTasks] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(id: string, action: "approve" | "reject") {
    setBusy(id);
    setError(null);
    try {
      const result = await apiClient.post<{ status: string }>(`/tasks/${id}/${action}`, {});
      setTasks((ts) => ts.map((t) => (t.id === id ? { ...t, status: result.status } : t)));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "action failed");
    } finally {
      setBusy(null);
    }
  }

  if (tasks.length === 0) {
    return <p className="text-sm text-muted-foreground">No workflow tasks.</p>;
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-3">
        {tasks.map((t) => (
          <li key={t.id} className="rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">{t.title}</span>
              <span className={`text-xs ${STATUS_TONE[t.status] ?? "text-muted-foreground"}`}>
                {t.status.replace(/_/g, " ")}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {t.type} · priority {t.priority}
              {t.due_date && ` · due ${t.due_date}`}
            </p>
            {t.status === "awaiting_approval" && (
              <div className="mt-3 flex gap-2">
                <Button size="sm" disabled={busy === t.id} onClick={() => decide(t.id, "approve")}>
                  Approve &amp; send
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy === t.id}
                  onClick={() => decide(t.id, "reject")}
                >
                  Reject
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
