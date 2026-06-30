// SERVER — 90-day window preloaded from memory renewal_calendar.
import { RenewalsClient } from "@/components/modules/renewals/renewals-client";
import { apiServer } from "@/lib/api";
import type { RenewalsResponse } from "@/lib/types";

export default async function RenewalsPage() {
  const renewals = await apiServer.get<RenewalsResponse>("/renewals?window=90");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Renewals</h1>
      <RenewalsClient initial={renewals} />
    </div>
  );
}
