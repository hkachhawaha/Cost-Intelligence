"use client";

// Minimal user menu — the Auth0 logout route is wired in Phase 0.
export function UserMenu() {
  return (
    <a
      href="/api/auth/logout"
      className="rounded-md px-3 py-1 text-sm hover:bg-accent"
      aria-label="Account menu"
    >
      Sign out
    </a>
  );
}
