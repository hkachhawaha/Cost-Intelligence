// UI label shown wherever a capability would need external data (§3.4). The external-
// intelligence seam is interface-only and feature-flagged OFF in v1–v3 — Cost Intelligence
// is first-party only. NirvanaI returns the out-of-scope message for benchmark/should-cost asks.
import { Badge } from "@/components/ui/badge";

export function RequiresExternalDataBadge() {
  return (
    <Badge variant="muted" title="Out of scope: first-party data only">
      requires external data
    </Badge>
  );
}
