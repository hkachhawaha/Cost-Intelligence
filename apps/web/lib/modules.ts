// The 12-module nav config (§3.2). v1Enabled gates Phase-5 modules; the rest are
// present in the nav but routed to "Soon" (Phase 7 / Phase 10).
import {
  LayoutDashboard,
  Target,
  BarChart3,
  FileText,
  Building2,
  TrendingUp,
  Banknote,
  CalendarClock,
  ShieldCheck,
  Layers,
  MessageSquare,
  CheckCircle2,
  ListChecks,
} from "lucide-react";

export interface ModuleDef {
  slug: string;
  label: string;
  icon: typeof LayoutDashboard;
  v1Enabled: boolean;
}

export const MODULES: ModuleDef[] = [
  { slug: "dashboard", label: "Dashboard", icon: LayoutDashboard, v1Enabled: true },
  { slug: "assessment", label: "Opportunity Assessment", icon: Target, v1Enabled: true },
  { slug: "spend", label: "Spend Explorer", icon: BarChart3, v1Enabled: true },
  { slug: "contracts", label: "Contracts", icon: FileText, v1Enabled: true },
  { slug: "renewals", label: "Renewals", icon: CalendarClock, v1Enabled: true },
  { slug: "recovery", label: "Margin Recovery", icon: Banknote, v1Enabled: true },
  { slug: "data-quality", label: "Data Quality", icon: CheckCircle2, v1Enabled: true },
  // Phase 7 modules — now live:
  { slug: "vendors", label: "Vendors", icon: Building2, v1Enabled: true },
  { slug: "indexation", label: "Indexation & Exposure", icon: TrendingUp, v1Enabled: true },
  { slug: "portfolio", label: "Portfolio", icon: Layers, v1Enabled: true },
  // Phase 9 module — agentic workflow tasks (human-in-the-loop approvals):
  { slug: "tasks", label: "Workflow Tasks", icon: ListChecks, v1Enabled: true },
  // Phase 10 module — pre-signature control (advisory; human signs):
  { slug: "commitment", label: "Commitment Check", icon: ShieldCheck, v1Enabled: true },
  { slug: "nirvana", label: "NirvanaI", icon: MessageSquare, v1Enabled: false },
];
