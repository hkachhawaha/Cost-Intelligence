// SERVER — rate-card verification queue (extracted cards awaiting a human gate).
import { RateCardVerificationQueue } from "@/components/modules/rate-cards/rate-card-verification-queue";
import { apiServer } from "@/lib/api";
import type { RateCardQueueResponse } from "@/lib/types";

export default async function RateCardsPage() {
  const { items } = await apiServer.get<RateCardQueueResponse>("/rate-cards/verification-queue");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Rate Cards — Verification</h1>
      <p className="text-sm text-muted-foreground">
        Only verified rate cards drive line-item recovery (above-rate &amp; volume-tier). Extracted
        cards are inert until a reviewer approves them.
      </p>
      <RateCardVerificationQueue initial={items} />
    </div>
  );
}
