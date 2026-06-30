"use client";

import * as React from "react";

import { cn } from "@/lib/cn";

interface TabsCtx {
  value: string;
  onValueChange: (v: string) => void;
}
const Ctx = React.createContext<TabsCtx | null>(null);

export function Tabs({
  value,
  onValueChange,
  children,
}: {
  value: string;
  onValueChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return <Ctx.Provider value={{ value, onValueChange }}>{children}</Ctx.Provider>;
}

export function TabsList({ children }: { children: React.ReactNode }) {
  return (
    <div role="tablist" className="inline-flex gap-1 rounded-md border p-1">
      {children}
    </div>
  );
}

export function TabsTrigger({ value, children }: { value: string; children: React.ReactNode }) {
  const ctx = React.useContext(Ctx);
  const active = ctx?.value === value;
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={() => ctx?.onValueChange(value)}
      className={cn(
        "rounded px-3 py-1 text-sm",
        active ? "bg-[hsl(var(--terzo-primary))] text-white" : "hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}
