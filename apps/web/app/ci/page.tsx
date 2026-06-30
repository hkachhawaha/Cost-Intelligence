// Cost Intelligence — the single-workspace, Google-Sheets-driven product (matches the
// Terzo-Cost-Intelligence-App-v2 prototype). Standalone full-screen SPA.
import "./ci.css";

import { CostIntelligenceApp } from "./CostIntelligenceApp";

export const metadata = { title: "Terzo Cost Intelligence" };

export default function CostIntelligencePage() {
  return <CostIntelligenceApp />;
}
