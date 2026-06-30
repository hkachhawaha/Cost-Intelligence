// Minimal classname joiner (shadcn uses clsx+tailwind-merge; this keeps deps lean).
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
