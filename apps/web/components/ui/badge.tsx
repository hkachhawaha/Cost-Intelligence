import { cn } from "@/lib/cn";

type Variant = "default" | "muted" | "warning";

const VARIANT: Record<Variant, string> = {
  default: "border bg-background text-foreground",
  muted: "border bg-muted text-muted-foreground",
  warning: "border-amber-300 bg-amber-50 text-amber-700",
};

export function Badge({
  variant = "default",
  className,
  children,
  title,
}: {
  variant?: Variant;
  className?: string;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        VARIANT[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
