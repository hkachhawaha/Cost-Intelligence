// Generated-by-hand mirror of the Phase-5 Pydantic response schemas
// (apps/api/app/schemas/read_models.py). Money arrives as strings (Decimal upstream).

export interface DashboardKpis {
  initialized: boolean;
  stale: boolean;
  last_synced_at: string | null;
  memory_version: number | null;
  total_spend: string;
  spend_under_management_pct: string;
  contract_compliance_pct: string;
  po_coverage_pct: string;
  match_coverage_pct: string;
  total_savings: string;
  total_recovery: string;
  total_identified: string;
  opportunity_count_by_type: Record<string, number>;
  opportunity_amount_by_type: Record<string, string>;
  top_opportunities: OpportunityOut[];
  alerts: Alert[];
}

export interface Alert {
  kind: string;
  severity: string;
  contract_id?: string;
  opportunity_id?: string;
  notice_deadline?: string;
  impact?: string;
}

export interface SpendBreakdownItem {
  label: string;
  amount: string;
}
export interface SpendBreakdownResponse {
  dimension: string;
  items: SpendBreakdownItem[];
}
export interface SpendTrendPoint {
  month: string;
  amount: string;
}
export interface MatchCoverageResponse {
  po_exact: number;
  vendor_amount_date: number;
  ai_inferred: number;
  unmatched: number;
  coverage_pct: string;
}

export interface ContractSummary {
  id: string;
  vendor_id: string;
  acv: string | null;
  tcv: string | null;
  start_date: string | null;
  end_date: string | null;
  renewal_type: string | null;
  status: string;
  indexation: { index_type: string | null; indexed_share: string; has_indexation: boolean };
}
export interface ContractListResponse {
  items: ContractSummary[];
  total: number;
  page: number;
  page_size: number;
}
export interface ContractDetail extends ContractSummary {
  effective_date: string | null;
  renewal_notice_days: number | null;
  uplift_pct: string;
  yearly_commit: string;
  payment_term_days: number | null;
  currency: string;
  po_numbers: string[];
  source_system: string;
}
export interface ContractSpendLine {
  spend_id: string;
  amount: string;
  spend_date: string;
  po_number: string | null;
}
export interface ContractSpendResponse {
  contract_id: string;
  total_matched_spend: string;
  utilization_pct: string;
  lines: ContractSpendLine[];
}

export interface RenewalEntry {
  contract_id: string;
  vendor_id: string;
  end_date: string;
  days_to_end: number;
  renewal_type: string | null;
  notice_deadline: string;
  acv: string | null;
}
export interface RenewalsResponse {
  within_90: RenewalEntry[];
  within_180: RenewalEntry[];
  within_365: RenewalEntry[];
}

export interface RecoveryItemOut {
  rec_id: string;
  opp_id: string;
  amount: string;
  status: string;
  evidence: Record<string, unknown> & { formula?: string };
}
export interface RecoveryPack {
  vendor_id: string;
  total: string;
  items: RecoveryItemOut[];
}
export interface RecoveryPacksResponse {
  packs: RecoveryPack[];
}

export interface DataQualityCoverage {
  low_confidence_matches: number;
  unmatched_count: number;
  match_coverage_pct: string;
}
export interface DataQualityEvent {
  id: string;
  event_type: string;
  detail: Record<string, unknown>;
  created_at: string;
}
export interface DataQualityEventsResponse {
  items: DataQualityEvent[];
}

export interface OpportunityOut {
  id: string;
  contract_id: string | null;
  type: string;
  bucket: string;
  impact: string;
  confidence: string;
  status: string;
  owner_id?: string | null;
  rationale?: string | null;
}
export interface OpportunityListResponse {
  items: OpportunityOut[];
  total: number;
  page: number;
  page_size: number;
  totals?: Record<string, string>;
}

export interface SyncStatus {
  initialized: boolean;
  status: string | null;
  stage: string | null;
  stale: boolean;
  last_synced_at: string | null;
  memory_version: number | null;
}

// ── Phase 6 — NirvanaI ───────────────────────────────────────────────────────
export interface NirvanaCitation {
  type: string;
  record_id: string;
  label: string;
  figure: string | null;
}

export interface NirvanaChatResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  intent: string;
  grounded: boolean;
  citations: NirvanaCitation[];
  latency_ms: number | null;
}

export interface NirvanaDraft {
  draft_id: string;
  template: string;
  title: string;
  body_markdown: string;
  citations: NirvanaCitation[];
  status: string;
  editable: boolean;
}

export interface ChatUiMessage {
  role: "user" | "assistant";
  content: string;
  grounded?: boolean;
  citations?: NirvanaCitation[];
}

// ── Phase 7 — Advanced modules ───────────────────────────────────────────────
export interface VendorRollup {
  vendor_id: string;
  name: string;
  total_spend: string;
  total_acv: string;
  contract_count: number;
  matched_spend_pct: string;
}
export interface VendorListResponse {
  vendors: VendorRollup[];
}

export interface ConsolidationCandidate {
  scope: string;
  key: string;
  label: string;
  vendor_count: number;
  contract_count: number;
  total_spend: string;
  fragmentation_score: string;
  rationale: Record<string, unknown>;
}
export interface ConsolidationResponse {
  candidates: ConsolidationCandidate[];
}

export interface ExposureLine {
  contract_id: string;
  vendor_name: string;
  acv: string;
  index_type: string;
  indexed_share: string;
  indexed_exposure: string;
  formula: string;
}
export interface ExposureResponse {
  assumed_move_pct: string;
  total_indexed_exposure: string;
  note: string;
  lines: ExposureLine[];
}

export interface EntityRollup {
  entity_id: string;
  entity_name: string;
  total_spend: string;
  spend_under_management_pct: string;
  identified_savings: string;
  identified_recovery: string;
}
export interface PortfolioResponse {
  entities: EntityRollup[];
}

export interface ExtractionItem {
  id: string;
  contract_id: string | null;
  status: string;
  extracted_fields: Record<string, unknown>;
  extracted_clauses: unknown[];
  field_confidence: Record<string, number>;
  injection_flags: string[];
  source_document: string;
}
export interface ExtractionListResponse {
  items: ExtractionItem[];
}

// ── Phase 8 — line-item depth & recovery ─────────────────────────────────────
export interface RateCardTierView {
  tier_index: number;
  min_volume: string;
  max_volume: string | null;
  tier_rate: string;
}
export interface RateCard {
  id: string;
  sku: string;
  raw_sku: string | null;
  description: string | null;
  unit_rate: string;
  uom: string;
  currency: string;
  is_tiered: boolean;
  source: string;
  confidence: string | null;
  verified_at: string | null;
  contract_id: string;
  tiers: RateCardTierView[];
}
export interface RateCardQueueResponse {
  items: RateCard[];
}
export interface RecoveryPackItem {
  id: string;
  opp_type: string | null;
  sku: string | null;
  quantity: string | null;
  billed_rate: string | null;
  contracted_rate: string | null;
  line_delta: string | null;
  amount: string;
}
export interface RecoveryPackDetail {
  pack_id: string;
  vendor_id: string | null;
  status: string;
  total_amount: string;
  items: RecoveryPackItem[];
}

// ── Phase 9 — workflow tasks & approval gates ────────────────────────────────
export interface WorkflowTask {
  id: string;
  title: string;
  type: string;
  status: string;
  priority: string;
  owner_id: string | null;
  opportunity_id: string | null;
  due_date: string | null;
}
export interface TasksResponse {
  tasks: WorkflowTask[];
}
export interface TaskDetail extends WorkflowTask {
  pending_gate_id: string | null;
}

// ── Phase 10 — commitment check & portfolio governance ───────────────────────
export interface StressScenarioView {
  move_pct: number;
  exposure: string;
  over_tolerance: boolean;
}
export interface CommitmentVerdictView {
  id: string;
  entity_id: string | null;
  vendor_name: string | null;
  indexed_exposure: string;
  scenarios: StressScenarioView[];
  verdict: "approve" | "condition" | "block";
  conditions: string[];
  rationale: string | null;
  advisory: boolean;
  signed_decision: string | null;
  signed_at: string | null;
}
export interface VendorLeverage {
  vendor_id: string;
  vendor: string | null;
  entities: string[];
  entity_count: number;
  total_spend: string;
  leverage_estimate: string;
  note: string;
}
export interface VendorLeverageResponse {
  vendors: VendorLeverage[];
}
