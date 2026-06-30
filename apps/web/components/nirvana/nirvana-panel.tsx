"use client";

import { MessageSquare } from "lucide-react";
import { useState } from "react";

import { ChatPanel } from "./chat-panel";

// Persistent slide-in NirvanaI assistant (Phase 6). The launcher is available on every
// module via the shell; the panel mounts the grounded ChatPanel.
export function NirvanaIPanel() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Open NirvanaI assistant"
        className="fixed bottom-6 right-6 rounded-full bg-[hsl(var(--terzo-primary))] p-3 text-white shadow-lg"
      >
        <MessageSquare className="h-5 w-5" />
      </button>
      {open && (
        <aside
          role="complementary"
          aria-label="NirvanaI"
          className="fixed inset-y-0 right-0 flex w-96 flex-col border-l bg-background p-4 shadow-xl"
        >
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">NirvanaI</h2>
            <button onClick={() => setOpen(false)} aria-label="Close">
              ✕
            </button>
          </div>
          <div className="mt-3 flex-1 overflow-hidden">
            <ChatPanel />
          </div>
        </aside>
      )}
    </>
  );
}
