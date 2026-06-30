// SERVER — preload exposure at the default 10% move; the slider re-models client-side.
import { ExposureSlider } from "@/components/modules/indexation/exposure-slider";
import { apiServer } from "@/lib/api";
import type { ExposureResponse } from "@/lib/types";

export default async function IndexationPage() {
  const initial = await apiServer.get<ExposureResponse>("/indexation/exposure?move_pct=10");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Indexation &amp; Exposure</h1>
      <p className="text-sm text-muted-foreground">
        Forward cost-risk modeled from a first-party assumed index move — not an external
        benchmark.
      </p>
      <ExposureSlider initial={initial} />
    </div>
  );
}
