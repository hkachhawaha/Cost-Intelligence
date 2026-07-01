"use client";

import { useEffect, useState } from "react";

import { ApiError, apiClient } from "@/lib/api";
import type { CiDataSourceStatus, CiSnapshot } from "@/lib/ci/types";

interface LlmProvider {
  name: string;
  active: boolean;
  status: string;
  models: {
    alias: string;
    model: string;
    useCase: string;
    costPerMillion: { input: string; output: string };
  }[];
}

export function SettingsView({ onChanged, snap }: { onChanged: () => void; snap?: CiSnapshot }) {
  const [activeTab, setActiveTab] = useState<"data-source" | "llm" | "cost">("data-source");
  const [status, setStatus] = useState<CiDataSourceStatus | null>(null);
  const [providers, setProviders] = useState<LlmProvider[]>([]);
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

  async function loadLlmProviders() {
    try {
      const res = await apiClient.get<{ providers: LlmProvider[] }>("/ci/settings/llm-providers");
      setProviders(res.providers);
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    loadStatus();
    loadLlmProviders();
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
      setMsg({ kind: "err", text: e instanceof ApiError ? e.detail : (e instanceof Error ? e.message : `${label} failed`) });
    } finally {
      setBusy(null);
    }
  }

  const fmtDate = (x?: string | null) => (x ? new Date(x).toLocaleString() : "—");
  const tag = status?.status === "connected" ? "b-ok" : status?.status === "error" ? "b-exp" : "b-opt";

  return (
    <div style={{ maxWidth: 760 }}>
      {/* Premium Tab Navigation */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, borderBottom: "1px solid var(--line)", paddingBottom: 10 }}>
        <button
          className={`btn ${activeTab === "data-source" ? "p" : ""}`}
          style={{ background: activeTab === "data-source" ? undefined : "transparent", color: activeTab === "data-source" ? undefined : "var(--muted)", cursor: "pointer" }}
          onClick={() => setActiveTab("data-source")}
        >
          🔗 Data Source
        </button>
        <button
          className={`btn ${activeTab === "llm" ? "p" : ""}`}
          style={{ background: activeTab === "llm" ? undefined : "transparent", color: activeTab === "llm" ? undefined : "var(--muted)", cursor: "pointer" }}
          onClick={() => setActiveTab("llm")}
        >
          🤖 LLM Providers
        </button>
        <button
          className={`btn ${activeTab === "cost" ? "p" : ""}`}
          style={{ background: activeTab === "cost" ? undefined : "transparent", color: activeTab === "cost" ? undefined : "var(--muted)", cursor: "pointer" }}
          onClick={() => setActiveTab("cost")}
        >
          📊 Cost Breakdown
        </button>
      </div>

      {activeTab === "data-source" && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
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
            <div className="card">
              <div className="sectlbl" style={{ margin: "0 0 4px" }}>🧠 Agent Memory</div>
              <div className="psub" style={{ margin: "0 0 10px" }}>Current snapshot in memory (read by every view and NirvanaI).</div>
              <div className="kv"><span>Memory version</span><b>v{snap.version}</b></div>
              <div className="kv"><span>Records in memory</span><b>{snap.contracts.length} contracts · {snap.invoices.length} invoices · {snap.purchaseOrders.length} POs · {snap.spend.length} spend · {snap.clauses.length} clauses · {snap.inventory.length} inventory</b></div>
              <div className="kv"><span>Opportunities generated</span><b>{snap.opportunities.length}</b></div>
            </div>
          )}
        </>
      )}

      {activeTab === "llm" && (
        <div className="card">
          <div className="sectlbl" style={{ margin: "0 0 4px" }}>🤖 LLM Provider Settings</div>
          <div className="psub" style={{ margin: "0 0 12px" }}>Active foundation model configurations mapped in the Model Gateway.</div>
          
          {providers.map((provider) => (
            <div key={provider.name} style={{ marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                <h3 style={{ fontSize: 16, fontWeight: 700 }}>{provider.name}</h3>
                <span className={`badge ${provider.active ? "b-ok" : "b-exp"}`}>
                  {provider.status}
                </span>
              </div>
              
              <table className="ltable" style={{ width: "100%", fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Alias</th>
                    <th style={{ textAlign: "left" }}>Model Pinned</th>
                    <th style={{ textAlign: "left" }}>Use Case</th>
                    <th style={{ textAlign: "right" }}>Cost / 1M Input</th>
                    <th style={{ textAlign: "right" }}>Cost / 1M Output</th>
                  </tr>
                </thead>
                <tbody>
                  {provider.models.map((m) => (
                    <tr key={m.alias}>
                      <td style={{ fontWeight: 600 }}>{m.alias}</td>
                      <td style={{ fontFamily: "monospace", color: "var(--purple-d)" }}>{m.model}</td>
                      <td>{m.useCase}</td>
                      <td style={{ textAlign: "right" }}>{m.costPerMillion.input}</td>
                      <td style={{ textAlign: "right" }}>{m.costPerMillion.output}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {providers.length === 0 && (
            <p className="psub" style={{ textAlign: "center", padding: "10px 0" }}>Loading provider settings...</p>
          )}
        </div>
      )}

      {activeTab === "cost" && (
        <div className="card">
          <div className="sectlbl" style={{ margin: "0 0 4px" }}>📊 Operational Cost Breakdown</div>
          <div className="psub" style={{ margin: "0 0 16px" }}>Detailed monthly cost breakdown of the current Supabase + Render production hosting.</div>
          
          <table className="ltable" style={{ width: "100%", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Service Provider</th>
                <th style={{ textAlign: "left" }}>Component</th>
                <th style={{ textAlign: "left" }}>Tier / Size</th>
                <th style={{ textAlign: "right" }}>Estimated Monthly Cost</th>
                <th style={{ textAlign: "left" }}>Notes</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ fontWeight: 600 }}>Vercel</td>
                <td>Next.js Frontend</td>
                <td>Hobby (Free)</td>
                <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green)" }}>$0.00</td>
                <td>100GB bandwidth, serverless functions, Edge CDN</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Render</td>
                <td>FastAPI Backend</td>
                <td>Free Tier</td>
                <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green)" }}>$0.00</td>
                <td>750 hrs/mo, spins down after 15min inactivity</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Supabase</td>
                <td>Database &amp; Auth</td>
                <td>Free Tier</td>
                <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green)" }}>$0.00</td>
                <td>500MB Postgres (pgvector) + GoTrue Auth</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Upstash</td>
                <td>Redis Cache</td>
                <td>Serverless Free Tier</td>
                <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green)" }}>$0.00</td>
                <td>10K commands/day, transient cache &amp; queue</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Google Gemini</td>
                <td>Gemini API</td>
                <td>Free Tier</td>
                <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green)" }}>$0.00</td>
                <td>15 RPM (Pro) / 30 RPM (Flash), generous free quota</td>
              </tr>
              <tr style={{ borderTop: "2px solid var(--line)" }}>
                <td colSpan={3} style={{ fontWeight: 800, fontSize: 14 }}>Total Monthly Cost</td>
                <td style={{ textAlign: "right", fontWeight: 800, fontSize: 14, color: "var(--green)" }}>$0.00</td>
                <td style={{ fontWeight: 600 }}>100% free tier — no paid plans active</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
