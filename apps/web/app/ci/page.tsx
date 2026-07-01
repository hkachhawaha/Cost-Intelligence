// Cost Intelligence — the single-workspace, Google-Sheets-driven product.
// Wrapped in Suspense so useSearchParams() inside CostIntelligenceApp works
// without triggering a Next.js build-time error.
import { Suspense } from "react";
import "./ci.css";

import { CostIntelligenceApp } from "./CostIntelligenceApp";

export const metadata = { title: "Terzo Cost Intelligence" };

export default function CostIntelligencePage() {
  return (
    <Suspense fallback={<div className="ci-loading">Loading…</div>}>
      <CostIntelligenceApp />
    </Suspense>
  );
}
