import { accessToken } from "@/lib/auth";
import { apiFetch } from "@/lib/api";

interface DataSource {
  id: string;
  name: string;
  source_type: string;
  status: string;
  last_synced_at: string | null;
  last_error: string | null;
}

// Server component: lists the tenant's data sources with sync status.
// Add-source + OAuth connect + quarantine review are wired as client islands
// in the full build; Phase 1 ships the list + status surface.
export default async function DataSourcesPage() {
  let sources: DataSource[] = [];
  let error: string | null = null;
  try {
    const token = await accessToken();
    sources = await apiFetch<DataSource[]>("/data-sources", { token } as RequestInit & {
      token?: string;
    });
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load data sources";
  }

  return (
    <section>
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Data Sources</h1>
        <p className="mt-1 text-sm text-slate-500">
          Connect Google Sheets to ingest Contracts, Invoices, and Spend.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <ul className="space-y-3">
        {sources.map((s) => (
          <li
            key={s.id}
            className="flex items-center justify-between rounded-md border p-4"
          >
            <div>
              <div className="font-medium">{s.name}</div>
              <div className="text-xs text-slate-500">
                {s.source_type} · {s.status}
                {s.last_synced_at
                  ? ` · synced ${new Date(s.last_synced_at).toLocaleString()}`
                  : " · never synced"}
              </div>
              {s.last_error && (
                <div className="mt-1 text-xs text-red-600">{s.last_error}</div>
              )}
            </div>
            <a
              href={`/api/data-sources/${s.id}/refresh`}
              className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-brand-fg"
            >
              Refresh
            </a>
          </li>
        ))}
        {sources.length === 0 && !error && (
          <li className="rounded-md border border-dashed p-6 text-center text-sm text-slate-500">
            No data sources yet. Add a Google Sheet to begin.
          </li>
        )}
      </ul>
    </section>
  );
}
