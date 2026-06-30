// Display + derivation helpers ported from the prototype, operating on the /ci/snapshot data.
// Money figures arrive Python-computed; these only format/group/answer — never recompute $.
import type { CiContract, CiOpportunity, CiSnapshot, CiSpend } from "./types";

export const fmt = (n: number) => "$" + Math.round(n || 0).toLocaleString("en-US");
export const fmtK = (n: number) => {
  n = Math.round(n || 0);
  return n >= 1e6 ? "$" + (n / 1e6).toFixed(2) + "M" : "$" + Math.round(n / 100) / 10 + "k";
};
export const pct = (a: number, b: number) => (b ? (a / b) * 100 : 0);
export const esc = (s: unknown) => String(s ?? "");

// Opportunity → icon + action-category (the new dashboard groups actions by these).
const OPP_ICON: Record<string, string> = {
  "Maverick spend": "🧭",
  "Unused commit": "📉",
  "Unused commitment": "📉",
  "Overspend vs ACV": "⚠️",
  "Overspend vs contract": "⚠️",
  "Silent auto-renewal": "🔁",
  "Uplift creep": "📈",
  "Renewal uplift creep": "📈",
  "Spend after expiry": "⌛",
  "Duplicate invoice": "📑",
  "Unclaimed rebate": "🧾",
  "Off-rate billing": "🏷️",
  "License shelfware": "🪑",
};
export const oppIcon = (type: string) => OPP_ICON[type] || "💡";

const OPP_ACT: Record<string, string> = {
  "Maverick spend": "Consolidate suppliers & reduce leakage",
  "Unused commit": "Resolve commitment gaps",
  "Unused commitment": "Resolve commitment gaps",
  "License shelfware": "Resolve commitment gaps",
  "Silent auto-renewal": "Renegotiate contract",
  "Uplift creep": "Renegotiate contract",
  "Renewal uplift creep": "Renegotiate contract",
};
export const oppAct = (type: string) => OPP_ACT[type] || "Recover margin";
export const ACT_CATEGORIES = [
  "Renegotiate contract",
  "Consolidate suppliers & reduce leakage",
  "Recover margin",
  "Resolve commitment gaps",
];
export const actIcon = (cat: string) =>
  ({
    "Renegotiate contract": "🤝",
    "Consolidate suppliers & reduce leakage": "🧭",
    "Recover margin": "💰",
    "Resolve commitment gaps": "🎯",
  })[cat] || "✅";

export const confCls = (c: string) => (c === "high" ? "c-high" : c === "med" ? "c-med" : "c-low");
export const confLbl = (c: string) => (c === "high" ? "High" : c === "med" ? "Medium" : "Low");
export const stCls = (s: string) =>
  s === "recovered" ? "st-rec" : s === "in_progress" ? "st-prog" : "st-open";
export const stLbl = (s: string) =>
  s === "recovered" ? "Recovered" : s === "in_progress" ? "In progress" : "Open";
export const pillCls = (m?: string) =>
  m === "PO" ? "po" : !m || m === "Unmatched" ? "un" : "fz";

// Level-1 taxonomy rollup from the contract category (keyword-based; covers Nexus categories).
export function l1Of(category?: string | null): string {
  const c = (category || "").toLowerCase();
  if (/cloud|software|saas|telecom|network|hardware|cdn|infrastructure|data|it\b/.test(c))
    return "Technology";
  if (/professional|staffing|consult|logistic|security|managed|service/.test(c)) return "Services";
  if (/facilit|office|real estate|admin/.test(c)) return "Facilities & Admin";
  return "Other";
}

export const cById = (snap: CiSnapshot, id?: string | null) =>
  snap.contracts.find((c) => c.id === id) || null;
export const canonVendor = (snap: CiSnapshot, s: CiSpend) =>
  s.resolvedContractId ? cById(snap, s.resolvedContractId)?.vendor || s.vendor : s.vendor;
export const catOf = (snap: CiSnapshot, s: CiSpend) =>
  s.resolvedContractId ? cById(snap, s.resolvedContractId)?.category || "Uncategorised" : "Uncategorised";
export const entityOf = (snap: CiSnapshot, s: CiSpend) =>
  s.resolvedContractId ? cById(snap, s.resolvedContractId)?.entity || "Unassigned" : "Unassigned";

export const sum = (rows: CiSpend[]) => rows.reduce((t, s) => t + (s.amount || 0), 0);
export const byContract = (snap: CiSnapshot, id: string) =>
  snap.spend.filter((s) => s.resolvedContractId === id);

export type BarRow = [string, number];
export const barData = (entries: BarRow[]) => entries.sort((a, b) => b[1] - a[1]);

const LOOKAHEAD = 90;
const today = (snap: CiSnapshot) => new Date(snap.syncedAt || Date.now());
const daysBetween = (a: Date, b: Date) => Math.round((a.getTime() - b.getTime()) / 86400000);

// ── NirvanAI: deterministic answers from the snapshot (ported from the prototype) ──────
export function nirvanaAnswer(snap: CiSnapshot, raw: string): string {
  const q = (raw || "").toLowerCase();
  const opps = snap.opportunities;
  const k = snap.kpis;
  const inDays = (n: number) =>
    snap.contracts.filter((c) => {
      if (!c.end) return false;
      const dd = daysBetween(new Date(c.end), today(snap));
      return dd >= 0 && dd <= n;
    });
  if (q.includes("save the most")) {
    const t = opps.slice(0, 3);
    return (
      "Your three highest-impact opportunities: " +
      t.map((o) => `<b>${o.type} — ${o.subject || ""}</b> (${fmt(o.impact)})`).join("; ") +
      `. Combined ${fmt(t.reduce((a, o) => a + o.impact, 0))}.`
    );
  }
  if (q.includes("auto-renew")) {
    const t = opps.filter((o) => o.type === "Silent auto-renewal");
    return t.length
      ? `${t.length} contract(s) auto-renew within the notice window: ` +
          t.map((o) => `<b>${o.subject}</b> (${fmt(o.impact)})`).join(", ") +
          ". Act before each notice deadline."
      : "No auto-renewals in the current window.";
  }
  if (q.includes("off-contract")) {
    const m = opps.find((o) => o.id === "maverick");
    return m
      ? `${fmt(m.exposure || 0)} of spend is off-contract (${m.subject}). Estimated ${fmt(m.impact)} recoverable at the current recapture rate.`
      : "No off-contract spend detected.";
  }
  if (q.includes("consolidate")) {
    const map: Record<string, Set<string>> = {};
    snap.spend.forEach((s) => {
      const c = catOf(snap, s);
      (map[c] = map[c] || new Set()).add(canonVendor(snap, s));
    });
    const m = Object.entries(map).filter(([, s]) => s.size > 1);
    return m.length
      ? "Consolidation candidates: " +
          m.map(([c, s]) => `<b>${c}</b> (${s.size} vendors)`).join(", ") +
          "."
      : "No multi-vendor categories.";
  }
  if (q.includes("recover")) {
    return `${fmt(k.recoverable)} is recoverable right now — duplicates, post-expiry spend, overspend and unclaimed rebates. See Margin Recovery to package supplier challenges.`;
  }
  if (q.includes("renewal") || q.includes("renew alert")) {
    const t = opps.filter(
      (o) => o.type === "Silent auto-renewal" || o.type === "Uplift creep",
    );
    const e = inDays(LOOKAHEAD);
    return `In the next ${LOOKAHEAD} days, ${e.length} contract(s) reach term and ${t.length} carry renewal exposure (${fmt(t.reduce((a, o) => a + o.impact, 0))} negotiable). Top: ${t[0] ? `<b>${t[0].subject}</b> (${fmt(t[0].impact)})` : "none"}.`;
  }
  if (q.includes("expir")) {
    const e = inDays(90).sort((a, b) => +new Date(a.end!) - +new Date(b.end!));
    return e.length
      ? `${e.length} contract(s) expire within 90 days: ` +
          e.map((c) => `<b>${c.vendor}</b> (${c.end})`).join(", ") +
          "."
      : "No contracts expire within 90 days.";
  }
  if (q.includes("total contract value") || q.includes("tcv")) {
    const tot = snap.contracts.reduce((t, c) => t + (c.contractValue || 0), 0);
    const top = [...snap.contracts].sort((a, b) => (b.contractValue || 0) - (a.contractValue || 0)).slice(0, 3);
    return `Total contract value across ${snap.contracts.length} contracts is ${fmt(tot)}. Largest: ${top.map((c) => `<b>${c.vendor}</b> (${fmt(c.contractValue || 0)})`).join(", ")}.`;
  }
  if (q.includes("commit")) {
    const cc = snap.contracts.filter((c) => c.yearlyCommit != null);
    const tot = cc.reduce((t, c) => t + (c.yearlyCommit || 0), 0);
    return cc.length
      ? `${cc.length} contract(s) carry a yearly commit totalling ${fmt(tot)}. Check Opportunities for under-utilised commits.`
      : "No contracts with yearly commits.";
  }
  return "I answer from your spend and contracts — try: renewal alerts, contracts expiring soon, total contract value, yearly commits, where you can save the most, or what's recoverable.";
}

// ── NirvanAI: document generation (ported from the prototype) ──────────────────────────
export function genDoc(snap: CiSnapshot, type: string, vendor: string): string {
  const c = snap.contracts.find((x) => x.vendor === vendor) || null;
  const opps = snap.opportunities.filter((o) => c && o.contractId === c.id);
  const actual = c
    ? sum(byContract(snap, c.id))
    : sum(snap.spend.filter((s) => canonVendor(snap, s) === vendor));
  const find = (t: string) => opps.find((o) => o.type === t);
  const L: string[] = [];
  const asOf = (snap.syncedAt || "").slice(0, 10);
  const head = () => {
    L.push(`To: ${vendor} — Account Management`);
    L.push("From: Procurement, [Your Company]");
    L.push("Date: " + asOf);
    if (c) L.push(`Re: Contract ${c.id} (${c.category})`);
    L.push("");
  };
  if (type === "Renegotiation email") {
    head();
    L.push(`Dear ${vendor} team,`, "");
    L.push(
      `As part of our annual commercial review, we analysed our spend against ${c ? "contract " + c.id : "our agreement"}. Key findings:`,
    );
    if (c)
      L.push(
        `• Annual value ${fmt(c.acv || 0)}; matched spend ${fmt(actual)}${c.yearlyCommit ? ` against a committed ${fmt(c.yearlyCommit)} (${Math.round(pct(actual, c.yearlyCommit))}% utilised).` : "."}`,
      );
    const un = find("Unused commit");
    if (un) L.push(`• We are tracking ${fmt(un.impact)} below committed volume and would like to right-size.`);
    const ov = find("Overspend vs ACV");
    if (ov) L.push(`• Billing of ${fmt(ov.impact)} above annual value needs a line-item reconciliation.`);
    const rb = find("Unclaimed rebate");
    if (rb) L.push(`• A rebate of ${fmt(rb.impact)} appears unclaimed under the contract terms.`);
    L.push("", `We value the partnership and would like to align on revised terms ahead of the ${c ? c.end : "upcoming"} renewal. Could we schedule a call in the next two weeks?`);
    L.push("", "Best regards,", "[Name], Procurement");
  } else if (type === "Non-renewal notice") {
    head();
    L.push(`Dear ${vendor},`, "");
    const nd = c && c.end ? new Date(new Date(c.end).getTime() - (c.renewalNoticeDays || 0) * 86400000).toISOString().slice(0, 10) : "[deadline]";
    L.push(
      `This letter constitutes formal notice that [Your Company] does not intend to allow ${c ? "contract " + c.id : "our agreement"} to auto-renew on its current terms, effective prior to the notice deadline of ${nd}.`,
    );
    L.push("", "We remain open to continuing on revised commercial terms and welcome a proposal reflecting our current usage and a capped escalation.");
    L.push("", "Regards,", "[Name], Procurement");
  } else if (type === "Supplier challenge letter") {
    head();
    L.push(`Dear ${vendor},`, "");
    const rec = snap.opportunities.filter(
      (o) => o.bucket === "recovery" && ((c && o.contractId === c.id) || o.subject === vendor),
    );
    const tot = rec.reduce((t, o) => t + o.impact, 0);
    L.push(
      `A reconciliation of invoices against ${c ? "contract " + c.id : "our agreement"} identified the following discrepancies totalling ${fmt(tot)}, which we request be credited:`,
    );
    rec.forEach((o) => L.push(`• ${o.type}: ${fmt(o.impact)} — ${o.rationale.replace(/<[^>]+>/g, "")}`));
    if (!rec.length) L.push("• [No recovery items currently detected for this supplier.]");
    L.push("", `Please confirm the credit / refund within ${c?.paymentTermDays || 30} days per our payment terms. Supporting detail is attached.`);
    L.push("", "Regards,", "Accounts Payable, [Your Company]");
  } else if (type === "RFP brief") {
    const cat = c ? c.category : "the category";
    L.push("RFP BRIEF — " + cat, "Date: " + asOf, "");
    L.push(`Objective: competitively source ${cat} spend (~${fmt(actual)}/yr) to reduce cost and improve terms.`);
    L.push(`Incumbent: ${vendor}${c ? ` (contract ${c.id}, annual value ${fmt(c.acv || 0)}, renews ${c.end})` : ""}.`);
    L.push("Scope: full category requirement; pricing on a fixed-rate card with capped, index-referenced escalation.");
    L.push("Evaluation: 50% commercial, 30% capability/SLA, 20% implementation & risk.");
    L.push("Timeline: RFP issue → 2 wks responses → 2 wks evaluation → award. Total 4 weeks.");
  } else if (type === "Supplier SWOT") {
    L.push("SUPPLIER SWOT — " + vendor, "Date: " + asOf, "");
    L.push("STRENGTHS");
    L.push(`• Incumbent with ${c ? `an active contract (${c.id})` : "established spend"}; annual spend ${fmt(actual)}.`);
    L.push("WEAKNESSES");
    opps.forEach((o) => L.push(`• ${o.type} — ${fmt(o.impact)}.`));
    if (!opps.length) L.push("• None detected from current data.");
    L.push("OPPORTUNITIES");
    L.push(`• Renegotiation / consolidation leverage; total identified value ${fmt(opps.reduce((t, o) => t + o.impact, 0))}.`);
    L.push("THREATS");
    L.push(`• ${c && c.renewalType === "Auto-renewal" ? "Auto-renewal lock-in" : "Switching cost"}.`);
    L.push("• Market benchmark unknown (requires external data — out of scope).");
  }
  return L.join("\n");
}
