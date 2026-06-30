import { describe, expect, it } from "vitest";

import { fmt, genDoc, l1Of, nirvanaAnswer } from "./compute";
import type { CiSnapshot } from "./types";

const SNAP: CiSnapshot = {
  version: 1,
  syncedAt: "2025-07-01T00:00:00Z",
  spreadsheetName: "Test",
  totalRecords: 3,
  invoices: [],
  purchaseOrders: [],
  inventory: [],
  clauses: [],
  relationships: { counts: {} },
  contracts: [
    {
      id: "NXC-1", vendor: "Acme Cloud", category: "Cloud & Infrastructure", entity: "Global",
      acv: 200000, contractValue: 600000, end: "2025-07-15", renewalNoticeDays: 30,
      autoRenew: true, renewalType: "Auto-renewal", rebateClause: true, slaPenaltyClause: false,
      status: "Active", paymentTermDays: 30,
    },
  ],
  spend: [
    { id: "T1", vendor: "Acme Cloud", resolvedContractId: "NXC-1", amount: 260000, matchMethod: "Contract ID" },
    { id: "T2", vendor: "Rogue Vendor", resolvedContractId: null, amount: 50000, matchMethod: "Unmatched" },
  ],
  opportunities: [
    {
      id: "overspend:NXC-1", type: "Overspend vs ACV", tag: "Overspend", subject: "Acme Cloud",
      contractId: "NXC-1", impact: 60000, confidence: 0.85, conf: "high", bucket: "recovery",
      status: "open", score: 51000, rationale: "Matched spend exceeds ACV.", formula: "x", action: "Audit.",
      evidence: [],
    },
    {
      id: "maverick", type: "Maverick spend", tag: "Off-contract", subject: "1 vendor",
      impact: 5000, exposure: 50000, confidence: 0.78, conf: "med", bucket: "savings",
      status: "open", score: 3900, rationale: "Off-contract.", formula: "x", action: "Consolidate.",
      evidence: [],
    },
    {
      id: "autorenew:NXC-1", type: "Silent auto-renewal", tag: "Auto-renewal", subject: "Acme Cloud",
      contractId: "NXC-1", impact: 10000, confidence: 0.9, conf: "high", bucket: "savings",
      status: "open", score: 9000, rationale: "Auto-renews soon.", formula: "x", action: "Notice.",
      evidence: [],
    },
  ],
  kpis: {
    total: 310000, matched: 260000, po: 0, maverick: 50000, identified: 65000, recovered: 0,
    recoverable: 60000, savings: 5000, oppCount: 2, spendUnderMgmtPct: 83.9, compliancePct: 0,
    poCoveragePct: 50, recordCounts: {},
  },
};

describe("nirvanaAnswer (deterministic, from memory)", () => {
  it("answers 'save the most' with the top opportunities", () => {
    const a = nirvanaAnswer(SNAP, "Where can I save the most?");
    expect(a).toContain("Overspend vs ACV");
    expect(a).toContain(fmt(60000));
  });

  it("answers 'recoverable' with the recoverable figure", () => {
    const a = nirvanaAnswer(SNAP, "What is recoverable right now?");
    expect(a).toContain(fmt(60000));
  });

  it("answers 'auto-renew' referencing the at-risk contract", () => {
    const a = nirvanaAnswer(SNAP, "What auto-renews soon?");
    expect(a.toLowerCase()).toContain("acme cloud");
  });

  it("falls back gracefully on an unknown question", () => {
    expect(nirvanaAnswer(SNAP, "weather?")).toContain("I answer from your spend and contracts");
  });
});

describe("genDoc (first-party document generation)", () => {
  it("drafts a supplier challenge letter citing recovery items", () => {
    const doc = genDoc(SNAP, "Supplier challenge letter", "Acme Cloud");
    expect(doc).toContain("Acme Cloud");
    expect(doc).toContain("Overspend vs ACV");
    expect(doc).toContain(fmt(60000));
  });

  it("drafts a renegotiation email referencing the contract", () => {
    const doc = genDoc(SNAP, "Renegotiation email", "Acme Cloud");
    expect(doc).toContain("Contract NXC-1");
    expect(doc).toContain(fmt(200000)); // ACV
  });
});

describe("l1Of taxonomy", () => {
  it("rolls categories up to a Level-1 group", () => {
    expect(l1Of("Cloud & Infrastructure")).toBe("Technology");
    expect(l1Of("Professional Services")).toBe("Services");
    expect(l1Of("Office Supplies")).toBe("Facilities & Admin");
  });
});
