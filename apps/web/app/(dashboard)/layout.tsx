// SERVER component — static shell (§3.2). Wraps modules in the TanStack Query
// provider so client components can refetch / invalidate.
import type { ReactNode } from "react";

import { NirvanaIPanel } from "@/components/nirvana/nirvana-panel";
import { Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/topbar";
import { MODULES } from "@/lib/modules";
import { Providers } from "@/lib/providers";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <Providers>
      <div className="flex h-screen bg-[hsl(var(--terzo-surface))]">
        <Sidebar modules={MODULES} />
        <div className="flex flex-1 flex-col overflow-hidden">
          <TopBar />
          <main className="flex-1 overflow-y-auto px-6 py-4" role="main">
            {children}
          </main>
        </div>
        <NirvanaIPanel />
      </div>
    </Providers>
  );
}
