// UI validation for the dashboard realignment — renders each view server-side (node env) with
// an injected Agent Memory snapshot and asserts the new dashboard layout, widgets and hubs
// against Designs/Terzo-Cost-Intelligence-Dashboard.html.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CiSnapshot } from "@/lib/ci/types";

import { CostIntelligenceApp } from "./CostIntelligenceApp";

const SNAP: CiSnapshot = {
  version: 1,
  syncedAt: "2025-07-01T09:00:00Z",
  spreadsheetName: "Nexus",
  totalRecords: 12,
  invoices: [{ id: "INV-1", contractId: "NXC-1" }, { id: "INV-2", contractId: "NXC-2" }],
  purchaseOrders: [{ poNumber: "PO-1", contractId: "NXC-1" }],
  inventory: [],
  clauses: [],
  relationships: { counts: { contracts: 2, spend: 4, invoices: 2, maverickRecords: 1 } },
  contracts: [
    { id: "NXC-1", vendor: "Acme Cloud", category: "Cloud & Infrastructure", region: "Global",
      entity: "Global", acv: 200000, contractValue: 600000, start: "2024-07-01", end: "2025-07-15",
      renewalNoticeDays: 30, autoRenew: true, renewalType: "Auto-renewal", rebateClause: true,
      slaPenaltyClause: false, status: "Active", paymentTermDays: 30, yearlyCommit: 240000,
      department: "IT", paymentTerms: "Net-30" },
    { id: "NXC-2", vendor: "Globex Telecom", category: "Telecom", region: "EU", entity: "EU",
      acv: 100000, contractValue: 200000, start: "2023-01-01", end: "2026-01-01",
      renewalNoticeDays: 60, autoRenew: false, renewalType: "Option", rebateClause: false,
      slaPenaltyClause: false, status: "Active", paymentTermDays: 30, department: "Network" },
  ],
  spend: [
    { id: "T1", vendor: "Acme Cloud", resolvedContractId: "NXC-1", contractId: "NXC-1", po: "PO-1",
      amount: 260000, spendDate: "2025-03-01", matchMethod: "Contract ID", matchConfidence: 0.97, costCenter: "CC-1", invoiceRef: "INV-1" },
    { id: "T2", vendor: "Globex Telecom", resolvedContractId: "NXC-2", contractId: "NXC-2",
      amount: 80000, spendDate: "2025-04-06", matchMethod: "Contract ID", matchConfidence: 0.97, costCenter: "CC-2", invoiceRef: "INV-2" },
    { id: "T3", vendor: "Rogue Vendor", resolvedContractId: null, amount: 50000, spendDate: "2025-05-07",
      matchMethod: "Unmatched", matchConfidence: 0, costCenter: "CC-9" },
  ],
  opportunities: [
    { id: "overspend:NXC-1", type: "Overspend vs ACV", tag: "Overspend", subject: "Acme Cloud",
      contractId: "NXC-1", impact: 60000, confidence: 0.85, conf: "high", bucket: "recovery",
      status: "open", score: 51000, rationale: "Paid <b>$260,000</b> vs ACV $200,000.",
      formula: "Overage = Actual − ACV", action: "Audit the overage.", evidence: [] },
    { id: "autorenew:NXC-1", type: "Silent auto-renewal", tag: "Auto-renewal", subject: "Acme Cloud",
      contractId: "NXC-1", impact: 10000, confidence: 0.9, conf: "high", bucket: "savings",
      status: "open", score: 9000, rationale: "Auto-renews soon.", formula: "ACV × uplift",
      action: "Send notice.", evidence: [] },
    { id: "dup:INV-9", type: "Duplicate invoice", tag: "Duplicate", subject: "Globex Telecom",
      contractId: "NXC-2", impact: 5000, confidence: 0.82, conf: "high", bucket: "recovery",
      status: "open", score: 4100, rationale: "Paid twice.", formula: "amount × 1", action: "Debit memo.", evidence: [] },
    { id: "maverick", type: "Maverick spend", tag: "Off-contract", subject: "1 vendor", impact: 5000,
      exposure: 50000, confidence: 0.78, conf: "med", bucket: "savings", status: "open", score: 3900,
      rationale: "Off-contract spend.", formula: "Σ unmatched", action: "Consolidate.", evidence: [] },
  ],
  kpis: {
    total: 390000, matched: 340000, po: 340000, maverick: 50000, identified: 80000, recovered: 0,
    recoverable: 65000, savings: 15000, oppCount: 4, spendUnderMgmtPct: 87.2, compliancePct: 87.2,
    poCoveragePct: 66.7, recordCounts: { maverickRecords: 1 },
  },
};

const view = (tab: string) => renderToStaticMarkup(<CostIntelligenceApp initialSnapshot={SNAP} initialTab={tab} />);

describe("Dashboard realignment — new layout from Terzo-Cost-Intelligence-Dashboard.html", () => {
  it("Home: hero 'found money', spend-under-management ring, off-contract, top actions, donut, alerts", () => {
    const h = view("home");
    expect(h).toContain("We found money across your spend");
    expect(h).toContain("Spend under management");
    expect(h).toContain("Off-contract exposure");
    expect(h).toContain("Top things to act on");
    expect(h).toContain("Where your money goes");
    expect(h).toContain("Needs your attention");
    expect(h).toContain("auto-renews soon"); // alert
  });

  it("Opportunities: filter chips + ranked opportunity cards", () => {
    const h = view("opps");
    expect(h).toContain("Recover now");
    expect(h).toContain("Future savings");
    expect(h).toContain("Overspend vs ACV");
    expect(h).toContain("recover now"); // recovery card label
  });

  it("Analyze hub: AI insights + spend trend + supplier performance + utilisation + variance", () => {
    const h = view("analyze");
    expect(h).toContain("AI-generated insights");
    expect(h).toContain("Spend trend");
    expect(h).toContain("Supplier performance");
    expect(h).toContain("Contract utilisation");
    expect(h).toContain("Variance vs contract");
  });

  it("Spend: under-contract ring, off-contract, by-category and top-vendor widgets", () => {
    const h = view("spend");
    expect(h).toContain("Under contract");
    expect(h).toContain("Off-contract");
    expect(h).toContain("By category");
    expect(h).toContain("Top vendors");
  });

  it("Contracts: card grid with utilisation + a drill-down affordance", () => {
    const h = view("contracts");
    expect(h).toContain("Acme Cloud");
    expect(h).toContain("under management");
    expect(h).toContain("View details");
  });

  it("Vendors: concentration KPIs + per-vendor risk cards", () => {
    const h = view("vendors");
    expect(h).toContain("Top-3 concentration");
    expect(h).toContain("Acme Cloud");
    expect(h).toContain("Concentration");
  });

  it("Act hub: actions grouped by recommended action category", () => {
    const h = view("act");
    expect(h).toContain("Actions to take");
    expect(h).toContain("Recover margin"); // an action category
  });

  it("Margin Recovery: recoverable totals grouped by vendor + draft challenge letter", () => {
    const h = view("recovery");
    expect(h).toContain("Total recoverable");
    expect(h).toContain("Draft challenge letter");
  });

  it("Commitments: utilisation rings + commitment KPIs", () => {
    const h = view("commitments");
    expect(h).toContain("Total commitments");
    expect(h).toContain("Compliance");
  });

  it("Intelligence hub: NirvanaI copilot hero + findings + recommendations", () => {
    const h = view("intelligence");
    expect(h).toContain("your cost-intelligence copilot");
    expect(h).toContain("AI findings");
    expect(h).toContain("Top recommendations");
  });

  it("Portfolio: spend-by-entity + group mix + entity scorecard", () => {
    const h = view("portfolio");
    expect(h).toContain("Spend by entity");
    expect(h).toContain("Group spend mix");
    expect(h).toContain("Entity scorecard");
  });

  it("Data Quality: match coverage + unmatched queue (maverick surfaced)", () => {
    const h = view("quality");
    expect(h).toContain("Match coverage");
    expect(h).toContain("Unmatched queue");
    expect(h).toContain("Rogue Vendor");
  });

  it("Sidebar: 5 nav groups + Ask NirvanaI button", () => {
    const h = view("home");
    for (const g of ["Overview", "Analyze", "Act", "Intelligence", "System"]) expect(h).toContain(g);
    for (const t of ["Home", "Opportunities", "Spend", "Contracts", "Vendors", "Margin Recovery", "Commitment Check", "Settings"]) expect(h).toContain(t);
    expect(h).toContain("Ask NirvanaI");
  });
});
