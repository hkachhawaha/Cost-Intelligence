// One chat message + inline source citations (§3 MessageBubble).
import { cn } from "@/lib/cn";
import type { ChatUiMessage } from "@/lib/types";

export function MessageBubble({ message }: { message: ChatUiMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-3 py-2 text-sm",
          isUser
            ? "bg-[hsl(var(--terzo-primary))] text-white"
            : "border bg-[hsl(var(--terzo-surface-raised))]",
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser && message.citations && message.citations.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1">
            {message.citations.map((c) => (
              <li
                key={c.record_id}
                title={c.label}
                className="rounded-full border bg-background px-2 py-0.5 text-[11px] text-muted-foreground"
              >
                {c.label}
              </li>
            ))}
          </ul>
        )}
        {!isUser && message.grounded === false && (
          <p className="mt-1 text-[11px] text-[hsl(var(--terzo-recovery))]">
            Not grounded — no figure stated.
          </p>
        )}
      </div>
    </div>
  );
}
