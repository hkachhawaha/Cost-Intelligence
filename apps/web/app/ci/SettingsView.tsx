"use client";

import { useEffect, useState } from "react";

import { ApiError, apiClient } from "@/lib/api";
import type { CiDataSourceStatus, CiSnapshot } from "@/lib/ci/types";

// Settings → Cost Intelligence → Data Source Configuration. Connect / Test / Refresh / Save
// the Google Sheet that powers the whole app. Restyled to the dashboard design system; the
// underlying integration (connect/test/refresh + status) is unchanged.
export function SettingsView({ onChanged, snap }: { onChanged: () => void; snap?: CiSnapshot }) {
  const [status, setStatus] = useState<CiDataSourceStatus | null>(null);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  async function loadStatus() {
    try {
      const st = await apiClient.get<CiDataSourceStatus>("/ci/data-source");
      setStatus(st);
      setUrl(st.spreadsheet_url || st.default_spreadsheet_url || "");
      setName(st.spreadsheet_name || "");
    } catch {
      /* ignore */
    }
  }
  useEffect(() => {
    loadStatus();
  }, []);

  async function act(label: string, fn: () => Promise<unknown>, reload = true) {
    setBusy(label);
    setMsg(null);
    try {
      const r = (await fn()) as Record<string, unknown>;
      if (label === "Test Connection") {
        const tabs = (r.tabs || {}) as Record<string, number>;
        setMsg({ kind: "ok", text: `Connection OK — ${r.total_rows} rows (${Object.entries(tabs).map(([t, n]) => `${t}: ${n}`).join(" · ")})` });
      } else {
        setMsg({ kind: "ok", text: `${label} succeeded.` });
      }
      await loadStatus();
      if (reload) onChanged();
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof ApiError ? e.detail : `${label} failed` });
    } finally {
      setBusy(null);
    }
  }

  const fmtDate = (x?: string | null) => (x ? new Date(x).toLocaleString() : "—");
  const tag = status?.status === "connected" ? "b-ok" : status?.status === "error" ? "b-exp" : "b-opt";

  return (
    <>
      <div className="card" style={{ maxWidth: 760, marginBottom: 16 }}>
        <div className="sectlbl" style={{ margin: "0 0 4px" }}>🔗 Cost Intelligence — Data Source</div>
        <div className="psub" style={{ margin: "0 0 12px" }}>Connect the Google Sheet that powers contracts, invoices, spend and insights. Share it &ldquo;anyone with the link can view&rdquo;.</div>
        <div className="formrow"><label>Spreadsheet URL</label><input type="text" style={{ width: 360 }} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://docs.google.com/spreadsheets/d/…" /></div>
        <div className="formrow"><label>Spreadsheet name</label><input type="text" style={{ width: 360 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nexus Communications" /></div>
        <div className="formrow"><label>Sync status</label><span className={`badge ${tag}`}>{status?.status || "never"}</span></div>
        <div className="formrow"><label>Last successful sync</label><span className="psub" style={{ margin: 0 }}>{fmtDate(status?.last_synced_at)}</span></div>
        <div className="formrow"><label>Total records processed</label><span className="psub" style={{ margin: 0 }}>{status?.total_records ?? 0}</span></div>
        {status?.last_error && <div className="alert a-r" style={{ marginTop: 8 }}><div className="ai">⚠</div><div>{status.last_error}</div></div>}
        <div className="linkrow" style={{ marginTop: 14 }}>
          <button className="btn" disabled={!!busy} onClick={() => act("Test Connection", () => apiClient.post("/ci/data-source/test", { url }), false)}>{busy === "Test Connection" ? "Testing…" : "Test Connection"}</button>
          <button className="btn p" disabled={!!busy} onClick={() => act("Connect Spreadsheet", () => apiClient.post("/ci/data-source/connect", { url, name }))}>{busy === "Connect Spreadsheet" ? "Connecting…" : "Connect Spreadsheet"}</button>
          <button className="btn" disabled={!!busy || !status?.connected} onClick={() => act("Refresh Data", () => apiClient.post("/ci/data-source/refresh", {}))}>{busy === "Refresh Data" ? "Refreshing…" : "Refresh Data"}</button>
          <button className="btn" disabled={!!busy} onClick={() => act("Save Configuration", () => apiClient.post("/ci/data-source/connect", { url, name }))}>{busy === "Save Configuration" ? "Saving…" : "Save Configuration"}</button>
        </div>
        {msg && <div className={`alert ${msg.kind === "ok" ? "a-g" : "a-r"}`} style={{ marginTop: 12 }}><div className="ai">{msg.kind === "ok" ? "✓" : "⚠"}</div><div>{msg.text}</div></div>}
        <div className="psub" style={{ margin: "12px 0 0" }}>On Connect/Refresh the agent reads every sheet, links contracts ↔ invoices ↔ spend, generates Cost Intelligence insights, and stores them in Agent Memory. The app runs from memory until you Refresh.</div>
      </div>

      {snap && (
        <div className="card" style={{ maxWidth: 760 }}>
          <div className="sectlbl" style={{ margin: "0 0 4px" }}>🧠 Agent Memory</div>
          <div className="psub" style={{ margin: "0 0 10px" }}>Current snapshot in memory (read by every view and NirvanaI).</div>
          <div className="kv"><span>Memory version</span><b>v{snap.version}</b></div>
          <div className="kv"><span>Records in memory</span><b>{snap.contracts.length} contracts · {snap.invoices.length} invoices · {snap.purchaseOrders.length} POs · {snap.spend.length} spend · {snap.clauses.length} clauses · {snap.inventory.length} inventory</b></div>
          <div className="kv"><span>Opportunities generated</span><b>{snap.opportunities.length}</b></div>
        </div>
      )}
    </>
  );
}
