// SERVER component — nav config is static.
import Link from "next/link";

import { cn } from "@/lib/cn";
import type { ModuleDef } from "@/lib/modules";

export function Sidebar({ modules }: { modules: ModuleDef[] }) {
  return (
    <nav
      aria-label="Modules"
      className="w-60 shrink-0 border-r bg-[hsl(var(--terzo-surface-raised))]"
    >
      <div className="px-4 py-5 font-semibold tracking-tight">Terzo Cost Intelligence</div>
      <ul className="space-y-1 px-2">
        {modules.map((m) => (
          <li key={m.slug}>
            <Link
              href={m.v1Enabled ? `/${m.slug}` : "#"}
              aria-disabled={!m.v1Enabled}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
                m.v1Enabled ? "hover:bg-accent" : "cursor-not-allowed opacity-40",
              )}
            >
              <m.icon className="h-4 w-4" aria-hidden />
              <span>{m.label}</span>
              {!m.v1Enabled && <span className="ml-auto text-xs">Soon</span>}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
