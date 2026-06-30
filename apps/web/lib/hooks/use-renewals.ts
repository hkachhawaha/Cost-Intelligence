import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { RenewalsResponse } from "@/lib/types";

export function useRenewals(window: 90 | 180 | 365, initialData?: RenewalsResponse) {
  return useQuery({
    queryKey: ["renewals", window],
    queryFn: () => apiClient.get<RenewalsResponse>(`/renewals?window=${window}`),
    initialData,
    staleTime: 60_000,
  });
}
