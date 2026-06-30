// Shapes of the /ci/snapshot Agent Memory payload (mirrors apps/api/app/cost_intelligence).
export interface CiContract {
  id: string;
  vendor: string;
  category: string;
  subcategory?: string | null;
  region?: string | null;
  entity?: string | null;
  contractValue?: number | null;
  acv?: number | null;
  start?: string | null;
  end?: string | null;
  renewalNoticeDays: number;
  autoRenew: boolean;
  renewalType: string;
  pricingModel?: string | null;
  paymentTerms?: string | null;
  paymentTermDays?: number | null;
  rebateClause: boolean;
  slaPenaltyClause: boolean;
  volumeCommitmentRaw?: string | null;
  yearlyCommit?: number | null;
  owner?: string | null;
  department?: string | null;
  status: string;
}

export interface CiSpend {
  id: string;
  spendDate?: string | null;
  vendor: string;
  contractId?: string | null;
  po?: string | null;
  costCenter?: string | null;
  department?: string | null;
  gl?: string | null;
  description?: string | null;
  amount: number;
  invoiceRef?: string | null;
  fiscalQuarter?: string | null;
  resolvedContractId?: string | null;
  matchMethod?: string;
  matchConfidence?: number;
}

export interface CiOpportunity {
  id: string;
  type: string;
  tag: string;
  subject?: string | null;
  contractId?: string | null;
  impact: number;
  exposure?: number;
  confidence: number;
  conf: "high" | "med" | "low";
  rationale: string;
  formula: string;
  action: string;
  evidence: CiSpend[];
  bucket: "savings" | "recovery";
  status: string;
  score: number;
}

export interface CiKpis {
  total: number;
  matched: number;
  po: number;
  maverick: number;
  identified: number;
  recovered: number;
  recoverable: number;
  savings: number;
  oppCount: number;
  spendUnderMgmtPct: number;
  compliancePct: number;
  poCoveragePct: number;
  recordCounts: Record<string, number>;
}

export interface CiSnapshot {
  version: number;
  syncedAt: string;
  spreadsheetName?: string | null;
  totalRecords: number;
  contracts: CiContract[];
  invoices: Record<string, unknown>[];
  purchaseOrders: Record<string, unknown>[];
  inventory: Record<string, unknown>[];
  clauses: Record<string, unknown>[];
  spend: CiSpend[];
  relationships: { counts: Record<string, number>; [k: string]: unknown };
  opportunities: CiOpportunity[];
  kpis: CiKpis;
}

export interface CiDataSourceStatus {
  connected: boolean;
  status: string;
  spreadsheet_url?: string;
  spreadsheet_name?: string | null;
  last_synced_at?: string | null;
  total_records?: number;
  last_error?: string | null;
  default_spreadsheet_url?: string;
}
