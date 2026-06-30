"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useNirvanaChat } from "@/lib/hooks/use-nirvana";
import type { ChatUiMessage } from "@/lib/types";

import { MessageBubble } from "./message-bubble";

// Persistent slide-in chat surface (§3 ChatPanel). Grounded Q&A with inline citations;
// answers come from first-party data only (the backend enforces groundedness).
export function ChatPanel({ moduleContext }: { moduleContext?: string }) {
  const [messages, setMessages] = useState<ChatUiMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);
  const chat = useNirvanaChat();

  async function send() {
    const message = input.trim();
    if (!message || chat.isPending) return;
    setError(null);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message }]);
    try {
      const res = await chat.mutateAsync({
        message,
        conversation_id: conversationId,
        module_context: moduleContext,
      });
      setConversationId(res.conversation_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          grounded: res.grounded,
          citations: res.citations,
        },
      ]);
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 503
          ? "Run an initial sync to enable NirvanaI."
          : e instanceof ApiError && e.status === 429
            ? "You've reached the assistant usage cap for now. Try again shortly."
            : "Something went wrong. Please try again.";
      setError(msg);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto py-3">
        {messages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground">
            Ask about your spend, contracts, renewals, or opportunities. Every figure is cited to
            your own data.
          </p>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {chat.isPending && <p className="text-xs text-muted-foreground">NirvanaI is thinking…</p>}
        {error && <p className="text-xs text-[hsl(var(--terzo-danger))]">{error}</p>}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        className="flex gap-2 border-t pt-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask NirvanaI…"
          aria-label="Message NirvanaI"
          className="flex-1 rounded-md border bg-transparent px-3 py-2 text-sm"
        />
        <Button type="submit" size="sm" disabled={chat.isPending}>
          Send
        </Button>
      </form>
    </div>
  );
}
