"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

// On tenant switch we MUST flush the client cache so no prior-tenant data bleeds
// across (keys never span tenants; backend RLS is the real boundary). §11.
export function TenantSwitcher() {
  const qc = useQueryClient();
  const [tenant, setTenant] = useState("Acme Corp");

  function switchTenant(next: string) {
    setTenant(next);
    qc.clear(); // no cross-tenant data bleed in the client cache
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Tenant</span>
      <select
        value={tenant}
        onChange={(e) => switchTenant(e.target.value)}
        className="rounded-md border bg-transparent px-2 py-1"
        aria-label="Switch tenant"
      >
        <option>Acme Corp</option>
        <option>Globex</option>
      </select>
    </label>
  );
}
