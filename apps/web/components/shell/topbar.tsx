"use client";

import { SyncStatusBadge } from "./sync-status-badge";
import { TenantSwitcher } from "./tenant-switcher";
import { UserMenu } from "./user-menu";

export function TopBar() {
  return (
    <header className="flex h-14 items-center gap-4 border-b px-6">
      <TenantSwitcher />
      <SyncStatusBadge />
      <div className="ml-auto">
        <UserMenu />
      </div>
    </header>
  );
}
