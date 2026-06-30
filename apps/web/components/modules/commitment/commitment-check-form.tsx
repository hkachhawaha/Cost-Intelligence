"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, apiClient } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type { CommitmentVerdictView } from "@/lib/types";

// Deal input → deterministic stress test → advisory verdict + sign-off. All $ figures are
// Python-computed upstream; this component only displays them and records a human decision.
const VERDICT_TONE: Record<string, "default" | "muted" | "warning"> = {
  approve: "default",
  condition: "warning",
  block: "warning",
};

const FIELDS = [
  { key: "vendor_name", label: "Vendor", type: "text", placeholder: "CloudCo" },
  { key: "acv", label: "ACV ($)", type: "number", placeholder: "1200000" },
  { key: "term_months", label: "Term (months)", type: "number", placeholder: "36" },
  { key: "indexed_share", label: "Indexed share (0–1)", type: "number", placeholder: "0.60" },
  { key: "assumed_index_pct", label: "Assumed index % (e.g. 0.03)", type: "number", placeholder: "0.03" },
  { key: "margin_tolerance", label: "Margin tolerance ($)", type: "number", placeholder: "800000" },
] as const;

export function CommitmentCheckForm() {
  const [form, setForm] = useState<Record<string, string>>({});
  const [verdict, setVerdict] = useState<CommitmentVerdictView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { ...form };
      if (!payload.term_months) delete payload.term_months;
      const v = await apiClient.post<CommitmentVerdictView>("/commitment-check", payload);
      setVerdict(v);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "stress test failed");
    } finally {
      setBusy(false);
    }
  }

  async function sign(decision: "accepted" | "declined") {
    if (!verdict) return;
    try {
      const v = await apiClient.post<CommitmentVerdictView>(
        `/commitment-check/${verdict.id}/sign`,
        { decision },
      );
      setVerdict(v);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "sign-off failed");
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <div className="space-y-3 rounded-lg border p-4">
        <h2 className="text-sm font-semibold">Proposed deal</h2>
        {FIELDS.map((f) => (
          <label key={f.key} className="block text-xs text-muted-foreground">
            {f.label}
            <input
              type={f.type}
              step="any"
              placeholder={f.placeholder}
              value={form[f.key] ?? ""}
              onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
              className="mt-1 w-full rounded border px-2 py-1 text-sm text-foreground"
            />
          </label>
        ))}
        <Button size="sm" disabled={busy} onClick={run}>
          {busy ? "Running…" : "Run stress test"}
        </Button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      <div className="space-y-3 rounded-lg border p-4">
        <h2 className="text-sm font-semibold">Verdict</h2>
        {!verdict ? (
          <p className="text-sm text-muted-foreground">Run a stress test to see the verdict.</p>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Badge variant={VERDICT_TONE[verdict.verdict]}>{verdict.verdict.toUpperCase()}</Badge>
              {verdict.advisory && <span className="text-xs text-muted-foreground">advisory</span>}
            </div>
            <p className="text-xs text-muted-foreground">
              Baseline indexed exposure:{" "}
              <strong className="text-foreground">{formatUsd(verdict.indexed_exposure)}</strong>
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="py-1">Adverse move</th>
                  <th className="text-right">Exposure</th>
                  <th className="text-right">Over tolerance</th>
                </tr>
              </thead>
              <tbody>
                {verdict.scenarios.map((s) => (
                  <tr key={s.move_pct} className="border-t">
                    <td className="py-1">+{s.move_pct}%</td>
                    <td className="text-right tabular-nums">{formatUsd(s.exposure)}</td>
                    <td className="text-right">{s.over_tolerance ? "⚠️ yes" : "ok"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {verdict.conditions.length > 0 && (
              <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                {verdict.conditions.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            )}
            {verdict.rationale && (
              <p className="text-xs text-muted-foreground">{verdict.rationale}</p>
            )}
            {verdict.signed_at ? (
              <p className="text-xs">
                Signed: <strong>{verdict.signed_decision}</strong>
              </p>
            ) : (
              <div className="flex gap-2">
                <Button size="sm" onClick={() => sign("accepted")}>
                  Sign &amp; accept
                </Button>
                <Button size="sm" variant="outline" onClick={() => sign("declined")}>
                  Decline
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
