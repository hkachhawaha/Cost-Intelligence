// SERVER — initial ranked list (memory top_opportunities + canonical paginated).
import { AssessmentClient } from "@/components/modules/assessment/assessment-client";
import { apiServer } from "@/lib/api";
import type { OpportunityListResponse } from "@/lib/types";

export default async function AssessmentPage() {
  const initial = await apiServer.get<OpportunityListResponse>(
    "/opportunities?sort=ranked&page=1",
  );
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Opportunity Assessment</h1>
      <p className="text-sm text-muted-foreground">Ranked by impact × confidence.</p>
      <AssessmentClient initialData={initial} />
    </div>
  );
}
