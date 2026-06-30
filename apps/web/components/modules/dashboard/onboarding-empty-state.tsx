import Link from "next/link";

// Shown when memory isn't built yet (new tenant; /dashboard/kpis → initialized:false).
// A guided empty state, NOT an error (§9.4).
export function OnboardingEmptyState() {
  return (
    <div className="mx-auto max-w-md rounded-lg border p-8 text-center">
      <h2 className="text-lg font-semibold">Let’s build your cost intelligence</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Connect a data source and run the initial sync. Once memory is built, your dashboard,
        savings, and recovery opportunities appear here.
      </p>
      <Link
        href="/settings/data-sources"
        className="mt-4 inline-block rounded-md bg-[hsl(var(--terzo-primary))] px-4 py-2 text-sm text-white"
      >
        Add a data source
      </Link>
    </div>
  );
}
