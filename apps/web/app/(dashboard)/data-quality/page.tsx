// SERVER — coverage from memory + canonical DQ event feed (parallel reads).
import { CoverageGauge } from "@/components/modules/dq/coverage-gauge";
import { ReviewQueueClient } from "@/components/modules/dq/review-queue-client";
import { apiServer } from "@/lib/api";
import type { DataQualityCoverage, DataQualityEventsResponse } from "@/lib/types";

export default async function DataQualityPage() {
  const [coverage, events] = await Promise.all([
    apiServer.get<DataQualityCoverage>("/data-quality/coverage"),
    apiServer.get<DataQualityEventsResponse>("/data-quality/events"),
  ]);
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Data Quality</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <CoverageGauge pct={coverage.match_coverage_pct} />
        <div className="rounded-lg border p-4">
          <div className="text-xs text-muted-foreground">Low-confidence matches</div>
          <div className="mt-1 text-2xl font-semibold">{coverage.low_confidence_matches}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs text-muted-foreground">Unmatched (maverick)</div>
          <div className="mt-1 text-2xl font-semibold">{coverage.unmatched_count}</div>
        </div>
      </div>
      <ReviewQueueClient initialEvents={events} />
    </div>
  );
}
