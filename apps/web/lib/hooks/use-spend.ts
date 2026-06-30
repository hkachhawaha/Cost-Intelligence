import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { SpendBreakdownResponse } from "@/lib/types";

export function useSpendBreakdown(dim: string, initialData?: SpendBreakdownResponse) {
  return useQuery({
    queryKey: ["spend", dim],
    queryFn: () => apiClient.get<SpendBreakdownResponse>(`/spend/${dim}`),
    initialData,
    staleTime: 60_000,
  });
}
