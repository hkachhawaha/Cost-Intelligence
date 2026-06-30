"use client";

import { useState } from "react";

import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import type { NirvanaDraft } from "@/lib/types";

// Editable draft preview with copy / "Mark sent" (§3 DocumentPreview). The platform
// never sends — "Mark sent" is the human action that PATCHes status=sent (audited).
export function DocumentPreview({ draft }: { draft: NirvanaDraft }) {
  const [body, setBody] = useState(draft.body_markdown);
  const [status, setStatus] = useState(draft.status);
  const sent = status === "sent";

  async function markSent() {
    await apiClient.patch(`/nirvana/drafts/${draft.draft_id}`, { status: "sent" });
    setStatus("sent");
  }

  return (
    <div className="rounded-lg border p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium">{draft.title}</h3>
        <span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
          {status}
        </span>
      </div>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        readOnly={sent}
        rows={10}
        className="w-full rounded-md border bg-transparent p-2 text-sm"
        aria-label="Draft body"
      />
      <div className="mt-2 flex gap-2">
        <Button size="sm" variant="outline" onClick={() => navigator.clipboard?.writeText(body)}>
          Copy
        </Button>
        <Button size="sm" onClick={markSent} disabled={sent}>
          {sent ? "Sent" : "Mark sent"}
        </Button>
      </div>
    </div>
  );
}
