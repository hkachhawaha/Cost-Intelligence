// SERVER — contract-extraction verification queue (gated to legal/admin at the API).
import { VerificationQueue } from "@/components/modules/extraction/verification-queue";
import { apiServer } from "@/lib/api";
import type { ExtractionListResponse } from "@/lib/types";

export default async function ExtractionPage() {
  const { items } = await apiServer.get<ExtractionListResponse>(
    "/extraction/verification-queue",
  );
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Contract Extraction — Verification</h1>
      <p className="text-sm text-muted-foreground">
        Extracted terms never enter the canonical record until a reviewer promotes them.
      </p>
      <VerificationQueue initial={items} />
    </div>
  );
}
