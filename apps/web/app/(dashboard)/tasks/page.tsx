// SERVER — workflow tasks (§5). The approve/reject queue is the human-in-the-loop gate:
// no external action fires until a reviewer approves a task awaiting approval.
import { TaskApprovalQueue } from "@/components/modules/tasks/task-approval-queue";
import { apiServer } from "@/lib/api";
import type { TasksResponse } from "@/lib/types";

export default async function TasksPage() {
  const { tasks } = await apiServer.get<TasksResponse>("/tasks");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Workflow Tasks</h1>
      <p className="text-sm text-muted-foreground">
        AI-drafted actions wait here for human approval. Nothing is sent externally until a task
        awaiting approval is explicitly approved &mdash; rejecting one sends nothing.
      </p>
      <TaskApprovalQueue initial={tasks} />
    </div>
  );
}
