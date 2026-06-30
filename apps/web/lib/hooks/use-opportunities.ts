import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { OpportunityListResponse } from "@/lib/types";

export function useOpportunities(
  params: { sort?: string; status?: string },
  initialData?: OpportunityListResponse,
) {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return useQuery({
    queryKey: ["opportunities", params],
    queryFn: () => apiClient.get<OpportunityListResponse>(`/opportunities?${qs}`),
    initialData,
    staleTime: 60_000, // memory-backed; safe to cache briefly client-side
  });
}

export function useUpdateStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiClient.patch(`/opportunities/${id}/status`, { status }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["opportunities"] }),
  });
}

export function useAssignOwner() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, owner_id }: { id: string; owner_id: string }) =>
      apiClient.patch(`/opportunities/${id}/assign`, { owner_id }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["opportunities"] }),
  });
}
